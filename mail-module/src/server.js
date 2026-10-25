#!/usr/bin/env node
'use strict';
const net = require('net');
const fs = require('fs');
const path = require('path');
const config = require('./config');
const { SmtpSession } = require('./smtp');
const { startAdminServer } = require('./admin');
const queue = require('./queue');

queue.ensureQueueDir();
fs.mkdirSync(path.dirname(config.BOUNCE_LOG), { recursive: true });

const smtpServer = net.createServer((socket) => {
  new SmtpSession(socket);
});

smtpServer.on('error', (e) => {
  console.error(`[mta] SMTP server error: ${e.message}`);
  process.exit(1);
});

smtpServer.listen(config.PORT, config.HOST, () => {
  console.log(`[mta] SMTP listening on ${config.HOST}:${config.PORT} (domain=${config.DOMAIN})`);
});

startAdminServer();
