'use strict';
const messages = new Map();

function record(name, meta) {
  messages.set(name, meta);
}

function get(name) {
  return messages.get(name);
}

function list() {
  return Array.from(messages.entries()).map(([name, meta]) => ({ name, ...meta }));
}

function updateWebhook(name, result) {
  const meta = messages.get(name);
  if (meta) meta.webhook = result;
}

function updateDelivery(name, result) {
  const meta = messages.get(name);
  if (meta) meta.delivery = result;
}

module.exports = { record, get, list, updateWebhook, updateDelivery };
