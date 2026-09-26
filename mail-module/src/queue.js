'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const config = require('./config');

function ensureQueueDir() {
  fs.mkdirSync(path.join(config.QUEUE_DIR, 'new'), { recursive: true });
  fs.mkdirSync(path.join(config.QUEUE_DIR, 'cur'), { recursive: true });
  fs.mkdirSync(path.join(config.QUEUE_DIR, 'tmp'), { recursive: true });
}

function deriveFilename(envelope) {
  if (envelope.messageId) {
    return envelope.messageId.replace(/[<>]/g, '').trim();
  }
  return `${Date.now()}.${crypto.randomBytes(6).toString('hex')}.eml`;
}

function queueFilePath(name) {
  return path.join(config.QUEUE_DIR, 'new', name);
}

function writeMessage(envelope, rawSource) {
  const name = deriveFilename(envelope);
  const filePath = queueFilePath(name);
  try {
    fs.writeFileSync(filePath, rawSource, { encoding: 'binary' });
  } catch (e) {
    // Don't leave a truncated spool file behind (e.g. after ENOSPC).
    try {
      fs.unlinkSync(filePath);
    } catch {
      // nothing written, or already gone
    }
    throw e;
  }
  return { name, filePath, size: Buffer.byteLength(rawSource, 'binary') };
}

function readMessage(name) {
  return fs.readFileSync(queueFilePath(name), 'binary');
}

function listNew() {
  try {
    return fs.readdirSync(path.join(config.QUEUE_DIR, 'new'));
  } catch {
    return [];
  }
}

module.exports = { ensureQueueDir, deriveFilename, queueFilePath, writeMessage, readMessage, listNew };
