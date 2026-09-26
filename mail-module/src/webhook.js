'use strict';
// Delivery-status notification (DSN) webhook callback. A submitter can ask
// to be POSTed a small JSON receipt once their message is queued, by adding
// an `X-Notify-Webhook: <url>` header to their message - a convenience
// feature modeled on real outbound-mail platforms (SendGrid/Mailgun/SES all
// offer webhook delivery events).
//
// The callback URL is client-supplied, so it is fenced: only http(s), and the
// destination must be a public address - loopback, private (RFC 1918 / ULA),
// link-local (incl. cloud metadata), CGNAT, multicast and reserved ranges are
// refused. The check runs inside the socket's DNS lookup, so the address that
// was validated is the one connected to (no rebinding window). Only the
// receiver's status code is recorded, never its response body. (VULN #8 was
// fetching any URL from the server's network position and recording the
// response body where the submitter could read it back.)
const dns = require('dns');
const http = require('http');
const https = require('https');
const net = require('net');
const { URL } = require('url');
const config = require('./config');

function ipv4Blocked(ip) {
  const [a, b] = ip.split('.').map(Number);
  return (
    a === 0 || a === 10 || a === 127 ||
    (a === 100 && b >= 64 && b <= 127) || // CGNAT
    (a === 169 && b === 254) || // link-local / cloud metadata
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    (a === 192 && b === 0) || // IETF protocol assignments
    (a === 198 && (b === 18 || b === 19)) || // benchmarking
    a >= 224 // multicast + reserved
  );
}

function addressBlocked(ip) {
  if (net.isIPv4(ip)) return ipv4Blocked(ip);
  const lower = ip.toLowerCase();
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(lower);
  if (mapped) return ipv4Blocked(mapped[1]);
  return (
    lower === '::' || lower === '::1' ||
    /^f[cd]/.test(lower) || // fc00::/7 unique-local
    /^fe[89ab]/.test(lower) || // fe80::/10 link-local
    /^ff/.test(lower) // multicast
  );
}

// dns.lookup-compatible resolver that refuses blocked destinations.
function guardedLookup(hostname, options, callback) {
  dns.lookup(hostname, { ...options, all: true }, (err, addresses) => {
    if (err) return callback(err);
    const bad = addresses.find((a) => addressBlocked(a.address));
    if (bad || addresses.length === 0) {
      const e = new Error(`webhook destination ${bad ? bad.address : hostname} is not allowed`);
      e.code = 'EWEBHOOKBLOCKED';
      return callback(e);
    }
    if (options && options.all) return callback(null, addresses);
    return callback(null, addresses[0].address, addresses[0].family);
  });
}

function fireWebhook(rawUrl, payload) {
  return new Promise((resolve) => {
    let parsed;
    try {
      parsed = new URL(rawUrl);
    } catch (e) {
      return resolve({ error: `invalid url: ${e.message}` });
    }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return resolve({ url: rawUrl, error: 'unsupported scheme' });
    }
    // A literal IP never goes through lookup, so check it here as well.
    const host = parsed.hostname.replace(/^\[|\]$/g, '');
    if (net.isIP(host) && addressBlocked(host)) {
      return resolve({ url: rawUrl, error: `webhook destination ${host} is not allowed` });
    }
    const mod = parsed.protocol === 'https:' ? https : http;
    const body = Buffer.from(JSON.stringify(payload));
    let settled = false;
    const finish = (result) => {
      if (!settled) {
        settled = true;
        resolve(result);
      }
    };
    const req = mod.request(
      parsed,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': body.length },
        timeout: config.WEBHOOK_TIMEOUT_MS,
        lookup: guardedLookup,
      },
      (res) => {
        res.resume(); // the receiver's reply body is never recorded
        res.on('end', () => finish({ url: rawUrl, status: res.statusCode }));
      }
    );
    req.on('error', (e) => finish({ url: rawUrl, error: e.message }));
    req.on('timeout', () => {
      req.destroy();
      finish({ url: rawUrl, error: 'timeout' });
    });
    req.write(body);
    req.end();
  });
}

module.exports = { fireWebhook };
