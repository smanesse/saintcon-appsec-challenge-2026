# KVS — complete vulnerability list & PoCs

The five PoCs below target the intentionally-vulnerable KVS store. All are
standalone Python 3, stdlib only, and self-verifying over the network — each
proves its bug *through the service* (reading the deployment's seeded secret
back through KVS, standing up a rogue peer KVS dials into, or timing KVS's own
replies) and prints `[+]` on confirmed success / `[-]` on failure.

## The scoreable secret: KVS_FLAG

Every disclosure PoC steals the **same** per-deployment secret, `KVS_FLAG`,
minted fresh by `../../generate-secrets.sh`. At startup the server seeds it two
ways (see `Store.Seed()` / `main()`):

- **into its own keyspace** under `fleet:control:flag` — the way a real app
  would have cached a credential — so an unauthenticated `GET` reads a genuine
  minted secret straight back (PoC #1); and
- **into its process environment** (`KVS_FLAG`) — so an unsandboxed `EVAL`
  `os.getenv()` leaks it too (PoCs #2, #3).

A standalone/dev run without a harness falls back to `FLAG{local-dev-default}`
so the PoCs still self-verify locally. This is what makes the disclosures
scoreable per the contract in `../../README.md`: they recover a value the
harness minted at deploy time, not one the PoC planted itself.

**Recommended: run everything in Docker.** The compose file brings up two
instances — `kvs` and `kvs-auth` — neither published to the host. **Both** have
a real `KVS_REQUIREPASS` configured and both carry `KVS_FLAG`, so the disclosure
PoCs (#1/#2/#3) score against either. Vuln #1 is that the server never enforces
the configured password, so #1's unauthenticated read still succeeds against
both; `kvs-auth` exists only as a distinct target for the AUTH-aware PoCs and
the un-numbered non-constant-time AUTH compare. Fixing vuln #1 (enforce the
configured password) makes #1 report failure against either instance.

```
# builds the images, waits for kvs, runs the flagship replication-takeover +
# secret-exfiltration PoC:
docker compose -f vuln_tests/docker-compose.yml run --build --rm poc

# run a different PoC (images already built):
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 02_eval_lua_rce.py kvs 6379
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 05_keys_glob_dos.py kvs 6379
```

Or point a script at an already-running KVS directly:

```
python3 vuln_tests/01_no_auth_default.py [host] [port]   # defaults 127.0.0.1 6379
```

## The list

| # | Vulnerability | Location | PoC |
|---|---------------|----------|-----|
| 1 | AUTH gate not enforced (sessions authenticated up front despite a configured password) → unauth read of the seeded `KVS_FLAG` | `handleConn()` in `main.go`; AUTH gate in `Session.dispatch()` in `session.go` | `01_no_auth_default.py` |
| 2 | `EVAL` runs unsandboxed Lua (`os`/`io`) → RCE + arbitrary file R/W + env disclosure (`KVS_FLAG`) | `cmdEval()` in `eval.go` | `02_eval_lua_rce.py` |
| 3 | `REPLICAOF` applies an untrusted peer's command stream (keyspace takeover, chainable into #2 to exfiltrate `KVS_FLAG`) | `cmdReplicaOf()` / `Server.replicateFrom()` in `replication.go` | `03_replicaof_injection.py` |
| 4 | Unbounded RESP bulk-string length → memory-exhaustion DoS / crash | `respReader.readBulk()` in `resp.go` | `04_bulklen_overflow_dos.py` |
| 5 | Exponential `KEYS` glob matching → algorithmic-complexity DoS | `cmdKeys()` in `session.go`; `stringMatchLen()` in `glob.go` | `05_keys_glob_dos.py` |

Two further planted vulns are **documented but ship without their own numbered
PoC** (by design — not every planted bug is scored; part of the exercise is
spotting them and judging their impact):

- **`CONFIG SET dir`/`dbfilename` + `SAVE`** (`Config.set()` / `cmdSave()` in
  `config.go`) is an arbitrary-file-write primitive with no independent
  readback, so on its own it can't satisfy the scoring contract's "steals a
  secret, or costs the team points" requirement (see root `README.md`). It's
  folded into #2 below — EVAL is the thing that turns "wrote a file" into
  "read it back and proved it."
- **Non-constant-time `AUTH` comparison** (`insecureCompare()` via `cmdAuth()`
  in `auth.go`) is a real timing side-channel that recovers the password
  byte-by-byte. A password is always configured, so the compare is reachable,
  but recovering it only *matters* once #1 is fixed — before that an attacker
  doesn't need the password, since the unenforced gate already grants full
  access. Left in the source as an exercise in spotting the
  early-return-on-first-mismatch shape; there is no scored PoC for it, and it's
  the intended reason `kvs-auth` exists.

## What each PoC actually proves

- **#1** opens a raw connection to `kvs`, runs privileged commands with no
  `AUTH` at all — even though a password is configured — and, the scoreable leg,
  `GET`s the seeded `fleet:control:flag` key to read the deployment's real
  `KVS_FLAG` straight out of the open keyspace. A no-auth data round-trip and
  `CONFIG GET` are kept as supporting evidence of full read/write + admin.
  Against a server where vuln #1 is fixed (the configured password is actually
  enforced) the server answers `NOAUTH` and #1 reports failure — exactly the
  defended state.
- **#2** runs several EVALs on one connection: `os.execute()` writes a token to
  a file (command execution), `io.open()` reads it back (arbitrary file read),
  and — the scoreable leg — `os.getenv('KVS_FLAG')` recovers the deployment's
  minted secret straight out of the process environment. An unsandboxed Lua
  state can read any env var the kvs process holds, so it also grabs
  `KVS_REQUIREPASS` as bonus evidence (configured on both instances). The PoC's
  pass/fail hinges on recovering `KVS_FLAG`. Its docstring also covers the
  `CONFIG SET`/`SAVE` file-write primitive as a documented capability of the
  same unsandboxed EVAL, not a separate PoC.
- **#3** stands up a rogue "replication master", gets the victim to
  `REPLICAOF` it, and streams back both an injected key (proving keyspace
  takeover) and an `EVAL` that copies the victim's own `KVS_FLAG` (via
  `os.getenv`) into an attacker-chosen key — read back over the PoC's normal
  client connection. This chains the takeover into concrete secret
  exfiltration, not just attacker-chosen data landing in the keyspace.
