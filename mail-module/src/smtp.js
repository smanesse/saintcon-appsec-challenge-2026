'use strict';
const crypto = require('crypto');
const tls = require('tls');
const config = require('./config');
const queue = require('./queue');
const registry = require('./registry');
const bounce = require('./bounce');
const webhook = require('./webhook');
const delivery = require('./delivery');
const { decodeXtext } = require('./xtext');
const tlscert = require('./tlscert');

function sanitizeAddr(raw) {
  // Strip control characters from an envelope address before it's used
  // anywhere. Applied to MAIL FROM / RCPT TO addresses. (The decoded AUTH=
  // parameter is rejected outright if it carries them - see onMailFrom().)
  return String(raw || '').replace(/[\r\n\0]/g, '').trim();
}

function domainOf(addr) {
  const at = addr.lastIndexOf('@');
  return at === -1 ? '' : addr.slice(at + 1);
}

function localPartOf(addr) {
  const at = addr.lastIndexOf('@');
  return at === -1 ? addr : addr.slice(0, at);
}

function safeEqual(provided, actual) {
  const a = crypto.createHash('sha256').update(String(provided)).digest();
  const b = crypto.createHash('sha256').update(String(actual)).digest();
  return crypto.timingSafeEqual(a, b);
}

class SmtpSession {
  constructor(socket) {
    this.socket = socket;
    this.buffer = '';
    this.state = 'command';
    this.pendingAuth = null;
    this.authenticated = false;
    this.tlsActive = false;
    this.heloName = null;
    this.envelope = null;
    this.dataLines = [];

    socket.on('data', (chunk) => this.onSocketData(chunk));
    socket.on('error', () => {});
    socket.on('close', () => {});

    this.greet();
  }

  write(text) {
    try {
      this.socket.write(text);
    } catch (e) {
    }
  }

  greet() {
    this.write(`220 ${config.DOMAIN} ESMTP MTA Service ready\r\n`);
  }

  onSocketData(chunk) {
    this.buffer += chunk.toString('binary');
    this.drain();
  }

