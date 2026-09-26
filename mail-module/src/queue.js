'use strict';
// Maildir-style queue: <QUEUE_DIR>/{new,cur,tmp}. Accepted messages are
// written to `new/` as flat files; this module has no concept of moving
// them to `cur/` (no separate "delivery worker" - this training service
// treats "queued" as "job done", which is realistic for a relay's outbound
// spool). Filenames are always server-generated (see deriveFilename()).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const config = require('./config');

function ensureQueueDir() {
  fs.mkdirSync(path.join(config.QUEUE_DIR, 'new'), { recursive: true });
  fs.mkdirSync(path.join(config.QUEUE_DIR, 'cur'), { recursive: true });
  fs.mkdirSync(path.join(config.QUEUE_DIR, 'tmp'), { recursive: true });
}

function deriveFilename() {
  // The on-disk name is always a server-generated, unpredictable identifier.
  // The client-supplied Message-ID is message content, never a filesystem
  // path. (VULN #7 was deriving the filename from Message-ID, so "../"
  // segments escaped the queue directory on both write and read.)
  return `${Date.now()}.${crypto.randomBytes(6).toString('hex')}.eml`;
}

const QUEUE_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

function queueFilePath(name) {
  // Shared by the writer below and the admin read-back endpoint (admin.js).
  // Only a plain queue filename is accepted, and the resolved path must still
  // sit directly inside QUEUE_DIR/new.
  const dir = path.resolve(config.QUEUE_DIR, 'new');
  if (typeof name !== 'string' || !QUEUE_NAME_RE.test(name) || name.includes('..')) {
    throw new Error('invalid queue file name');
  }
  const full = path.resolve(dir, name);
  if (path.dirname(full) !== dir) {
    throw new Error('invalid queue file name');
  }
  return full;
}

function writeMessage(envelope, rawSource) {
  const name = deriveFilename();
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
