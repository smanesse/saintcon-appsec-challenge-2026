# Bridge Console — USS AUDITOR-7

A **spaceship bridge console** frontend for the SAINTCON AppSec Challenge. Each
of the repo's 8 modules is shown as a ship **subsystem**. The console
auto-detects which subsystems are actually running and gives the operator a
real, working way to interact with each live one **over its actual protocol** —
no simulation, no fictional combat. Offline subsystems are shown as offline.

> Unsigned visitors get the sign-in page at `/`. After sign-in, `/` is the cockpit.

The console is a first-class service in the primary fleet stack
(`fleet-compose.yml`). By default only the console starts; you bring up the
modules you want, either from the console or from the shell. `start.sh` and a
bare `python3 server.py` remain for running *just* the console.

## Bring the fleet up

From the repo root, `./start.sh` / `./stop.sh` are the friendly entry points
(thin wrappers over `bridge/fleet-up.sh` / `bridge/fleet-down.sh`):

```bash
./start.sh                 # console only (fast). Start modules from the console.
./start.sh fmm dnsm        # console + those modules (and their dependencies)
./start.sh day2            # console + a release day's modules (cumulative)
./start.sh all             # console + every module
./start.sh --build-only all  # pre-build images without starting anything
./stop.sh                  # stop all of it
```

The underlying scripts live at `bridge/fleet-up.sh` / `bridge/fleet-down.sh`
and take the same arguments. If you prefer raw compose, run it from `bridge/`
(where `fleet-compose.yml` lives) so the console can still manage the fleet:
`cd bridge && docker compose -f fleet-compose.yml up --build -d bridge`.

Then open **http://127.0.0.1:8787**. With no bridge session, `/` is the
sign-in page (`cockpit-ui/live3d/auth/index.html`, served at `/` — the address
does not contain `live3d`). A session already on the bridge gets the cockpit
(`cockpit-ui/live3d/index.html`) at that same address. Signing out returns to
sign-in. Module names are `fmm dnsm kvs ipm log
mqb ota mail`. Dependencies come up automatically: IPM brings FMM, OTA brings
DNSM and FMM, MAIL brings DNSM, and DNSM brings the internal metadata service.

**Builds take a while.** Each module builds from source the first time it
starts: expect several minutes per module and well over 10 minutes for the
whole fleet on a typical laptop. IPM (compiles ImageMagick) and LOG (Scala/sbt)
are the slowest. Later starts reuse the cached images and take seconds. To get
the waiting out of the way, run `./start.sh --build-only all` while
you read the module docs.

**Starting from the console.** Each subsystem card has power buttons:

- **START** creates the container (and its dependencies), building the image on
  first use. The button stays busy until the build finishes.
- **REBUILD** rebuilds the image from your edited source and recreates just that
  container. Use it after patching a module to test your fix locally.
- **RESTART** / **STOP** act on the running container. A loopback browser on
  the port this console is actually serving can use them. A public origin cannot.

The console uses the same per-deployment secrets (`secrets/fleet.env`) as
`fleet-up.sh`, so a module started either way is configured identically.

- Port `8787` (`BRIDGE_PORT`), host `0.0.0.0` in the container / `127.0.0.1` on a
  host run (`BRIDGE_HOST`).
- Live services: in `fleet-compose.yml` the console runs with
  `BRIDGE_LIVE_MODE=compose` and dials each module by service name on its
  container port over the compose network (works the same on Linux, macOS and
  Windows; ports stay bound to `127.0.0.1`). On a host run it dials
  `BRIDGE_LIVE_HOST` (default `127.0.0.1`) on the published ports.
- Requirements: **Python 3 stdlib only** — no `pip install`, no Node, no build.

### Just the console

```bash
./bridge/start.sh          # build + start only the `bridge` service from fleet-compose.yml
./bridge/start.sh logs     # follow the console logs
./bridge/start.sh down     # stop + remove only the console container
# or, with no Docker at all:  cd bridge && python3 server.py
```

The modules are released over **3 days**. Each day's modules are clients of
earlier days, never the reverse, so a new drop needs no changes to
already-released modules:

| Selector | Modules |
|---|---|
| `day1` | FMM, DNSM, KVS |
| `day2` | + IPM, LOG, MQB |
| `day3` / `all` | + OTA, MAIL |

Under the hood the modules carry docker compose **profiles** (`day1`/`day2`/`day3`);
the console has none, so a bare `docker compose -f bridge/fleet-compose.yml up`
starts only the console. Both `fleet-up.sh` and the console enable every profile
and name the services to start.
JVM-based services (IPM, LOG) take ~30–60 s to answer after starting; then click
**RESCAN FLEET** in the console. Host port map (host → container):

