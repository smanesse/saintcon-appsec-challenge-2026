'use strict';
const { exec } = require('child_process');
const config = require('./config');

function sendBounceNotification(envelopeFrom, rcpt, reason) {
  const cmd = `"${config.BOUNCE_SCRIPT}" "${envelopeFrom}" "${rcpt}" "${reason}"`;
  exec(cmd, { timeout: 5000 }, (err) => {
    if (err) {
      console.error(`[bounce] notify-bounce.sh failed: ${err.message}`);
    }
  });
}

module.exports = { sendBounceNotification };
