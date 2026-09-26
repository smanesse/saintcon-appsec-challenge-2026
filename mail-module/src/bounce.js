'use strict';
// Bounce/delivery-failure notification hook. Real MTAs commonly shell out
// to a site-local script or a `sendmail`-compatible binary to handle bounce
// notifications (paging, ticketing, a custom DSN mailer) rather than
// hardcoding that policy in the daemon itself - see Sendmail's mailer
// definitions or Exim's `system_filter`/transport hooks for the real-world
// pattern this mirrors.
const { execFile } = require('child_process');
const config = require('./config');

function sendBounceNotification(envelopeFrom, rcpt, reason) {
  // The script is run directly with an argument vector - no shell is
  // involved, so the attacker-controlled envelope sender reaches the script
  // as a single inert argument ($1) whatever characters it contains. (VULN
  // #3 was interpolating it into a /bin/sh command string, where $(...) and
  // backticks executed even inside the double quotes.)
  execFile(config.BOUNCE_SCRIPT, [envelopeFrom, rcpt, reason], { timeout: 5000 }, (err) => {
    if (err) {
      console.error(`[bounce] notify-bounce.sh failed: ${err.message}`);
    }
  });
}

module.exports = { sendBounceNotification };
