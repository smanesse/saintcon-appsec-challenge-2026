/* Concise station help for the module ? button.
 * Normal use only. The Tutorial in help.js is a separate control.
 * Every string is painted with textContent. Pictures live under assets/help/.
 */

const pic = (code, id) => 'assets/help/' + code + '/' + id + '.png';

function page(code, id, title, paragraphs, alt) {
  return { id, title, paragraphs, image: pic(code, id), alt };
}

function mod(code, what, tryText, pages, controls, excluded) {
  return { what, try: tryText, pages, controls, excluded };
}

const devbar = {
  name: 'debug toolbar',
  reason: 'The occlusion, text, plane, and hotspot buttons are dev chrome, not part of the player station.',
};

export const MODULE_HELP = {
  DNSM: mod(
    'DNSM',
    "Query and edit example.com DNS records.",
    "Enter www.example.com in QNAME and press Enter.",
    [
      page('DNSM', 'purpose', 'What this station is', [
        "Query DNS records: enter QNAME, choose QUERY TYPE, then click BEACON SWEEP.",
        "Read replies in STAR CHART; open CHART COURIER to edit records.",
      ], 'The Nav Beacon, the name-lookup station'),
      page('DNSM', 'qname', 'The name to look up', [
        "Click QNAME, enter www.example.com, and press Enter to query.",
        "Escape cancels editing without sending.",
      ], 'QNAME, the line where the lookup name is typed'),
      page('DNSM', 'qtype', 'The kind of record', [
        "Select QUERY TYPE before querying.",
        "NXDOM indicates a missing name; it is not a control.",
      ], 'QUERY TYPE, the row of record-kind lamps'),
      page('DNSM', 'sweep', 'Sending the lookup', [
        "Click BEACON SWEEP or press Enter to query; dragging also queries on release.",
        "Double-click to keep the beam rotating.",
      ], 'BEACON SWEEP, the scope that sends a lookup'),
      page('DNSM', 'chart', 'Reading the replies', [
        "Drag STAR CHART up or down to review replies.",
        "New replies appear first and scroll into view automatically.",
      ], 'STAR CHART, the drum that shows the replies'),
      page('DNSM', 'card', 'The chart card', [
        "Open CHART COURIER for LOOKUP or RECORDS.",
        "Queries also update QNAME and STAR CHART.",
      ], 'The chart card, out of the courier slot'),
      page('DNSM', 'lookup', 'Looking up on the card', [
        "Use LOOK UP or Enter to query the synchronized name and type fields.",
        "Select a PLOT LOG entry to query it again.",
      ], 'name, type, LOOK UP and the plot log'),
      page('DNSM', 'records', 'Adding records', [
        "Use ADD to draft records relative to example.com (@ for the apex), then SEND or Ctrl+Enter to import them.",
        "RELOAD FILE restores records from the zone file.",
      ], 'name, type, value, the chart text, SEND and RELOAD FILE'),
      mastPage('DNSM'),
      refitPage('DNSM'),
    ],
    [
      ctl('QNAME', 'hotspot QNAME', 'beginQueryEdit, Enter calls fireQuery', 'service', 'qname'),
      ctl('QUERY TYPE', 'P.qtype hotspot', 'setQtype', 'local', 'qtype'),
      ctl('BEACON SWEEP', 'sweepHot', 'click or pointerup calls fireQuery', 'service', 'sweep'),
      ctl('STAR CHART', 'P.chart hotspot', 'drag rolls the drum', 'display', 'chart'),
      ctl('CHART COURIER', 'courierHot', 'openCard', 'local', 'card'),
      ctl('Close', '#cardClose', 'closeCard', 'local', 'card'),
      ctl('LOOKUP', '#tabLookup', 'showFace', 'local', 'card'),
      ctl('RECORDS', '#tabRecords', 'showFace', 'local', 'card'),
      ctl('name', '#cardName', 'lookup name', 'service', 'lookup'),
      ctl('type', '#cardType', 'setQtype', 'local', 'lookup'),
      ctl('LOOK UP', '#cardLook', 'fireQuery', 'service', 'lookup'),
      ctl('plot log', '#cardRecent', 'replot', 'service', 'lookup'),
      ctl('name', '#recName', 'record owner', 'local', 'records'),
      ctl('type', '#recType', 'record type', 'local', 'records'),
      ctl('value', '#recVal', 'record value', 'local', 'records'),
      ctl('ADD', '#recAdd', 'addRecord', 'local', 'records'),
      ctl('chart text', '#recText', 'zone lines to send', 'service', 'records'),
      ctl('SEND', '#recSend', 'fireImport', 'service', 'records'),
      ctl('RELOAD FILE', '#recReload', 'fireReload', 'service', 'records'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  FMM: mod(
    'FMM',
    "Browse, read, and upload files.",
    "Open MANIFEST, SIGN IN, then double-click a file.",
    [
      page('FMM', 'purpose', 'What this station is', [
        "Open MANIFEST and SIGN IN to browse or transfer files.",
        "File uploads do not submit code for grading.",
      ], 'The Cargo Bay, the file-transfer station'),
      page('FMM', 'manifest', 'Picking up the manifest', [
        "Open MANIFEST for the file list.",
        "The clipboard keeps showing your folder and selection when the sheet is closed.",
      ], 'MANIFEST, the clipboard whose sheet lifts up'),
      page('FMM', 'signin', 'Signing in', [
        "Use the prefilled account with SIGN IN, or paste a TOKEN and select RESUME.",
        "COPY TOKEN copies it to the clipboard; SIGN OUT forgets it locally.",
      ], 'The manifest sheet sign-in fields USER, PASS, SIGN IN, TOKEN and RESUME'),
      page('FMM', 'files', 'Folders and files', [
        "Double-click a row or press Enter to open it; Backspace or UP returns to the parent folder.",
        "REFRESH reloads the list; LOG shows protocol exchanges.",
      ], 'The manifest sheet with the path, the list, UP, REFRESH and LOG'),
      page('FMM', 'view', 'Reading a file', [
        "Select a file and use OPEN to view it.",
        "SAVE downloads a local copy; EDIT prepares a text file for editing and upload.",
      ], 'A cargo slip with a fetched file, SAVE and EDIT'),
      page('FMM', 'upload', 'Uploading a file', [
        "Open NEW SLIP, set NAME, and type contents or use FROM DISK.",
        "LOAD CRATE uploads here; names require letters, digits or underscores, a dot, and an alphanumeric extension.",
      ], 'An outbound slip with NAME, the contents, FROM DISK and LOAD CRATE'),
      page('FMM', 'channel', 'How the bytes travel', [
        "Choose PASV or PORT with CHANNEL and I or A with TYPE.",
        "Check the data deck for the endpoint and transfer result.",
      ], 'CHANNEL and TYPE on the bay'),
      page('FMM', 'lift', 'The lift and the rail', [
        "After signing in, drag CARGO LIFT up to fetch the selected file, or down to open an outbound slip (upload if already open).",
        "DATA RAIL only animates.",
      ], 'CARGO LIFT and DATA RAIL on the Cargo Bay'),
      page('FMM', 'hold', 'The hold dial', [
        "Drag HOLD to move the gauge; it sends no file command.",
      ], 'The HOLD dial on the Cargo Bay'),
      mastPage('FMM'),
      refitPage('FMM'),
    ],
    [
      ctl('MANIFEST', 'manifestHot', 'openPunch', 'local', 'manifest'),
      ctl('Close', '#punchClose', 'hidePunch', 'local', 'manifest'),
      ctl('USER', '#punchUser', 'sent by SIGN IN', 'service', 'signin'),
      ctl('PASS', '#punchPass', 'sent by SIGN IN', 'service', 'signin'),
      ctl('SIGN IN', '#punchLogin', 'doLogin', 'service', 'signin'),
      ctl('TOKEN', '#punchTok', 'sent by RESUME', 'service', 'signin'),
      ctl('RESUME', '#punchSess', 'doSess', 'service', 'signin'),
      ctl('COPY TOKEN', '#deskCopyTok', 'copies the session token', 'local', 'signin'),
      ctl('SIGN OUT', '#deskSignOut', 'signOut', 'local', 'signin'),
      ctl('DIR', '#deskList', 'selectEntry, double-click openEntry', 'service', 'files'),
      ctl('UP', '#deskUp', 'goUp', 'service', 'files'),
      ctl('REFRESH', '#punchList', 'refreshList', 'service', 'files'),
      ctl('LOG', '#deskLogBtn', 'toggleLog', 'display', 'files'),
      ctl('OPEN', '#punchDoRetr', 'openEntry', 'service', 'view'),
      ctl('SAVE', '#deskSave', 'saveView', 'local', 'view'),
      ctl('EDIT', '#deskEdit', 'editView', 'local', 'view'),
      ctl('NEW SLIP', '#deskNew', 'newSlip', 'local', 'upload'),
      ctl('NAME', '#punchStor', 'upload file name', 'service', 'upload'),
      ctl('FROM DISK', '#deskPick and #deskFile', 'pickDiskFile', 'local', 'upload'),
      ctl('LOAD CRATE', '#punchDoStor', 'upload', 'service', 'upload'),
      ctl('CHANNEL', 'hotspot CHANNEL', 'setChannel', 'service', 'channel'),
      ctl('TYPE', 'hotspot TYPE', 'doType', 'service', 'channel'),
      ctl('CARGO LIFT', 'hotspot CARGO LIFT', 'commitLift', 'service', 'lift'),
      ctl('DATA RAIL', 'hotspot DATA RAIL', 'drag scrubs the transfer', 'display', 'lift'),
      ctl('HOLD', 'hotspot HOLD', 'drag the dial', 'display', 'hold'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  IPM: mod(
    'IPM',
    "Convert images and store results in FMM.",
    "Open SOURCE, choose a sample, then SEND.",
    [
      page('IPM', 'purpose', 'What this station is', [
        "Convert images: open SOURCE, configure a conversion, then SEND.",
        "IPM stores the result in FMM and opens it in DEVELOPING TRAY.",
      ], 'The Optical Sensor Array, the image-processing station'),
      page('IPM', 'scope', 'The scope dial', [
        "Turn SCOPE SELECT to set FIT IN to 256, 512, or 1K.",
        "SVG selects the built-in drawing; ZIP selects batch conversion.",
      ], 'SCOPE SELECT, the dial with stops for size, drawing and batch'),
      page('IPM', 'source', 'Where the picture comes from', [
        "Choose SAMPLE, UPLOAD, URL, or ZIP in SOURCE.",
        "Click PERISCOPE HEAD to cycle samples or the SOURCE rail to reopen the work order.",
      ], 'The periscope head and the SOURCE rail'),
      page('IPM', 'capture', 'Sending the request', [
        "Review REQUEST, then use SEND or CAPTURE PLUNGER.",
        "EXPOSE stays lit while running; failures reopen the work order with an error.",
      ], 'CAPTURE PLUNGER, the control that sends the request'),
      page('IPM', 'tray', 'The reply and the hold', [
        "Open DEVELOPING TRAY to inspect RESPONSE or SAVE the converted image.",
        "FMM HOLD fetches stored files by name; dragging the tray only changes the animation.",
      ], 'DEVELOPING TRAY and the OUTPUT size'),
      page('IPM', 'bench', 'The work order', [
        "Set FIT IN, FORMAT, and STORE AS; blank format uses PNG and blank name generates one.",
        "ZIP ignores these fields and uses service defaults.",
      ], 'The work order with SOURCE, OUTPUT and REQUEST'),
      mastPage('IPM'),
      refitPage('IPM'),
    ],
    [
      ctl('SCOPE SELECT', 'P.dial hotspot', 'applyScope', 'local', 'scope'),
      ctl('SOURCE', '#ipm-bench SOURCE', 'st.mode', 'local', 'source'),
      ctl('PERISCOPE HEAD', 'S.head hotspot', 'cycles the samples', 'local', 'source'),
      ctl('REQUEST', '#ipm-bench REQUEST', 'requestLines', 'display', 'capture'),
      ctl('SEND', '#ipm-bench SEND', 'pressCapture', 'service', 'capture'),
      ctl('CAPTURE PLUNGER', 'P.capture hotspot', 'pressCapture', 'service', 'capture'),
      ctl('DEVELOPING TRAY', 'P.tray hotspot', 'drag scrubs the develop', 'display', 'tray'),
      ctl('OUTPUT', 'hotspot OUTPUT', 'focusPanel output', 'display', 'tray'),
      ctl('RESPONSE', '#ipmPrint RESPONSE', 'renderResponse', 'display', 'tray'),
      ctl('FMM HOLD', '#ipmPrint FMM HOLD', 'fetchStored', 'service', 'tray'),
      ctl('FIT IN', '#ipm-bench FIT IN', 'st.width / st.height', 'local', 'bench'),
      ctl('FORMAT', '#ipm-bench FORMAT', 'st.format', 'local', 'bench'),
      ctl('STORE AS', '#ipm-bench STORE AS', 'st.outName', 'local', 'bench'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  KVS: mod(
    'KVS',
    "Read and write keys or run Lua scripts.",
    "Enter SET ship online on TELETYPE PLATEN and press Enter.",
    [
      page('KVS', 'purpose', 'What this station is', [
        "Query the key-value store through TELETYPE PLATEN.",
        "BANK DRAWERS edits keys; PUNCHED TAPE runs Lua scripts.",
      ], 'Core Memory Banks, the key-value station'),
      page('KVS', 'platen', 'Typing a command', [
        "Click TELETYPE PLATEN, enter SET ship online, then GET ship, pressing Enter after each.",
        "Quote values containing spaces; Up and Down recall commands.",
      ], 'TELETYPE PLATEN, the command line'),
      page('KVS', 'key', 'The send key', [
        "Press TELEGRAPH KEY or Enter to send the current command.",
        "Each command uses a separate, automatically authenticated connection.",
      ], 'TELEGRAPH KEY, the send key beside the platen'),
      page('KVS', 'ledger', 'Opening the ledger', [
        "Click BANK DRAWERS to list and edit keys.",
        "Switch between KEYS and SCRIPT TAPE; commands also print on the platen.",
      ], 'The bank ledger lifted off the drawers'),
      page('KVS', 'keys', 'Finding keys', [
        "Enter a match pattern such as crew.* and use SCAN or Enter.",
        "Click a result, or select it with arrow keys and Enter, to read it.",
      ], 'match, SCAN and the key list on the ledger'),
      page('KVS', 'value', 'Reading and storing', [
        "Use READ to fetch a key, SET or Ctrl+Enter to store it, and DEL to delete it.",
        "Optional ttl is in seconds; leave pass blank for the console password.",
      ], 'key, value, ttl, READ, DEL and SET on the ledger'),
      page('KVS', 'tape', 'The script tape', [
        "Open PUNCHED TAPE, enter lua, and use RUN or Ctrl+Enter.",
        "Space-separated keys and argv populate KEYS and ARGV.",
      ], 'SCRIPT TAPE on the ledger, opened from the reel'),
      page('KVS', 'lamps', 'The lamp bank', [
        "Click MEMORY BANK to ping the store.",
        "Its lamps show the last command state: READ, WRITE, EVAL, or FAULT.",
      ], 'MEMORY BANK, the lamp row'),
      mastPage('KVS'),
      refitPage('KVS'),
    ],
    [
      ctl('TELETYPE PLATEN', 'platen hotspot', 'Enter calls sendNow', 'service', 'platen'),
      ctl('TELEGRAPH KEY', 'P.key hotspot', 'sendNow', 'service', 'key'),
      ctl('BANK DRAWERS', 'drawers hotspot', 'openLedger and scanKeys', 'service', 'ledger'),
      ctl('Close', '#ledgerClose', 'closeLedger', 'local', 'ledger'),
      ctl('KEYS', '#tabKeys', 'showFace', 'local', 'ledger'),
      ctl('match', '#ledgerMatch', 'scan pattern', 'service', 'keys'),
      ctl('SCAN', '#ledgerScan', 'scanKeys', 'service', 'keys'),
      ctl('key list', '#ledgerKeys', 'readKey', 'service', 'keys'),
      ctl('key', '#ledgerKey', 'key name', 'service', 'value'),
      ctl('value', '#ledgerVal', 'value to store', 'service', 'value'),
      ctl('ttl', '#ledgerTtl', 'expiry seconds', 'service', 'value'),
      ctl('READ', '#ledgerRead', 'readKey', 'service', 'value'),
      ctl('DEL', '#ledgerDel', 'delKey', 'service', 'value'),
      ctl('SET', '#ledgerSet', 'setKey', 'service', 'value'),
      ctl('pass', '#ledgerPass', 'own password', 'service', 'value'),
      ctl('PUNCHED TAPE', 'P.reel hotspot', 'opens the script tape, drag spins', 'local', 'tape'),
      ctl('SCRIPT TAPE', '#tabTape', 'showFace', 'local', 'tape'),
      ctl('lua', '#ledgerScript', 'script', 'service', 'tape'),
      ctl('keys', '#ledgerSKeys', 'script keys', 'service', 'tape'),
      ctl('argv', '#ledgerSArgs', 'script arguments', 'service', 'tape'),
      ctl('RUN', '#ledgerRun', 'runScript', 'service', 'tape'),
      ctl('MEMORY BANK', 'P.lamps hotspot', 'pings the bank', 'service', 'lamps'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  LOG: mod(
    'LOG',
    "Read, search, and write logs.",
    "Open LOG SHEET, enter a message, then STAMP.",
    [
      page('LOG', 'purpose', 'What this station is', [
        "Read or add logs through LOG SHEET.",
        "Use SEARCH LENS to search; read results on LOG TAPE.",
      ], 'The Black Box, the flight-recorder station'),
      page('LOG', 'sheet', 'Tearing off the sheet', [
        "Open LOG SHEET for full log lines and message entry.",
        "It initially loads recent lines.",
      ], 'The log sheet lifted off the recorder'),
      page('LOG', 'download', 'Reading a file', [
        "Enter FILE and use OPEN to read it oldest-first.",
        "SAVE downloads the sheet; LOG TAPE shows the same lines newest-first.",
      ], 'FILE, OPEN and SAVE on the log sheet'),
      page('LOG', 'compose', 'Adding a line', [
        "Set level and source, enter message, then use STAMP or Enter.",
        "The sheet reloads that source with the new line at the end.",
      ], 'The stamp strip with the level button, source, message, and STAMP'),
      page('LOG', 'lens', 'Searching', [
        "Click SEARCH LENS, enter a query, and press Enter.",
        "Results appear on the tape and sheet; dragging the lens does not search.",
      ], 'SEARCH LENS over the log tape'),
      page('LOG', 'tape', 'The paper', [
        "Drag LOG TAPE to scroll through results.",
        "Use STAMP to add lines or SEARCH LENS to search.",
      ], 'LOG TAPE, the paper on the recorder'),
      page('LOG', 'source', 'Picking a file', [
        "Click SOURCE to cycle log files.",
        "The tape, sheet, and FILE field follow the selection.",
      ], 'SOURCE, the selector for a log file'),
      page('LOG', 'wipe', 'Deleting a log', [
        "Activate WIPE twice: the first activation arms it; the second deletes the selected log file.",
        "Read the result on the tape and sheet.",
      ], 'WIPE, the covered delete switch'),
      mastPage('LOG'),
      refitPage('LOG'),
    ],
    [
      ctl('LOG SHEET', 'tailHot hotspot', 'openSheet', 'local', 'sheet'),
      ctl('Close', '#sheetClose', 'closeSheet', 'local', 'sheet'),
      ctl('FILE', '#logDl', 'Enter calls commitDownload', 'service', 'download'),
      ctl('OPEN', '#sheetOpen', 'commitDownload', 'service', 'download'),
      ctl('SAVE', '#sheetSave', 'saveSheet', 'local', 'download'),
      ctl('level', '#logLevel', 'cycles INFO WARN ERROR', 'local', 'compose'),
      ctl('source', '#logSrc', 'sent by commitIngest', 'service', 'compose'),
      ctl('message', '#logMsg', 'Enter calls commitIngest', 'service', 'compose'),
      ctl('STAMP', '#logStamp', 'commitIngest', 'service', 'compose'),
      ctl('SEARCH LENS', 'P.lens hotspot and #logQ', 'click focuses #logQ, Enter commitSearch', 'service', 'lens'),
      ctl('LOG TAPE', 'P.tape hotspot', 'drag runs the paper', 'display', 'tape'),
      ctl('SOURCE', 'P.source hotspot', 'picks a log file', 'local', 'source'),
      ctl('WIPE', 'P.wipe hotspot', 'arm, then delete', 'service', 'wipe'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  MQB: mod(
    'MQB',
    "Publish and subscribe to MQTT topics.",
    "Subscribe to hull/temp in PATCH BAY, then PUBLISH from OPERATOR CARD.",
    [
      page('MQB', 'purpose', 'What this station is', [
        "Test MQTT messaging: subscribe through PATCH BAY.",
        "Open OPERATOR CARD to connect, publish, or configure a will.",
      ], 'The Drone Telemetry Bus, the message-bus station'),
      page('MQB', 'card', 'Lifting the operator card', [
        "Open OPERATOR CARD for LINE, SEND, WILL, and the traffic printout.",
        "Your entries remain when you close it.",
      ], 'The operator card lifted off the will card'),
      page('MQB', 'line', 'The line', [
        "Use CONNECT to open the line or HANG UP to disconnect normally.",
        "Blank pass uses the console password; keep alive sets the ping interval in seconds.",
      ], 'client, pass, the jack list, CONNECT and HANG UP on the LINE face'),
      page('MQB', 'send', 'Publishing', [
        "Set topic, payload, qos, and retain, then use PUBLISH or Ctrl+Enter.",
        "The topic follows the last jack you touched.",
      ], 'topic, payload, qos, retain and PUBLISH on the SEND face'),
      page('MQB', 'will', 'The will', [
        "Set topic and up to five lines on WILL before connecting.",
        "CONNECT arms the will with those values.",
      ], 'The WILL face of the operator card'),
      page('MQB', 'patch', 'Topics and the patch bay', [
        "Edit a topic line with Enter; click its PATCH BAY jack to toggle subscription.",
        "Drag a plugged cord off the bay to drop the connection and trigger the will.",
      ], 'Topic lines and the PATCH BAY'),
      page('MQB', 'retained', 'The retained switch', [
        "Click RETAINED MESSAGE to cycle live, retained, and clear, publishing the card’s payload on the focused topic.",
        "Clear removes the retained copy.",
      ], 'RETAINED MESSAGE, the publish switch'),
      page('MQB', 'traffic', 'Watching the bus', [
        "Click BUS TRAFFIC to open the traffic printout; dragging only animates the trace.",
        "Click KEEP ALIVE to ping immediately.",
      ], 'BUS TRAFFIC and KEEP ALIVE'),
      mastPage('MQB'),
      refitPage('MQB'),
    ],
    [
      ctl('OPERATOR CARD', 'willHot hotspot', 'openCard', 'local', 'card'),
      ctl('Close', '#cardClose', 'closeCard', 'local', 'card'),
      ctl('LINE', '#tabLine', 'showFace', 'local', 'card'),
      ctl('pass', '#cardPass', 'own password', 'service', 'line'),
      ctl('jack list', '#cardJacks', 'toggleJack', 'service', 'line'),
      ctl('keep alive', '#cardKa', 'ping interval', 'local', 'line'),
      ctl('CONNECT', '#cardConn', 'connect', 'service', 'line'),
      ctl('HANG UP', '#cardHang', 'hangup', 'service', 'line'),
      ctl('topic', '#cardTopic', 'publish topic', 'service', 'send'),
      ctl('payload', '#cardPayload', 'publish text', 'service', 'send'),
      ctl('qos', '#cardQos', 'QoS 0 or 1', 'service', 'send'),
      ctl('retain', '#cardRetain', 'keep a copy', 'service', 'send'),
      ctl('PUBLISH', '#cardPub', 'publishCard', 'service', 'send'),
      ctl('topic', '#cardWillTopic', 'will topic, sent on connect', 'service', 'will'),
      ctl('lines', '#cardWill', 'will text, sent on connect', 'service', 'will'),
      ctl('topic line', 'topic hotspots', 'focusTopic', 'local', 'patch'),
      ctl('PATCH BAY', 'P.patch hotspot', 'subscribe, unsubscribe, or drop', 'service', 'patch'),
      ctl('RETAINED MESSAGE', 'P.retained hotspot', 'publish live, kept, or clear', 'service', 'retained'),
      ctl('BUS TRAFFIC', 'P.scope hotspot', 'opens the traffic, drag runs the trace', 'display', 'traffic'),
      ctl('KEEP ALIVE', 'P.keepalive hotspot', 'sends a ping', 'service', 'traffic'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  MTA: mod(
    'MTA',
    "Send mail and inspect the relay queue.",
    "Open MESSAGE FORM, fill from and to, then POST.",
    [
      page('MTA', 'purpose', 'What this station is', [
        "Open MESSAGE FORM to send mail through the relay.",
        "Inspect queued messages in QUEUE PIGEONHOLES.",
      ], 'The Subspace Comms Relay, the mail station'),
      page('MTA', 'form', 'Tearing off a form', [
        "Open MESSAGE FORM, enter your message, and use POST.",
        "The form keeps your entries for another post.",
      ], 'The message form lifted off the pad'),
      page('MTA', 'envelope', 'Writing the message', [
        "Fill from, to, subj, and body; Enter advances through single-line fields.",
        "RSET clears the envelope.",
      ], 'The envelope on the message form: from, to, subj, and body'),
      page('MTA', 'auth', 'The auth stamp', [
        "Fill user and pass and choose mech (PLAIN or LOGIN) to authenticate the next POST.",
        "Leave credentials blank to send without authentication.",
      ], 'AUTH STAMP on the message form: user, pass, and mech'),
      page('MTA', 'post', 'Posting', [
        "Use POST or Ctrl+Enter to send.",
        "Inspect the SMTP transcript and status; accepted messages appear in QUEUE PIGEONHOLES.",
      ], 'POST, RSET, and the printout on the message form'),
      page('MTA', 'tls', 'Encryption', [
        "Check STARTTLS or turn STARTTLS SCRAMBLER one notch to request encryption on the next POST.",
        "A successful post resets this setting.",
      ], 'The STARTTLS SCRAMBLER'),
      page('MTA', 'queue', 'Reading the queue', [
        "Click an envelope in QUEUE PIGEONHOLES to read its stored message.",
        "The rack shows the newest ten; click an empty slot for the full list.",
      ], 'QUEUE PIGEONHOLES, the relay\'s queue'),
      page('MTA', 'theatre', 'The handset and the tube', [
        "Click PNEUMATIC TUBE to refresh the queue.",
        "Cradling COMMS HANDSET posts the form, or clears the envelope if the form is empty.",
      ], 'COMMS HANDSET and the PNEUMATIC TUBE'),
      mastPage('MTA'),
      refitPage('MTA'),
    ],
    [
      ctl('MESSAGE FORM', 'padHot hotspot', 'openForm', 'local', 'form'),
      ctl('Close', '#formClose', 'closeForm', 'local', 'form'),
      ctl('from', '#mtaFrom', 'envelope sender', 'service', 'envelope'),
      ctl('to', '#mtaTo', 'envelope recipient', 'service', 'envelope'),
      ctl('subj', '#mtaSubj', 'subject', 'service', 'envelope'),
      ctl('body', '#mtaBody', 'message body', 'service', 'envelope'),
      ctl('RSET', '#formRset', 'rsetEnvelope', 'local', 'envelope'),
      ctl('user', '#mtaUser', 'auth user', 'service', 'auth'),
      ctl('pass', '#mtaPass', 'auth password', 'service', 'auth'),
      ctl('mech', '#mtaMech', 'PLAIN or LOGIN', 'service', 'auth'),
      ctl('POST', '#formPost', 'commitSend', 'service', 'post'),
      ctl('STARTTLS', '#mtaStarttls', 'arms encryption', 'local', 'tls'),
      ctl('STARTTLS SCRAMBLER', 'P.scrambler hotspot', 'throw', 'local', 'tls'),
      ctl('QUEUE PIGEONHOLES', 'P.queue hotspot', 'printMessage or printQueue', 'service', 'queue'),
      ctl('COMMS HANDSET', 'P.handset hotspot', 'lift, or cradle to post', 'service', 'theatre'),
      ctl('PNEUMATIC TUBE', 'P.capsule hotspot', 'pullQueue', 'service', 'theatre'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  OTA: mod(
    'OTA',
    "Publish packages and check device versions.",
    "Open the PUBLISH cartridge, choose a module, then PUBLISH on the card.",
    [
      page('OTA', 'purpose', 'What this station is', [
        "Publish software updates for fmm, ipm, or log through PUBLISH.",
        "Use the boards to check stored versions and device reports.",
      ], 'The Fleet Replicator Grid, the update station'),
      page('OTA', 'card', 'The cartridge card', [
        "Click the PUBLISH cartridge to open its card.",
        "LATEST and FLEET read status; PUBLISH on the card sends an update.",
      ], 'The cartridge card lifted off the cartridge'),
      page('OTA', 'cartridge', 'Filling in the cartridge', [
        "Choose module and version, then use PUBLISH or Enter in version.",
        "Leave version blank to use the suggested next version.",
      ], 'module, version, and PUBLISH on the cartridge card'),
      page('OTA', 'publish', 'Seating a cartridge', [
        "Drag PUBLISH up, then push it down until it seats to publish the card’s values.",
        "The card opens with the result.",
      ], 'PUBLISH, the cartridge lift'),
      page('OTA', 'readings', 'Reading the grid', [
        "Use LATEST for the selected module’s newest package, or FLEET for all packages and registered devices.",
        "Changing module also fetches its latest package.",
      ], 'LATEST, FLEET, and the printout on the cartridge card'),
      page('OTA', 'propagate', 'Sending it down the rack', [
        "Drag PROPAGATE to replay the update animation.",
        "It runs automatically after publishing and sends no request.",
      ], 'PROPAGATE, the chevron spine'),
      page('OTA', 'fleet', 'Who has which version', [
        "Click FLEET VERSIONS to refresh packages and device reports.",
        "Boards show stored versions; green means a device reports that version, amber means none does.",
      ], 'FLEET VERSIONS, the boards and beacons'),
      page('OTA', 'poll', 'Checking for an update', [
        "Drag POLL INTERVAL and release to fetch the selected module’s latest package.",
        "It does not change a device’s polling interval.",
      ], 'POLL INTERVAL, the needle for update checks'),
      mastPage('OTA'),
      refitPage('OTA'),
    ],
    [
      ctl('PUBLISH', 'P.cartridge hotspot', 'click: openCard; seat: publish', 'service', 'publish'),
      ctl('Close', '#cardClose', 'closeCard', 'local', 'card'),
      ctl('module', '#otaModule', 'fmm, ipm, or log', 'service', 'cartridge'),
      ctl('version', '#otaVersion', 'version to publish', 'service', 'cartridge'),
      ctl('PUBLISH on the card', '#cardPublish', 'publish', 'service', 'cartridge'),
      ctl('LATEST', '#cardLatest', 'pullLatest', 'service', 'readings'),
      ctl('FLEET', '#cardFleet', 'pullFleet', 'service', 'readings'),
      ctl('PROPAGATE', 'P.propagate hotspot', 'runs the pulse down the spine', 'display', 'propagate'),
      ctl('FLEET VERSIONS', 'P.fleet hotspot', 'pullFleet', 'service', 'fleet'),
      ctl('POLL INTERVAL', 'P.poll hotspot', 'pointerup calls pullLatest', 'service', 'poll'),
      ...mastControls(),
      ...refitControls(),
    ],
    [devbar],
  ),

  PKT: mod(
    'PKT',
    "Attack the A.L.I.E.N. ships with exploits you edit on disk, tested locally or graded remotely.",
    "Select a ship, edit its exploit.py on disk, then Run against local ship.",
    [
      page('PKT', 'purpose', 'What this station is', [
        "Exploit the A.L.I.E.N. ships one at a time: pick a ship, edit its exploit.py on disk, then test it locally or submit it for grading.",
        "The ships are Navcomputer, Cargo Manifests, Reactor Core, and Docking Bay; this station has no refit port.",
      ], 'The Signal Harpoon station'),
      page('PKT', 'scoring', 'The fleet-scoring panel', [
        "Edit aliens/<ship>/exploit.py on disk; the panel shows the path, and the connect-and-print scaffold is already there.",
        "Test locally runs it against a local ship and does not score; Submit to remote grades it in the cloud, where it must retrieve and print a fresh flag.",
      ], 'The A.L.I.E.N. fleet-scoring panel'),
      page('PKT', 'aim', 'Aiming at a ship', [
        "Drag TARGET BEARING to aim at and select the nearest ship.",
        "Use PAYLOAD SELECT to step the target to the next ship.",
      ], 'TARGET BEARING and PAYLOAD SELECT'),
      page('PKT', 'fire', 'Charging, arming, and firing', [
        "With a ship locked and the bank spooled by CHARGE, ARM then FIRE launches the run, the same as the panel button.",
        "ARM needs a lock and a spooled bank; activate ARM again to make it safe.",
      ], 'CHARGE, ARM, and FIRE'),
      page('PKT', 'return', 'The result', [
        "IMPACT shows the verdict (a hit on a local flag or a remote boarding); click RETURN LINE to scroll the reply.",
        "Click IMPACT to acknowledge the lamps.",
      ], 'RETURN LINE and IMPACT'),
      mastPage('PKT'),
    ],
    [
      ctl('Test locally / Submit to remote', '.as-mode', 'chooses local test or remote grading', 'service', 'scoring'),
      ctl('Ship', '.as-target', 'picks one released ship', 'service', 'scoring'),
      ctl('Run against local ship / Submit for scoring', '#alienSubmit .ac-act', 'runs locally or submits for grading', 'service', 'scoring'),
      ctl('TARGET BEARING', 'P.target hotspot', 'aims at a ship and selects it', 'local', 'aim'),
      ctl('PAYLOAD SELECT', 'P.payload hotspot', 'steps to the next ship', 'local', 'aim'),
      ctl('CHARGE', 'P.charge hotspot', 'spools the bank', 'local', 'fire'),
      ctl('ARM', 'P.arm hotspot', 'throws the master arm', 'local', 'fire'),
      ctl('FIRE', 'P.fire hotspot', 'launches the selected run', 'service', 'fire'),
      ctl('RETURN LINE', 'P.catch hotspot', 'scrolls the printout', 'display', 'return'),
      ctl('IMPACT', 'P.verdict hotspot', 'acknowledges the lamps', 'display', 'return'),
      ...pktMastControls(),
    ],
    [{
      name: 'preset attack drum',
      reason: 'The payload drum steps the target ship. It is not a list of built-in attacks.',
    }, {
      name: 'refit port',
      reason: 'module.js mounts the status mast and does not call mountRefit. There is no rebuild button.',
    }],
  ),
};

function ctl(name, selector, handler, kind, pageId) {
  return { name, selector, handler, kind, page: pageId };
}

function mastPage(code) {
  if (code === 'PKT') {
    return page(code, 'mast', 'The status mast', [
      'The status mast is the light on this station. It stays only the light until you point and move onto it, click it, or press Enter or Space. Click pins the reading. The reading is read-only.',
      'This mast reads the fleet tally and the arm lamp. It does not show power buttons.',
      'This station has no refit port. There is no rebuild button here. The mast does not rebuild the station. Click again, Escape, or leaving the station clears a pinned reading.',
    ], 'The status mast on the Signal Harpoon');
  }
  return page(code, 'mast', 'The status mast', [
    "Hover over the status mast, or focus it and press Enter or Space, for read-only status.",
    "Click to pin and scroll solved items; power controls are in REFIT PORT.",
  ], 'The status mast on this station');
}

function refitPage(code) {
  return page(code, 'refit', 'The refit port', [
    "Open REFIT PORT for Start, Stop, Restart (confirmation required), or Rebuild & restart after source edits.",
    "Rebuilding replaces the local service and drops data stored only inside the container; it does not submit for grading.",
  ], 'The refit panel with START, STOP, RESTART, MODULE, SERVICE, CHANGES, Rebuild & restart, and Close');
}

function mastControls() {
  return [
    ctl('status mast', 'TELLTALE MAST hotspot', 'point and move, click, or Enter or Space', 'display', 'mast'),
  ];
}

function pktMastControls() {
  return [
    ctl('status mast', 'TELLTALE MAST hotspot', 'point and move, click, or Enter or Space', 'display', 'mast'),
  ];
}

function refitControls() {
  return [
    ctl('REFIT PORT', 'hotspot REFIT PORT', 'click toggles the panel', 'local', 'refit'),
    ctl('MODULE', '#refit MODULE', 'station name', 'display', 'refit'),
    ctl('SERVICE', '#refit SERVICE', 'service name', 'display', 'refit'),
    ctl('CHANGES', '#refit CHANGES', 'changes since the last build', 'display', 'refit'),
    ctl('BUILT', '#refit BUILT', 'labelled sample build line', 'display', 'refit'),
    ctl('START', 'refit Start', 'powers the service on unless it is already on', 'service', 'refit'),
    ctl('STOP', 'refit Stop', 'powers the service off when it is on', 'service', 'refit'),
    ctl('RESTART', 'refit Restart', 'asks, then cycles the service', 'service', 'refit'),
    ctl('Rebuild & restart', '#refit button.go', 'startRebuild', 'service', 'refit'),
    ctl('Close', '#refit Close', 'hides the panel', 'local', 'refit'),
  ];
}
