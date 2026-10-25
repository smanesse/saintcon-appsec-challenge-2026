# Log Aggregation Module — API Reference

LOG (`log`) is the spacecraft's **flight recorder / log aggregation hub**. Other
modules ship log lines to it; operators search, download and review those logs
through a small HTTP API and a server-rendered dashboard. It is a natural hub —
everything on the ship talks to it — which is exactly what makes it a
high-value target.

> ⚠️ This service contains **intentional, deliberate vulnerabilities** for
> teaching. Do not deploy it on any network you don't fully control. This
> document describes the *functional* API so clients (and tests) can drive it.

---

## Connection

| Property | Value |
|----------|-------|
| Transport | HTTP/1.1 (http4s / Cats Effect, Scala 2.13) |
| Default bind | `0.0.0.0:8080` |
| Request bodies | `application/json` or `application/x-www-form-urlencoded` (ingest) |
| Response bodies | JSON, raw `text/plain` for downloads, `text/html` for the dashboard |
| Concurrency | Async, one shared logs root on local disk |

All configuration is overridable via environment variables with the `LOG_`
prefix (plus `SERVER_PORT`, which wins for the port):

| Variable | Meaning | Default |
|----------|---------|---------|
| `SERVER_PORT` / `LOG_PORT` | listen port | `8080` |
| `LOG_ROOT` | directory logs are stored under | `/home/ctf/log/logs` |
| `LOG_SECRET` | path of the rotating secret/flag | `/home/ctf/log/secret/flag.txt` |
| `LOG_OP_TOKEN` | operator token for privileged actions (wipe) | `operator-secret` |
| `LOG_DASHBOARD_TAIL` | how many recent lines the dashboard renders | `100` |

Logs are stored one file per source, `<source>.log`, under the logs root. A
stored line looks like `2026-07-18T12:00:00Z [INFO] <message>`.

---

## Endpoints

### `POST /ingest`
Accept a single log record from a module and append it to that source's file.

- **Body:** JSON `{"source": "...", "level": "...", "message": "..."}` **or**
  form-encoded `source=...&level=...&message=...`.
  - `message` — **required**. The log text.
  - `source` — optional, default `misc`. Names the target file (`<source>.log`);
    restricted to `[A-Za-z0-9_.-]`.
  - `level` — optional, default `INFO`.

**Success — `200 OK`:**
```json
{ "stored": true, "source": "nav", "level": "INFO", "message": "engine start" }
```

**Missing message — `400 Bad Request`:** `{ "error": "message is required" }`.

### `GET /search?q=...&source=...`
Search stored log lines and return the matching lines.

- **Params:** `q` (**required**) the query; `source` (optional) restricts the
  search to a single source file, otherwise all sources are searched.

**Success — `200 OK`:**
```json
{ "q": "engine", "source": "nav", "count": 1, "matches": ["2026-... [INFO] engine start"] }
```

**Missing `q` — `400 Bad Request`** (query-parameter decoding failure).

### `GET /logs/{name}`
Download a stored log file as raw text.

- **Success — `200 OK`:** raw file bytes (`Content-Type: text/plain`).
- **Not found — `404 Not Found`:** `{ "error": "no such log: <name>" }`.

### `GET /dashboard`
Server-rendered HTML page showing the most recent log lines across all sources.

- **Reply — `200 OK`:** `text/html`.

### `DELETE /logs/{name}`
Delete (wipe) a stored log file. Intended to be an operator-only action; supply
the operator token in the `X-Operator-Token` header.

- **Success — `200 OK`:** `{ "deleted": true, "name": "nav.log" }`
  (`"deleted": false` if the file did not exist).

### `GET /health`
Liveness probe.

- **Reply — `200 OK`:** `ok`

---

## Status code summary

| Code | Meaning in this service |
|------|--------------------------|
| `200` | Success (ingested / search done / file returned / dashboard / wiped / healthy) |
| `400` | Bad request — missing `message` on ingest, or missing `q` on search |
| `404` | Requested log file does not exist |
| `405` | Method not allowed for the route |

---

## Minimal client session

```
# health
$ curl -s http://localhost:8080/health
ok

# ingest a record (JSON)
$ curl -s -H 'Content-Type: application/json' \
       -d '{"source":"nav","level":"INFO","message":"engine start"}' \
       http://localhost:8080/ingest
{"stored":true,"source":"nav","level":"INFO","message":"engine start"}

# ingest a record (form)
$ curl -s -d 'source=nav&message=course corrected' http://localhost:8080/ingest

# search
$ curl -s 'http://localhost:8080/search?q=engine&source=nav'
{"q":"engine","source":"nav","count":1,"matches":["2026-... [INFO] engine start"]}

# download the raw file
$ curl -s http://localhost:8080/logs/nav.log

# view the dashboard
$ curl -s http://localhost:8080/dashboard

# wipe a log (operator token)
$ curl -s -X DELETE -H 'X-Operator-Token: operator-secret' \
       http://localhost:8080/logs/nav.log
{"deleted":true,"name":"nav.log"}
```