  drain() {
    let idx;
    while ((idx = this.buffer.indexOf('\n')) !== -1) {
      let line = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 1);
      if (line.endsWith('\r')) line = line.slice(0, -1);

      if (this.state === 'data') {
        this.onDataLine(line);
      } else {
        this.onCommandLine(line);
      }
    }
  }

  onCommandLine(line) {
    if (this.pendingAuth) {
      return this.onAuthContinuation(line);
    }
    if (line.trim() === '') return;

    const verb = line.split(/\s+/, 1)[0].toUpperCase();
    switch (verb) {
      case 'HELO':
        return this.onHelo(line, false);
      case 'EHLO':
        return this.onHelo(line, true);
      case 'MAIL':
        return this.onMailFrom(line);
      case 'RCPT':
        return this.onRcptTo(line);
      case 'DATA':
        return this.onDataCommand();
      case 'RSET':
        this.envelope = null;
        return this.write('250 2.0.0 Ok\r\n');
      case 'NOOP':
        return this.write('250 2.0.0 Ok\r\n');
      case 'STARTTLS':
        return this.onStartTls();
      case 'AUTH':
        return this.onAuth(line);
      case 'QUIT':
        this.write('221 2.0.0 Bye\r\n');
        return this.socket.end();
      default:
        return this.write('502 5.5.2 Command not recognized\r\n');
    }
  }

  onHelo(line, extended) {
    const parts = line.trim().split(/\s+/);
    this.heloName = sanitizeAddr(parts[1] || '').slice(0, 255) || 'unknown';
    this.envelope = null;

    if (!extended) {
      return this.write(`250 ${config.DOMAIN} Hello ${this.heloName}\r\n`);
    }
    const lines = [
      `250-${config.DOMAIN} Hello ${this.heloName}`,
      '250-PIPELINING',
      '250-8BITMIME',
      '250-AUTH PLAIN LOGIN',
    ];
    if (!this.tlsActive) lines.push('250-STARTTLS');
    lines.push('250 HELP');
    this.write(lines.join('\r\n') + '\r\n');
  }

  onMailFrom(line) {
    const m = /^MAIL\s+FROM:\s*<([^>]*)>\s*(.*)$/i.exec(line.trim());
    if (!m) return this.write('501 5.5.4 Syntax error in MAIL FROM parameters\r\n');

    const rawFrom = m[1];
    const rest = m[2] || '';
    let authParam = null;
    for (const p of rest.split(/\s+/).filter(Boolean)) {
      const eq = p.indexOf('=');
      if (eq === -1) continue;
      const key = p.slice(0, eq).toUpperCase();
      const val = p.slice(eq + 1);
      if (key === 'AUTH') {
        // RFC 4954 ESMTP AUTH= parameter, xtext-encoded. Per RFC 3461 §4 a
        // decoded value carrying CR, LF or NUL is invalid and is rejected
        // outright, so it can never splice a line into the stored header
        // block (see finishData()). (VULN #2 was keeping such a value as-is,
        // letting "+0D+0A" forge an X-Notify-Webhook header.)
        authParam = decodeXtext(val);
        if (/[\r\n\0]/.test(authParam)) {
          return this.write('501 5.5.4 Invalid AUTH= parameter\r\n');
        }
      }
    }

    this.envelope = {
      from: sanitizeAddr(rawFrom),
      authParam,
      rcpts: [],
      messageId: null,
      subject: null,
      notifyWebhook: null,
    };
    this.write('250 2.1.0 Ok\r\n');
  }

  onRcptTo(line) {
    if (!this.envelope) {
      return this.write('503 5.5.1 Bad sequence of commands: need MAIL FROM first\r\n');
    }
    const m = /^RCPT\s+TO:\s*<([^>]*)>/i.exec(line.trim());
    if (!m) return this.write('501 5.5.4 Syntax error in RCPT TO parameters\r\n');

    const rcpt = sanitizeAddr(m[1]);
    if (!rcpt.includes('@')) return this.write('501 5.1.3 Bad recipient address syntax\r\n');

    // Relay control: mail for MTA_DOMAIN is accepted from anyone, but relaying
    // to any other domain requires an authenticated session. (VULN #1 was an
    // open relay: any unauthenticated client could push unbounded mail for
    // any domain onto the shared queue disk.)
    if (domainOf(rcpt).toLowerCase() !== config.DOMAIN.toLowerCase() && !this.authenticated) {
      return this.write('554 5.7.1 Relay access denied: authentication required\r\n');
    }
    this.envelope.rcpts.push(rcpt);
    this.write('250 2.1.5 Ok\r\n');
  }

  onDataCommand() {
    if (!this.envelope || this.envelope.rcpts.length === 0) {
      return this.write('503 5.5.1 Bad sequence of commands: need MAIL FROM/RCPT TO first\r\n');
    }
    this.state = 'data';
    this.dataLines = [];
    this.write('354 End data with <CR><LF>.<CR><LF>\r\n');
  }

  onDataLine(line) {
    if (line === '.') {
      this.finishData();
      return;
    }
    if (line.startsWith('..')) line = line.slice(1);
    this.dataLines.push(line);
  }

  finishData() {
    this.state = 'command';
    const body = this.dataLines.join('\r\n');
    this.dataLines = [];

    const bodyBlankIdx = body.indexOf('\r\n\r\n');
    const bodyHeaderBlock = bodyBlankIdx === -1 ? body : body.slice(0, bodyBlankIdx);
    for (const hl of bodyHeaderBlock.split('\r\n')) {
      const mid = /^Message-ID:\s*(.+)$/i.exec(hl);
      if (mid) this.envelope.messageId = mid[1].trim();
      const subj = /^Subject:\s*(.*)$/i.exec(hl);
      if (subj) this.envelope.subject = subj[1].trim();
    }

    let prefix = `Return-Path: <${this.envelope.from}>\r\n`;
    prefix += `Received: from ${this.heloName || 'unknown'} by ${config.DOMAIN} with ESMTP; ${new Date().toUTCString()}\r\n`;
    if (this.envelope.authParam && this.tlsActive) {
      // authParam was validated CR/LF/NUL-free in onMailFrom(), so this is
      // exactly one header line.
      prefix += `X-Original-Auth: ${this.envelope.authParam}\r\n`;
    }

    const rawSource = prefix + body;
    let name;
    let size;
    try {
      ({ name, size } = queue.writeMessage(this.envelope, rawSource));
    } catch (e) {
      // A failed spool write (e.g. ENOSPC on a full queue disk) rejects this
      // one message; it must never escape as an uncaught exception and take
      // the whole relay down.
      console.error(`[mta] queue write failed: ${e.message}`);
      this.envelope = null;
      return this.write('452 4.3.1 Insufficient system storage\r\n');
    }

    const rawBlankIdx = rawSource.indexOf('\r\n\r\n');
    const rawHeaderBlock = rawBlankIdx === -1 ? rawSource : rawSource.slice(0, rawBlankIdx);
    let notifyWebhook = null;
    for (const hl of rawHeaderBlock.split('\r\n')) {
      const hook = /^X-Notify-Webhook:\s*(.+)$/i.exec(hl);
      if (hook) notifyWebhook = hook[1].trim();
    }
    this.envelope.notifyWebhook = notifyWebhook;

    registry.record(name, {
      from: this.envelope.from,
      to: this.envelope.rcpts.slice(),
      subject: this.envelope.subject,
      size,
      receivedAt: new Date().toISOString(),
      webhook: null,
    });

    for (const rcpt of this.envelope.rcpts) {
      const domain = domainOf(rcpt);
      const local = localPartOf(rcpt);
      if (domain === config.DOMAIN && !config.LOCAL_USERS.includes(local)) {
        bounce.sendBounceNotification(this.envelope.from, rcpt, 'no such user');
      }
    }

    if (this.envelope.notifyWebhook && this.authenticated) {
      webhook
        .fireWebhook(this.envelope.notifyWebhook, {
          queued: name,
          from: this.envelope.from,
          to: this.envelope.rcpts,
        })
        .then((result) => registry.updateWebhook(name, result));
    }

    if (config.RESOLVER) {
      const envForDelivery = { from: this.envelope.from, rcpts: this.envelope.rcpts.slice() };
      delivery
        .deliverMessage(envForDelivery, rawSource)
        .then((result) => registry.updateDelivery(name, result))
        .catch((e) => registry.updateDelivery(name, [{ status: 'deferred', error: e.message }]));
    }

    this.write(`250 2.0.0 Ok: queued as ${name}\r\n`);
    this.envelope = null;
  }

  onAuth(line) {
    const parts = line.trim().split(/\s+/);
    const mech = (parts[1] || '').toUpperCase();
    if (mech === 'PLAIN') {
      if (parts[2]) return this.finishAuthPlain(parts[2]);
      this.pendingAuth = 'PLAIN';
      return this.write('334 \r\n');
    }
    if (mech === 'LOGIN') {
      this.pendingAuth = 'LOGIN_USER';
      return this.write('334 VXNlcm5hbWU6\r\n');
    }
    return this.write('504 5.5.4 Unrecognized authentication type\r\n');
  }

  onAuthContinuation(line) {
    if (this.pendingAuth === 'PLAIN') {
      this.pendingAuth = null;
      return this.finishAuthPlain(line.trim());
    }
    if (this.pendingAuth === 'LOGIN_USER') {
      this.authLoginUser = this.b64decode(line.trim());
      this.pendingAuth = 'LOGIN_PASS';
      return this.write('334 UGFzc3dvcmQ6\r\n');
    }
    if (this.pendingAuth === 'LOGIN_PASS') {
      const pass = this.b64decode(line.trim());
      this.pendingAuth = null;
      return this.checkAuth(this.authLoginUser, pass);
    }
    this.pendingAuth = null;
    return this.write('501 5.5.2 Authentication cancelled\r\n');
  }

  b64decode(s) {
    try {
      return Buffer.from(s, 'base64').toString('utf8');
    } catch {
      return '';
    }
  }

  finishAuthPlain(b64) {
    const decoded = this.b64decode(b64);
    const segs = decoded.split('\0');
    const user = segs.length >= 3 ? segs[1] : segs[0] || '';
    const pass = segs.length >= 3 ? segs[2] : segs[1] || '';
    this.checkAuth(user, pass);
  }

  checkAuth(user, pass) {
    const userOk = safeEqual(user, config.AUTH_USER);
    const passOk = safeEqual(pass, config.AUTH_PASS);
    if (userOk && passOk) {
      this.authenticated = true;
      return this.write('235 2.7.0 Authentication successful\r\n');
    }
    return this.write('535 5.7.8 Authentication credentials invalid\r\n');
  }

  onStartTls() {
    if (this.tlsActive) return this.write('503 5.5.1 Already using TLS\r\n');
    if (!tlscert.KEY || !tlscert.CERT) return this.write('454 4.7.0 TLS not available\r\n');

    this.write('220 2.0.0 Ready to start TLS\r\n');

    const rawSocket = this.socket;
    rawSocket.removeAllListeners('data');
    const tlsSocket = new tls.TLSSocket(rawSocket, {
      isServer: true,
      key: tlscert.KEY,
      cert: tlscert.CERT,
    });
    this.socket = tlsSocket;
    this.tlsActive = true;
    this.heloName = null;
    this.envelope = null;

    tlsSocket.on('data', (chunk) => this.onSocketData(chunk));
    tlsSocket.on('error', () => {});
    tlsSocket.on('close', () => {});

  }
}

module.exports = { SmtpSession };
