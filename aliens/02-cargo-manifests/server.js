
const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = 8080;
const MANIFEST_DIR = path.join(__dirname, "manifests");

const SHELL = (body) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A.L.I.E.N. Cargo Manifests</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; min-height:100vh; background:#05060d; color:#c9b8ff;
    font-family:"Courier New",monospace; display:flex; align-items:center;
    justify-content:center; }
  .panel { width:min(760px,92vw); border:1px solid #4a2f7a; border-radius:10px;
    padding:28px 30px; background:#0a0713; box-shadow:0 0 40px rgba(150,80,255,.15); }
  h1 { font-size:20px; letter-spacing:3px; margin:0 0 4px; }
  .sub { color:#7d5fb0; font-size:12px; margin-bottom:22px; }
  label { display:block; font-size:12px; color:#a48fd4; margin-bottom:6px; }
  input[type=text] { width:100%; box-sizing:border-box; padding:10px 12px;
    background:#050309; color:#d9c9ff; border:1px solid #4a2f7a; border-radius:6px;
    font-family:inherit; font-size:14px; }
  button { margin-top:14px; padding:10px 20px; background:#2c1a4d; color:#d9c9ff;
    border:1px solid #7d4fce; border-radius:6px; font-family:inherit; font-size:14px;
    cursor:pointer; letter-spacing:1px; }
  button:hover { background:#3a2266; }
  ul { font-size:13px; color:#9d86cc; }
  a { color:#c9a8ff; }
  .warn { color:#ff8ab0; font-size:12px; }
  pre { margin-top:22px; padding:14px; background:#050309; border:1px solid #2f1c50;
    border-radius:6px; white-space:pre-wrap; color:#e6dcff; min-height:40px;
    overflow-x:auto; }
</style></head>
<body><div class="panel">${body}</div></body></html>`;

function terminal(body) {
  return SHELL(`
  <h1>&#128230; A.L.I.E.N. CARGO MANIFESTS</h1>
  <div class="sub">HOLD INVENTORY SYSTEM v4.1 // access: CREW</div>
  <form method="GET" action="/manifest">
    <label for="file">MANIFEST FILE TO RETRIEVE</label>
    <input type="text" id="file" name="file" value="bay-1.txt" autocomplete="off">
    <button type="submit">RETRIEVE</button>
  </form>
  <p style="font-size:12px;color:#7d5fb0;margin-top:18px;">Available manifests:</p>
  <ul>
    <li><a href="/manifest?file=bay-1.txt">bay-1.txt</a></li>
    <li><a href="/manifest?file=bay-2.txt">bay-2.txt</a></li>
    <li><a href="/manifest?file=quarantine.txt">quarantine.txt</a></li>
  </ul>
  ${body}`);
}

function sanitize(name) {
  return name.split("../").join("");
}

function send(res, code, html, extraHeaders = {}) {
  res.writeHead(code, { "Content-Type": "text/html", ...extraHeaders });
  res.end(html);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === "/") {
    return send(res, 200, terminal(""));
  }

  if (url.pathname === "/manifest") {
    const raw = url.searchParams.get("file") || "";
    const cleaned = sanitize(raw);

    const target = path.join(MANIFEST_DIR, cleaned);

    fs.readFile(target, "utf8", (err, data) => {
      if (err) {
        return send(res, 404,
          terminal(`<pre>*** MANIFEST NOT FOUND ***\nrequested: ${cleaned}</pre>`));
      }
      send(res, 200, terminal(`<pre>${data.replace(/</g, "&lt;")}</pre>`));
    });
    return;
  }

  send(res, 404, terminal("<pre>404</pre>"));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Cargo manifest terminal online on :${PORT}`);
});
