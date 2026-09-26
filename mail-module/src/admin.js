'use strict';
const http = require('http');
const fs = require('fs');
const config = require('./config');
const queue = require('./queue');
const registry = require('./registry');

function send(res, status, body, contentType) {
  const isString = typeof body === 'string';
  const buf = Buffer.from(isString ? body : JSON.stringify(body, null, 2));
  res.writeHead(status, {
    'Content-Type': contentType || (isString ? 'text/plain' : 'application/json'),
    'Content-Length': buf.length,
  });
  res.end(buf);
}

function startAdminServer() {
  const server = http.createServer((req, res) => {
    try {
      handle(req, res);
    } catch (e) {
      send(res, 500, { error: e.message });
    }
  });
  server.listen(config.ADMIN_PORT, config.HOST, () => {
    console.log(`[mta] admin HTTP listening on ${config.HOST}:${config.ADMIN_PORT}`);
  });
  return server;
}

function handle(req, res) {
  const pathname = (req.url || '').split('?')[0];

  if (req.method === 'GET' && pathname === '/health') {
    return send(res, 200, { status: 'ok' });
  }

  if (req.method === 'GET' && pathname === '/queue') {
    return send(res, 200, registry.list());
  }

  if (req.method === 'GET' && req.url.startsWith('/queue/')) {
    const name = decodeURIComponent(req.url.slice('/queue/'.length).split('?')[0]);
    let raw;
    try {
      // This re-reads straight from disk via queue.readMessage() rather than
      // trusting the in-memory registry; queueFilePath() rejects any name
      // that isn't a plain file directly inside the queue directory.
      raw = queue.readMessage(name);
    } catch (e) {
      return send(res, 404, { error: 'not found' });
    }
    const meta = registry.get(name) || {};
    return send(res, 200, { name, ...meta, raw });
  }

  if (req.method === 'GET' && pathname === '/bounces') {
    try {
      return send(res, 200, fs.readFileSync(config.BOUNCE_LOG, 'utf8'), 'text/plain');
    } catch {
      return send(res, 200, '', 'text/plain');
    }
  }

  send(res, 404, { error: 'not found' });
}

module.exports = { startAdminServer };
