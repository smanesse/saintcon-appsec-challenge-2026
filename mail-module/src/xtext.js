'use strict';
function decodeXtext(value) {
  return String(value).replace(/\+([0-9A-Fa-f]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

module.exports = { decodeXtext };
