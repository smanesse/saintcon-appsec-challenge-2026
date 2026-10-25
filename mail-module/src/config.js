'use strict';
const path = require('path');

function num(v, def) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : def;
}

const MODULE_ROOT = path.join(__dirname, '..');

module.exports = {
  HOST: process.env.MTA_HOST || '0.0.0.0',
  PORT: num(process.env.MTA_PORT || process.env.SERVER_PORT, 2525),
  ADMIN_PORT: num(process.env.MTA_ADMIN_PORT, 8081),

  DOMAIN: process.env.MTA_DOMAIN || 'mta.local',

  QUEUE_DIR: process.env.MTA_QUEUE_DIR || path.join(MODULE_ROOT, 'queue'),

  LOCAL_USERS: (process.env.MTA_LOCAL_USERS || 'alice,bob,postmaster')
    .split(',').map((s) => s.trim()).filter(Boolean),

  AUTH_USER: process.env.MTA_AUTH_USER || 'relay',
  AUTH_PASS: process.env.MTA_AUTH_PASS || 'relay123',

  BOUNCE_SCRIPT: process.env.MTA_BOUNCE_SCRIPT || path.join(MODULE_ROOT, 'scripts', 'notify-bounce.sh'),
  BOUNCE_LOG: process.env.MTA_BOUNCE_LOG || path.join(MODULE_ROOT, 'data', 'bounces.log'),

  TLS_KEY: process.env.MTA_TLS_KEY || path.join(MODULE_ROOT, 'certs', 'dev-key.pem'),
  TLS_CERT: process.env.MTA_TLS_CERT || path.join(MODULE_ROOT, 'certs', 'dev-cert.pem'),

  WEBHOOK_TIMEOUT_MS: num(process.env.MTA_WEBHOOK_TIMEOUT_MS, 5000),

  RESOLVER: process.env.MTA_RESOLVER || null,
  RELAY_PORT: num(process.env.MTA_RELAY_PORT, 25),
  RELAY_TIMEOUT_MS: num(process.env.MTA_RELAY_TIMEOUT_MS, 8000),
};
