#!/usr/bin/env python3
import os
import subprocess

from flask import Flask, request, render_template_string

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A.L.I.E.N. Navcomputer</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; min-height: 100vh; background: #04070d;
    color: #7dffce; font-family: "Courier New", monospace;
    display: flex; align-items: center; justify-content: center;
  }
  .console {
    width: min(760px, 92vw); border: 1px solid #1d5f4a;
    border-radius: 10px; padding: 28px 30px; background: #060b13;
    box-shadow: 0 0 40px rgba(45, 255, 190, 0.12);
  }
  h1 { font-size: 20px; letter-spacing: 3px; margin: 0 0 4px; }
  .sub { color: #3c8f77; font-size: 12px; margin-bottom: 22px; }
  label { display: block; font-size: 12px; color: #59c9a4; margin-bottom: 6px; }
  input[type=text] {
    width: 100%; box-sizing: border-box; padding: 10px 12px;
    background: #020509; color: #9dffdc; border: 1px solid #1d5f4a;
    border-radius: 6px; font-family: inherit; font-size: 14px;
  }
  button {
    margin-top: 14px; padding: 10px 20px; background: #0d3a2c;
    color: #9dffdc; border: 1px solid #2fae86; border-radius: 6px;
    font-family: inherit; font-size: 14px; cursor: pointer; letter-spacing: 1px;
  }
  button:hover { background: #12513c; }
  pre {
    margin-top: 22px; padding: 14px; background: #020509;
    border: 1px solid #123c30; border-radius: 6px; white-space: pre-wrap;
    color: #b7ffe6; min-height: 40px; overflow-x: auto;
  }
  .blip { color: #2fae86; }
</style>
</head>
<body>
  <div class="console">
    <h1>&#128126; A.L.I.E.N. NAVCOMPUTER</h1>
    <div class="sub">SECTOR SCANNER v2.3 // pilot clearance: <span class="blip">GREEN</span></div>
    <form method="POST" action="/scan">
      <label for="coords">ENTER NAV BEACON / STAR COORDINATES TO PING</label>
      <input type="text" id="coords" name="coords" value="{{ coords }}"
             placeholder="e.g. 127.0.0.1" autocomplete="off">
      <button type="submit">INITIATE SCAN</button>
    </form>
    {% if output is not none %}
    <pre>{{ output }}</pre>
    {% endif %}
  </div>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(PAGE, output=None, coords="127.0.0.1")


@app.route("/scan", methods=["POST"])
def scan():
    coords = request.form.get("coords", "")

    cmd = "ping -c 1 -W 1 " + coords
    try:
        output = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        result = output.stdout + output.stderr
    except subprocess.TimeoutExpired:
        result = "*** SCAN TIMED OUT — beacon unresponsive ***"

    if not result.strip():
        result = "*** NO SIGNAL RETURNED ***"

    return render_template_string(PAGE, output=result, coords=coords)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