- **#4** confirms the DoS **by liveness of a separate bystander connection**,
  not by the attack request's own fate. It walks both failure modes of the
  unbounded bulk-length parser but only the second denies the bystander: the
  oversized-but-positive length merely hangs the *attacker's* own connection
  (the bystander keeps answering PING — proving a slow attacker request is not
  a DoS), while a **negative** length panics `make()` and, with no `recover()`
  and no container restart policy, crashes the whole process — after which the
  bystander connection is dead *and* fresh connects are refused. Pass requires
  that proven denial of the bystander.
- **#5** confirms the DoS **by bystander impact**, not by the attacker's own
  `KEYS` latency. It baselines an ordinary second connection's idle `GET`
  (sub-millisecond), then times that same `GET` while the pathological
  `KEYS a*a*...*b` holds the global keyspace lock — the bystander stalls for
  seconds (or times out). Pass requires the bystander be degraded by a large
  factor vs. its baseline (or denied outright), proving the exponential blowup
  + global lock is a shared-service DoS, not just a slow attacker.

## Notes on how these interact

- **#1 is the master key for #2, #3, and #5.** Every one of those is
  reachable by an unauthenticated client precisely because the server never
  enforces the configured password. Enforcing it (fixing #1) gates all of them
  behind AUTH at once — which is exactly what makes the non-constant-time AUTH
  compare matter: the timing side-channel in that check is how an attacker gets
  *back* through the gate without knowing the password, re-opening #2/#3/#5.
  Note that #2 and #3 don't *stop* mattering once #1 is fixed, though — see the
  next point.

- **#2's unsandboxed EVAL discloses the deployment's `KVS_FLAG` regardless of
  whether this connection was authenticated.** `os.getenv()` reads the *whole*
  process environment, so even against a server where #1 is fixed — where a
  client must AUTH to run EVAL at all — the secret comes straight out of the
  environment, not brute-forced through the gate. That matters because #3 uses exactly this to
  turn a keyspace takeover into secret theft: it streams an `EVAL` over the
  replication link that reads `KVS_FLAG` via `os.getenv()` and writes it into a
  key the attacker can read back over a normal connection — `replicaConn.Write`
  discards direct replies on that link, so exfiltrating through the keyspace is
  how the PoC gets the value out. #2 also still keeps its independent arbitrary
  file read/write via `io.open` — including reading back whatever
  `CONFIG SET dir`/`dbfilename` + `SAVE` wrote, the "Redis writes a webshell /
  authorized_keys" technique.

- **#2 and #3 both reach admin-level effects, by different routes.** #2 is
  code execution in-process; #3 is data/command injection from a fake
  replication master. #3 is the most protocol-specific: once KVS is your
  replica it applies *any* command you stream, including #2's `EVAL`
  primitive — so #3 is also a delivery vehicle for #2 against a victim you can
  only reach via `REPLICAOF`. Fixing #3 (don't trust arbitrary masters)
  removes that delivery path but leaves #2 directly exploitable by a normal
  client.

- **#4 and #5 are both denial-of-service but with nothing else in common.**
  #4 is a *memory* exhaustion in the protocol parser (before a command even
  dispatches); #5 is a *CPU* exhaustion inside a specific command's matcher.
  #5 is aggravated by the global keyspace lock — a single pathological `KEYS`
  stalls every other client, not just the attacker's connection — while #4
  costs the attacker only one connection per allocation (except the negative
  case, which crashes the whole process). Neither fix touches the other.

