'use strict';
const http = require('http');
const https = require('https');
const { URL } = require('url');
const config = require('./config');

function fireWebhook(rawUrl, payload) {
  return new Promise((resolve) => {
    let parsed;
    try {
      parsed = new URL(rawUrl);
    } catch (e) {
      return resolve({ error: `invalid url: ${e.message}` });
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
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => {
          if (data.length < 4096) data += chunk.toString('binary');
        });
        res.on('end', () => finish({ url: rawUrl, status: res.statusCode, body: data.slice(0, 2000) }));
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
