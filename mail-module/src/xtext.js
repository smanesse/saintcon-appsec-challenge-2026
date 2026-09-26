'use strict';
// "xtext" encoding, RFC 3461 §4 (used by the ESMTP DSN extension's ORCPT/
// ENVID parameters) and RFC 4954/2554 (the AUTH= parameter on MAIL FROM).
// It exists precisely so a mailbox/identity string that contains bytes a
// plain SMTP command line can't carry safely (space, '+', high-bit octets,
// and - relevantly here - CR/LF/NUL) can be represented as plain ASCII:
// any octet may be written as "+HH" (two hex digits).
//
// RFC 3461 §4 is explicit that after decoding, an implementation MUST treat
// a decoded value containing CR, LF, or NUL as invalid and reject it before
// using it anywhere - those bytes are exactly why xtext exists, so letting
// them back out undefeats the whole point. decodeXtext() below does the
// decoding; src/smtp.js's onMailFrom() performs that rejection before the
// decoded AUTH= value is used anywhere.
function decodeXtext(value) {
  return String(value).replace(/\+([0-9A-Fa-f]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

module.exports = { decodeXtext };