- **The non-constant-time AUTH compare only matters once #1 is fixed.** A
  password is always configured, so the comparison is reachable, but the timing
  leak is worthless while the gate isn't enforced — an attacker needs no
  password to get in. The moment #1 is fixed and AUTH is actually required, the
  side-channel becomes the way *back* through the gate — a classic case where
  closing one hole exposes the weakness behind it. There is no scored PoC for
  it, but it's the intended reason `kvs-auth` exists.

## Fix directions (brief — save the detail for when they ask)

1. **Enforce the configured AUTH gate:** mark a session authenticated up front
   only when no password is configured (`authenticated: srv.cfg.password() ==
   ""`), so a configured `KVS_REQUIREPASS` actually forces AUTH before any
   command runs. Additionally require a password to be set at all — refuse to
   start, or bind only to loopback, when it isn't — so a writable keyspace is
   never served unauthenticated on a routable interface. (Seeding a real secret
   into that open keyspace is what makes the open state directly scoreable — #1
   just reads it.)
2. **Unsandboxed EVAL:** run scripts in a locked-down interpreter with `os`,
   `io`, `loadfile`, `dofile`, `package` and friends removed (as real Redis
   does), or drop server-side scripting entirely. This also closes the
   `CONFIG SET dir`/`dbfilename` + `SAVE` file-write's readback path via
   `io.open`; independently, validate `dir`/`dbfilename` against an allow-list
   (no traversal, a fixed data directory, a fixed extension) so the write
   itself isn't arbitrary either.
3. **Untrusted replication:** authenticate the master (shared secret / mTLS),
   pin the allowed master address, and never expose `REPLICAOF` to
   unauthenticated clients; a replica must not accept arbitrary admin commands
   over the link.
4. **Unbounded bulk length:** enforce a maximum bulk length (Redis's
   `proto-max-bulk-len`, 512MB) and reject negative/oversized lengths with a
   protocol error *before* allocating; read incrementally rather than
   pre-sizing a buffer to the client's claim.
5. **Exponential glob:** replace the recursive backtracking matcher with a
   linear-time glob (dynamic-programming or an equivalent NFA), and/or cap
   pattern complexity; don't hold the global lock across an unbounded scan.

Plus the un-numbered **timing side-channel**: compare the password with a
constant-time routine (`crypto/subtle.ConstantTimeCompare`) over hashes of
equal length, so the response time reveals nothing about the correct prefix.
