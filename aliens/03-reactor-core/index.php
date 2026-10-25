<?php


class DiagnosticLog {
    public $label = "idle";
    public $lastReading = 0;
}

class MaintenanceReport {
    public $source = "";
    public $buffer = null;

    public function __destruct() {
        if ($this->buffer === null && $this->source !== "") {
            $this->buffer = @file_get_contents($this->source);
            echo "<pre class='report'>MAINTENANCE REPORT ["
               . htmlspecialchars($this->source) . "]\n\n"
               . htmlspecialchars($this->buffer) . "</pre>";
        }
    }
}

$state = null;
if (!empty($_COOKIE['reactor_session'])) {
    $blob = base64_decode($_COOKIE['reactor_session'], true);
    if ($blob !== false) {
        $state = @unserialize($blob);
    }
}

if (!($state instanceof DiagnosticLog)) {
    $state = new DiagnosticLog();
}

if (isset($_GET['diag'])) {
    $state->label = substr((string)$_GET['diag'], 0, 40);
    $state->lastReading = random_int(1000, 9999);
    setcookie('reactor_session', base64_encode(serialize($state)), [
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
}
?>
<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A.L.I.E.N. Reactor Core</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; min-height:100vh; background:#0d0503; color:#ffb38a;
    font-family:"Courier New",monospace; display:flex; align-items:center;
    justify-content:center; }
  .core { width:min(760px,92vw); border:1px solid #7a3a1f; border-radius:10px;
    padding:28px 30px; background:#130806; box-shadow:0 0 50px rgba(255,90,30,.15); }
  h1 { font-size:20px; letter-spacing:3px; margin:0 0 4px; }
  .sub { color:#b0603c; font-size:12px; margin-bottom:22px; }
  .gauge { font-size:13px; color:#d48a5f; }
  label { display:block; font-size:12px; color:#d4855f; margin:16px 0 6px; }
  input[type=text]{ width:100%; box-sizing:border-box; padding:10px 12px;
    background:#0a0402; color:#ffd9c2; border:1px solid #7a3a1f; border-radius:6px;
    font-family:inherit; font-size:14px; }
  button{ margin-top:14px; padding:10px 20px; background:#4d221a; color:#ffd9c2;
    border:1px solid #ce6a3f; border-radius:6px; font-family:inherit; font-size:14px;
    cursor:pointer; letter-spacing:1px; }
  button:hover{ background:#663022; }
  .report{ margin-top:22px; padding:14px; background:#0a0402; border:1px solid #50241c;
    border-radius:6px; white-space:pre-wrap; color:#ffe6d9; overflow-x:auto; }
</style></head>
<body><div class="core">
  <h1>&#9762; A.L.I.E.N. REACTOR CORE</h1>
  <div class="sub">CONTAINMENT CONSOLE v7.7 // clearance: ENGINEER</div>
  <p class="gauge">Last diagnostic: <b><?= htmlspecialchars($state->label) ?></b>
     &nbsp;|&nbsp; reading: <b><?= (int)$state->lastReading ?></b> mSv</p>
  <form method="GET" action="/">
    <label for="diag">RUN CONTAINMENT DIAGNOSTIC</label>
    <input type="text" id="diag" name="diag" placeholder="e.g. coolant-loop"
           autocomplete="off">
    <button type="submit">RUN</button>
  </form>
  <p style="font-size:12px;color:#8a4a30;margin-top:18px;">
    Session state is preserved in your <code>reactor_session</code> cookie.</p>
</div>
<?php
?>
</body></html>
