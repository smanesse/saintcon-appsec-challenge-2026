'use strict';
const fs = require('fs');
const config = require('./config');

let KEY;
let CERT;
try {
  KEY = fs.readFileSync(config.TLS_KEY);
  CERT = fs.readFileSync(config.TLS_CERT);
} catch (e) {
  console.error(`[mta] WARNING: could not load TLS cert/key from ${config.TLS_KEY} / ${config.TLS_CERT} (${e.message}); STARTTLS will fail`);
}

module.exports = { KEY, CERT };