| Day | Subsystem | Module | Host port(s) |
|---|---|---|---|
| 1 | FMM  Cargo Bay / Data Vault | file-management-module | 2121 |
| 1 | DNSM Nav Beacon | dns-module | 8053 (tcp+udp), admin 8054 |
| 1 | KVS  Core Memory Banks | keystore-module | 6379 |
| 2 | IPM  Optical Sensor Array | image-processing-module | 8080 |
| 2 | LOG  Black Box Recorder | log-module | 8085 |
| 2 | MQB  Drone Telemetry Bus | mqtt-module | 1883, admin 8082 |
| 3 | OTA  Fleet Replicator Grid | ota-module | 8090 |
| 3 | MAIL Subspace Comms Relay | mail-module | 2525, admin 8083 |

> `fleet-compose.yml` **publishes** these deliberately-vulnerable services on
> localhost for the demo. Do not run it on an untrusted network.

## What you get

- **Ship status (left):** all 8 subsystems, each showing live/offline state and
  link latency from the real probe, with a status pip and alarm colouring.
- **Operations console (center):** an interaction panel for **each subsystem
  that is actually reachable**. Each has a small form (or terminal) that
  performs one real operation and prints the real result. Offline subsystems
  aren't given controls — they're listed in an "OFFLINE" strip.
- **System event log (right):** real events — subsystems coming online/offline,
  every interaction fired and its real outcome.
- **Status strip (top):** subsystems online, mean link latency, live-interaction
  count, last scan time.
- Auto-scan every 6 s (toggle **AUTO**), manual **RESCAN FLEET**, stardate clock,
  drifting starfield.

## The interactions are real — each speaks the module's actual protocol

Every panel POSTs to `/api/interact`, which drives the service using a
stdlib-only client modelled directly on that module's
`unit_tests/test_*.py` reference client and README "minimal client session"
(see `interactors.py`).

| Subsystem | Real operation | Protocol |
|---|---|---|
| FMM | authenticate (USER/PASS → session token) + PWD | raw FTP-like TCP control connection |
| IPM | upload + convert a real 1×1 PNG, retrieve it back through FMM | HTTP multipart |
| DNSM | A/AAAA/TXT/MX/NS/CNAME query, answer section decoded | DNS wire format over UDP |
| KVS | RESP terminal — SET/GET/PING/KEYS/… | RESP (Redis protocol) over raw TCP |
| LOG | ingest a log line; search ingested lines | HTTP JSON |
| OTA | list published-update versions per module + registered devices | HTTP JSON |
| MQB | publish/subscribe round-trip (two real MQTT clients) | hand-rolled MQTT 3.1.1 |
| MAIL | full SMTP session (EHLO/MAIL/RCPT/DATA), confirmed via admin queue | SMTP over TCP |

To adjust which operations/fields appear, edit the `actions` in
`data/catalog.json` — the frontend renders the forms from it. To change how an
operation talks to a service, edit `interactors.py`.

### What's real vs. themed

| Element | Source |
|---|---|
| Subsystem online/offline + latency | **real** — TCP/UDP probe + `docker ps` via `/api/live` |
| Every interaction result (login token, DNS answers, RESP replies, MQTT round-trip, SMTP queue id, converted image, log matches, OTA versions/devices) | **real** — live service over its actual protocol |
| Subsystem/ship names, HUD styling, starfield, stardate | themed presentation only |

Nothing about a module's state is fabricated: a panel is either backed by a
live service or shown as offline.

## Harness uplink — the bridge is the harness's client

The bridge runs **locally on a contestant's machine** and is the only UI they
use. The **harness** (the `saintcon-appsec-harness` repo) runs in the cloud and
is driven entirely through its JSON API. The bridge is that API's client: it
authenticates on the contestant's behalf, packages source into a bundle, and
submits it — so the browser never talks to the harness directly. There are two
independent submission actions, each in its own console:

- **Submit modules** (the **grade station**, the brass port in the wide cockpit)
  — packages every module's source; the harness grades it for functional
  correctness and planted-vuln PoCs and returns a per-module result.
- **Submit A.L.I.E.N.** (the **weapons console**, the PKT Signal Harpoon
  close-up) — packages just the exploit scripts (with a ship picker); the
  harness runs them against the chosen ship(s) and reports ships boarded. The
  grade station links to it rather than carrying this track itself.

The two are **separate submissions** on separate daily budgets; the scoreboard
unifies their results. While either job is grading, the console shows a live
per-phase / per-station progress indicator (and a compact tell in the bottom
sill), fed by the harness's sanitized `progress` — phase + per-item state only,
never counts.

