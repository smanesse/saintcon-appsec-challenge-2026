'use strict';
const net = require('net');
const dnsp = require('dns').promises;
const config = require('./config');

function domainOf(addr) {
  const at = String(addr).lastIndexOf('@');
  return at === -1 ? '' : addr.slice(at + 1).trim().toLowerCase();
}

async function dnsmResolver() {
  let host = config.RESOLVER;
  let port = 53;
  const colon = host.lastIndexOf(':');
  if (colon !== -1) {
    const p = parseInt(host.slice(colon + 1), 10);
    if (Number.isFinite(p)) { port = p; host = host.slice(0, colon); }
  }
  let ip = host;
  if (!net.isIP(host)) {
    const { address } = await dnsp.lookup(host);
    ip = address;
  }
  const r = new dnsp.Resolver();
  r.setServers([`${ip}:${port}`]);
  return r;
}

async function nextHopFor(r, domain) {
  let mxHost = domain;
  try {
    const mx = await r.resolveMx(domain);
    if (mx && mx.length) {
      mx.sort((a, b) => a.priority - b.priority);
      mxHost = mx[0].exchange;
    }
  } catch (_) { }
  const addrs = await r.resolve4(mxHost);
  return { mxHost, ip: addrs[0] };
}

function wrapData(rawSource) {
  const stuffed = String(rawSource).replace(/\r?\n\./g, (m) => m.replace('.', '..'));
  const withCrlf = stuffed.replace(/\r?\n/g, '\r\n');
  return withCrlf.replace(/\r\n$/, '') + '\r\n.\r\n';
}

function relayOne(ip, port, from, rcpt, rawSource) {
  return new Promise((resolve) => {
    const sock = net.createConnection({ host: ip, port });
    sock.setTimeout(config.RELAY_TIMEOUT_MS);
    let buf = '';
    let settled = false;
    const steps = [
      { expect: 220, send: `EHLO ${config.DOMAIN}\r\n` },
      { expect: 250, send: `MAIL FROM:<${from}>\r\n` },
      { expect: 250, send: `RCPT TO:<${rcpt}>\r\n` },
      { expect: 250, send: 'DATA\r\n' },
      { expect: 354, send: wrapData(rawSource) },
      { expect: 250, send: 'QUIT\r\n' },
    ];
    let i = 0;
    const done = (result) => {
      if (settled) return;
      settled = true;
      try { sock.destroy(); } catch (_) { }
      resolve({ nextHop: `${ip}:${port}`, ...result });
    };
    const readReply = () => {
      const lines = buf.split('\r\n');
      for (let k = 0; k < lines.length; k++) {
        const line = lines[k];
        if (line.length >= 4 && line[3] === ' ' && /^\d{3}$/.test(line.slice(0, 3))) {
          buf = lines.slice(k + 1).join('\r\n');
          return parseInt(line.slice(0, 3), 10);
        }
      }
      return null;
    };
    const pump = () => {
      let code;
      while ((code = readReply()) !== null) {
        const step = steps[i];
        if (!step) return;
        if (code !== step.expect) {
          return done({ status: 'rejected', code, at: i });
        }
        sock.write(step.send);
        i += 1;
        if (i >= steps.length) return done({ status: 'delivered', code });
      }
    };
    sock.on('data', (chunk) => { buf += chunk.toString('binary'); pump(); });
    sock.on('timeout', () => done({ status: 'deferred', error: 'timeout' }));
    sock.on('error', (e) => done({ status: 'deferred', error: e.message }));
    sock.on('close', () => done({ status: 'deferred', error: 'connection closed' }));
  });
}

async function deliverMessage(envelope, rawSource) {
  if (!config.RESOLVER) return null;
  const results = [];
  let resolver;
  try {
    resolver = await dnsmResolver();
  } catch (e) {
    return [{ status: 'deferred', error: `resolver init failed: ${e.message}` }];
  }
  const domains = new Map();
  for (const rcpt of envelope.rcpts || []) {
    const d = domainOf(rcpt);
    if (!d || d === config.DOMAIN) continue;
    if (!domains.has(d)) domains.set(d, []);
    domains.get(d).push(rcpt);
  }
  for (const [domain, rcpts] of domains) {
    let hop;
    try {
      hop = await nextHopFor(resolver, domain);
    } catch (e) {
      results.push({ domain, status: 'deferred', error: `no route: ${e.message}` });
      continue;
    }
    for (const rcpt of rcpts) {
      const r = await relayOne(hop.ip, config.RELAY_PORT, envelope.from, rcpt, rawSource);
      results.push({ domain, rcpt, mxHost: hop.mxHost, ...r });
    }
  }
  return results;
}

module.exports = { deliverMessage, domainOf };
