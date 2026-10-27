# Vulnerable Module Collection

This repo is a collection of small, self-contained, **intentionally-vulnerable
services** for a security/CTF course. Each one is a "module" that models a
realistic piece of infrastructure (a file server, an image pipeline, …), speaks
a real protocol, and does something genuinely useful. Teams audit the source,
find and exploit the planted weaknesses, and fix them in place.

The modules:

- **`file-management-module/` (FMM)** — a C++ FTP-like file server (plaintext
  TCP control connection + separate data connection).
- **`image-processing-module/` (IPM)** — a Java/Spring-Boot HTTP image
  converter that shells out to a bundled ImageMagick and STORs its output into
  FMM.
- **`dns-module/` (DNSM)** — a C authoritative DNS name server.
- **`keystore-module/` (KVS)** — a Go RESP (Redis-protocol) key-value store.
- **`log-module`** — a Scala/http4s log-ingestion and dashboard service.
- **`ota-module` (OTA)** — a Go fleet-update server, with an agent wired into
  FMM/IPM/log as a client of each.
- **`mqtt-module` (MQB)** — a Python (asyncio) MQTT 3.1.1 broker for a fleet
  of IoT devices, hand-rolled wire format.
- **`mail-module` (MTA)** — a Node.js outbound SMTP relay.

Several also compose: IPM is a *client* of FMM, and OTA's agent talks to
FMM/IPM/log, so a module can stand alone or depend on a sibling.

Supporting apps (not scored targets): `bridge/` is the operator console and
scoring client, and `metadata-service/` is a benign internal-only service the
fleet keeps on its trusted network.

> ⚠️ **Everything here is deliberately insecure.** The modules exist to be
> attacked in a lab and must never run on a network you do not fully control.
> The compose files keep every module on a private Docker network and never
> publish a module port to the host.

## Run it

From the repo root:

```bash
./start.sh            # build + start the Bridge Console (fast); then open http://127.0.0.1:8787
./start.sh all        # console + every module (first builds are slow)
./stop.sh             # stop everything
```

`./start.sh` / `./stop.sh` are the primary entry points (thin wrappers over
`bridge/fleet-up.sh` / `bridge/fleet-down.sh`); they accept module names or a
release day (`day1` `day2` `day3` `all`). On Windows, `start.bat` takes the
same arguments (it delegates to `start.sh` via Git Bash or WSL). Start individual modules from the
console's START buttons or by passing them to `./start.sh`. The console submits
to the scoring harness at `https://saintcon.sketrik.dev` by default; override
with `HARNESS_URL=...` or disable the uplink with `HARNESS_URL=`.

## CI and harness updates

Pull requests to `main` run every `*/unit_tests/run-in-docker.sh` functional
suite, including the bridge. A push to `main` runs the same suites; once they
all pass, GitHub Actions marks the commit approved and asks the AWS harness
host to pull it. If grading is in progress, the action waits for an idle queue.
The host also checks the last approved commit every five minutes as a fallback.

Run the same suites locally with `./run-all-unit-tests.sh`.

---

## Design principles

1. **Realistic, not contrived.** The service does a real job with a real
   protocol/API. The weaknesses are the kind you actually find in that kind of
   system — not artificial "guess the flag" puzzles. A team that audits the
   source learns transferable lessons.
2. **Deliberately vulnerable, clearly labelled.** Every module screams that it
   is unsafe (banner comments, README warnings) and must never run on an
   untrusted network. Mitigations are intentionally disabled where they'd get
   in the way, with a comment at the build setting that says so.
3. **Functional tests ≠ security.** The `unit_tests/` prove the *intended*
   behaviour works. They are driven purely over the wire and say nothing about
   the planted weaknesses.
4. **Everything runs in Docker, off the host.** The vulnerable service (and any
   vulnerable dependency) is only ever reachable on a private compose network,
   never published to a host port, in the default flows.
5. **The functional README has no spoilers.** Each module's `README.md`
   documents the *functional* protocol/API so clients and tests can drive it,
   and nothing more.

---

## What a submission may contain

Teams fix weaknesses by editing **source code, in place**. A submission is
scored by rebuilding every module from the challenge's own pristine baseline and
overlaying only the source files a team sends — so a team cannot add a new kind
of file, change the Docker build, or install extra packages through a
submission. Those are *fixed infrastructure*: Dockerfiles, compose files,
dependency manifests (`requirements.txt`, `package.json`, `go.mod`, `pom.xml`,
`build.sbt`, …), shell runners, vendored third-party code, and data files all
come from the baseline, and edits to them are ignored.

This is enforced by construction, not by trust: the bridge console packages a
snapshot that **contains only allowlisted source** (`bridge/harness.py` →
`package_repo`), so unallowed files are never even delivered. The allowlist is
published as the shared contract at [`submission-policy.json`](submission-policy.json)
(the scoring harness mirrors it) — source extensions in, everything else out.
When a team transmits, the console reports the file count and how many
non-source files were left out, so it's clear what did and didn't ship.

---

## Standard module layout

```
<name>-module/
├── README.md              # FUNCTIONAL protocol/API reference (no spoilers)
├── Dockerfile             # multi-stage build → runtime; runs as unprivileged `ctf` user
├── .dockerignore          # keep build context lean
│
├── <source>               # the service itself (fmm.cpp / src/**, pom.xml, Makefile, …)
│
└── unit_tests/            # FUNCTIONAL tests — prove the intended behaviour works
    ├── test_<name>.py     # network/HTTP-driven, stdlib only, env-var configurable
    ├── docker-compose.yml # service (unpublished) + a python test runner
    └── run-in-docker.sh   # build + run tests + clean up; exit code mirrors the run
```

Naming: the module directory is `<thing>-module`; the service/binary and all
env-var prefixes use a short uppercase acronym (`FMM`, `IPM`).

### Conventions each module follows

- **`README.md`** is written for a client author, not an attacker: a one-line
  intro, a prominent ⚠️ "do not deploy" block, a **Connection** table, a full
  command/endpoint reference with **every** reply/status code, a status-code
  summary, and a minimal client session transcript. No weakness is mentioned or
  hinted at.
- **The service source** builds with mitigations off where they'd block a
  planted weakness (and says so in a comment). All config is overridable via
  environment variables with the module's prefix.
- **The `Dockerfile`** is multi-stage (build → slim runtime), restates that the
  image is deliberately vulnerable, runs as an unprivileged `ctf` user, and
  `EXPOSE`s the service port — but the compose files **do not publish it**.
- **`unit_tests/`** are stdlib-only, driven purely over the wire, exercising the
  intended protocol/API from `README.md`. The compose file runs the service on
  an `expose`-only (unpublished) port on a private network plus a
  `python:3.x-slim` runner; `run-in-docker.sh` builds, runs, and tears
  everything down, mirroring the test exit code.

### Runtime secrets

Any flag or credential a deployment relies on is **unique per deployment**,
minted fresh at deploy time — never a value baked into the repo or image. See
[`generate-secrets.sh`](generate-secrets.sh) for how the per-deployment flags
and credentials are minted and fed to the stack.

---

## Adding a new module

Use the **`new-module`** skill rather than hand-rolling the scaffold. It
produces a complete module in this exact layout: real working functionality,
functional unit tests, README documentation, and Dockerized runners.
