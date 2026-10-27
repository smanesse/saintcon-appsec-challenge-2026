# SAINTCON AppSec Challenge — repo guide

Collection of small, self-contained, **intentionally-vulnerable** services for
a security/CTF course. Each module speaks a real protocol and does something
genuinely useful. Full design principles, the standard module layout, and the
submission contract live in `README.md` — read it before touching module
internals or adding a new one; don't duplicate its content here.

## Modules

| Dir | Acronym | Domain |
|---|---|---|
| `file-management-module/` | FMM | FTP-like file server (C++) |
| `image-processing-module/` | IPM | HTTP image conversion via ImageMagick (Java/Spring), client of FMM |
| `dns-module/` | DNSM | Authoritative DNS server (C) |
| `keystore-module/` | KVS | Redis-protocol (RESP) key-value store (Go) |
| `log-module/` | LOG | Log ingestion + dashboard (Scala/http4s) |
| `ota-module/` | OTA | Fleet-update server + agent, client of FMM/IPM/log (Go) |
| `mqtt-module/` | MQB | MQTT 3.1.1 broker (Python asyncio) |
| `mail-module/` | MTA | SMTP outbound relay (Node.js) |
| `bridge/` | — | Operator console + scoring client (Python stdlib); **not vulnerable** |

The first 8 are the intentionally-vulnerable, scored modules. `bridge/` is a
first-class module in the same layout (`README.md`, `unit_tests/`,
`Dockerfile`) and a service in the primary stack — but it is the **console**,
not a target.

Each module directory is self-contained: `README.md` (functional protocol
reference, no spoilers) and `unit_tests/` (functional tests only). Read the
specific module's own docs before working in it — don't assume this table is
more than a map.

The **primary stack** is `bridge/fleet-compose.yml`: all 8 scored modules plus
the `bridge` console. `bridge/fleet-up.sh` starts only the console by default;
modules start from its START buttons or by name (`fleet-up.sh fmm dnsm`, `day2`,
`all`) (published on 127.0.0.1
for the demo — never on an untrusted network). The console packages a whole-repo
snapshot and submits it to a third-party scoring harness over HTTP via
`POST /api/submit` (see `bridge/harness.py`; configured with `HARNESS_URL`).

One supporting app, not a module itself:
- `metadata-service/` — benign internal-only HTTP service the fleet keeps on
  its trusted network. It serves per-deployment secrets from env and is not
  vulnerable itself. See its README.

## Ground rules that apply everywhere

- Nothing here is safe to expose off a private Docker network — never publish
  a module port to the host in compose files.
- `unit_tests/` are functional tests only — they prove the intended behaviour
  works and say nothing about the planted weaknesses.
- Any flag or credential a deployment relies on is runtime-generated per
  deployment (see `generate-secrets.sh`), never a value hardcoded in the
  repo/image.
- Adding a brand-new module: use the `new-module` skill rather than
  hand-rolling the scaffold.

## Where to look for more

- `README.md` — design principles, standard layout, per-piece conventions, and
  the submission contract.
- `<module>/README.md` — everything module-specific (functional reference).
- `generate-secrets.sh` — how runtime secrets get minted per deployment.