Proxy endpoints on the console (the browser only ever calls these):

- `GET /api/harness`, `GET /api/auth/status` — safe state (harness configured?,
  its URL, logged-in?, username). **Never** returns the token.
- `POST /api/auth/register` `{name, username, password}` and
  `POST /api/auth/login` `{username, password}` — call the harness, then cache the
  returned bearer token locally (see `BRIDGE_SESSION_FILE`).
- `POST /api/auth/logout` — clears the local session (and the harness token).
- `GET /api/scoreboard` — public top 10, proxied as-is. `GET /api/score` —
  the signed-in caller's score, solved vuln count, and solved ship count.
  Refuses when nobody is signed in.
- `GET /api/flags` — the signed-in caller's **earned A.L.I.E.N. reward flags**,
  one per boarded ship that has a static flag configured, from the harness
  `GET /api/flags` (`{ok, flags:[{alien, name, challenge_path, flag}]}`). The
  bridge additively persists what the harness returns to `data/flags.json`
  (keyed by username), so the wallet survives reloads and a briefly-unreachable
  harness; if the harness can't be reached the kept flags are returned with
  `stale: true`. The cockpit shows these on the menu bar (the **A.L.I.E.N.
  flags** button + panel) and inline on a successful alien submission. Only the
  stable reward flag is ever surfaced — never the random flag the grader mints
  to verify a solve.
- `GET /api/challenges` — proxied list of active modules (id, name,
  `challenge_path`, `allowed_files`) **and released A.L.I.E.N. ships**
  (`aliens[]`, same shape). The bridge uses each entry's `allowed_files` to know
  exactly what to package, and the released `aliens[]` to populate the submit
  panel's ship picker.
- `POST /api/submit` with `{kind: "module"}` (the default) — the **module
  track**. Packages every module's files matching that module's `allowed_files`
  (so the harness accepts each entry; tests, vendored code, Dockerfiles,
  manifests and data are left out — fixed by the baseline) into one ZIP with
  repo-relative paths (`<module>/<file>`), then submits it with the logged-in
  token to the harness's `/api/submit`. No alien grading happens here. Returns
  `{ok, job_id, status, packaged{fileCount, moduleCount, modules[]}}`. A
  multipart upload (field `file`, optional `kind`) takes the same track from a
  player-built ZIP instead of packaging the local source.
- `POST /api/submit` with `{kind: "alien", alien_target}` — the **A.L.I.E.N.
  track**. Packages only the released ships' exploit files and forwards to the
  harness's `/api/submit/alien`. `alien_target` is an **A.L.I.E.N. ship id** to
  grade only that (released) ship, or omitted / `"all"` to grade every released
  ship. Returns the same shape (`packaged` counts ships instead of modules).
- `POST /api/alien/test` `{challenge_path}` — **local** A.L.I.E.N. test (no
  harness). Loopback-only. Brings that ship up from `aliens/docker-compose.yml`
  (`docker compose up -d --build`, building on first use), waits for it to
  answer, runs its `aliens/<ship>/exploit.py` against it the way the harness
  grades it (`~15s`, in a `python:3.12-slim` + allowlist grader container on a
  private internet-less network; ships are independent, no boarding pass), greps
  the output for the ship's own flag, then **spins the ship down** (`rm -s -f`)
  — always, even on failure. It
  holds the same fleet lock the power/rebuild paths use. Returns
  `{ran, solved, flag?, output}`, or an error such as `ship_start_failed` /
  `ship_unreachable` / `conflict`. See `alien_local.py` (parse + run) and
  `server.alien_local_test` (lifecycle). This runs the operator's own repo
  script on the operator's own machine, which is why it is loopback-gated and
  never exposed to a remote origin.
- `GET /api/submissions`, `GET /api/submissions/<id>` — proxied status/result,
  then sanitized for the cockpit. The browser sees `status_name`, `passed`,
  `result_summary`, `security_status`, `security_solved: [{module, n}, …]`
  (fixed PoC indices), and when the scorer sent a security list,
  `security: [{module, vulns: [{n, fixed, error, skipped}]}]`, solved numbers
  only. No missed number, vuln name, slug, title, or PoC output. Module counts,
  summaries, and n/m ratios are stripped. The grade screen shows solved numbers
  only.

Config (env on the console):

| Var | Meaning | Default on this lab compose |
|---|---|---|
| `HARNESS_URL` | base URL of the harness API | **empty** (no uplink until set) |
| `HARNESS_TIMEOUT` | per-request timeout, seconds | `30` |
| `BRIDGE_SESSION_FILE` | where the contestant's token is cached | `bridge/data/session.json` |
| `BRIDGE_AUTOUPDATE` | enable release-update checks at all | `1` |
| `BRIDGE_UPDATE_AUTOAPPLY` | auto-pull an additive update (vs. banner + click) | `0` |
| `BRIDGE_UPDATE_APPLY` | allow `POST /api/updates/apply` at all | `0` |
| `BRIDGE_UPDATE_REMOTE` / `BRIDGE_UPDATE_BRANCH` | upstream to track | `origin` / `main` |

`fleet-compose.yml` defaults `HARNESS_URL` to the public event harness
`https://saintcon.sketrik.dev`, so a fresh fleet can log in and submit without
extra configuration. Override it to point elsewhere (e.g.
`HARNESS_URL=http://127.0.0.1:8888` for local harness rehearsal), or set it
**empty** (`HARNESS_URL=`) to run a disposable local fleet with no external
uplink. `fleet-up.sh` prints the effective value. The bridge is `network_mode: host`.
Because the repo is mounted read-only in the container, `fleet-compose.yml` gives
the bridge a writable `bridge-session` volume and sets
`BRIDGE_SESSION_FILE=/session/session.json` so login survives a restart. The full
API this client speaks is documented at the top of `harness.py` and implemented
in `saintcon-appsec-harness/app/main/api.py`.

```bash
# point the console at a different harness (e.g. local dev) when bringing the fleet up:
HARNESS_URL=http://127.0.0.1:8888 ./start.sh
# or disable the external uplink entirely:
HARNESS_URL= ./start.sh
```

## Self-update — pulling the daily releases

The challenge ships over three days; each day pushes a **purely additive** commit
to the upstream branch (a new A.L.I.E.N. ship scaffold, a new module, …). The
console checks for these every few minutes (`GET /api/updates`: a `git fetch`
plus a diff of what the local `HEAD` is missing — read-only) and shows a banner
below the top bar when one is available. Lab compose defaults
`BRIDGE_UPDATE_AUTOAPPLY=0` and `BRIDGE_UPDATE_APPLY=0` (banner only; apply
opt-in). Set both to `1` only when intentionally auto-pulling.

Applying is non-destructive (see `updater.py`):

- clean tree already on the release branch → a fast-forward (a plain `git pull`);
- otherwise (you committed local work, or sit on your own branch) each missing
  commit is **cherry-picked** onto your current `HEAD`, preserving your history;
- uncommitted edits are stashed for the duration and popped back afterward;
- **safety rail:** apply refuses unless *every* pending commit is purely
  additive. A commit that modifies or deletes existing files is surfaced but
  never auto-applied, so an unexpected upstream change can't clobber your patch.

For this the bridge image includes `git` and `fleet-compose.yml` mounts the repo
**read-write** (it's your own operator console, not a scored target). The
containerized bridge runs as root with no git identity, so `updater.py` supplies
a fallback committer identity (`BRIDGE_UPDATE_AUTHOR_NAME` /
`BRIDGE_UPDATE_AUTHOR_EMAIL`) only when the checkout has none configured.

## Architecture / room to grow

- `server.py` — Python stdlib HTTP server. `GET /` checks the bridge login
  token: no session serves the sign-in page, a session serves the cockpit.
  Scripts, module pages, and assets are served at the site root from
  `cockpit-ui/live3d/` (that directory name is not a public URL). Plates are
  under `/cockpit/`, three.js under `/three-exploration/`. JSON API
  (`/api/catalog`, `/api/live`, `/api/interact`, `/api/power`, `/api/health`,
  `/api/harness`, the `/api/auth/*` proxy, `/api/challenges`, `/api/submit`,
  `/api/submissions`, `/api/updates`). A real backend process (not a static file) so it can reach
  Docker-network services, drive the fleet, and proxy to the harness — and it
  holds the contestant's harness token locally so the browser never sees it.
- `interactors.py` — one stdlib protocol client per module; `dispatch()` routes
  `(code, action, params)` to the right one.
- `harness.py` — stdlib harness API client: `package_challenge()` builds one ZIP
  of the given pieces' allowed source (repo-relative paths, scoped by each
  piece's `allowed_files`); `register()/login()/submit_modules()/submit_aliens()
  /get_submission()` call the harness API. The API it speaks is documented at the
  top of the file.
- `data/catalog.json` — subsystems + their interaction action specs.
- `fleet-compose.yml` — the primary stack: all 8 modules **plus this console**
  (service `bridge`, on the host network, mounting the repo + Docker socket).
  `fleet-up.sh` / `fleet-down.sh` bring it up/down; `start.sh` targets just the
  console service.

This module is the operator console, not a scored target.
