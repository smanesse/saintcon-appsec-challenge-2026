# FMM - complete vulnerability list & PoCs

All PoCs below were run against the current `fmm.cpp`. Each script prints what
it did and decides success/failure BY LIVENESS where the vuln is a DoS - it
baselines or re-probes a SEPARATE client and only claims an outage when that
bystander is actually denied, never from the attacker's own request fate. A
couple need elevated care - see their individual notes. (Numbering skips #3 and
#6: the use-after-free PoC (#3) was removed - a real, deterministic freed-memory
read, but not a scoreable bystander DoS on the stock glibc build - and the old
data-race PoC (#6) was removed as too flaky to self-verify. Both underlying bugs
(the use-after-free on QUIT and the unsynchronized `g_sessions` table) are still
present in `fmm.cpp`, just no longer exercised by a shipped PoC. Numbering also
ends at #8: the FTP-bounce (#9) and PASV-data-hijack (#10) PoCs were removed
because they can only be scored by comparing the data connection's peer IP to
the control connection's, yet both PoCs co-locate the attacker with the client
(same source IP, even over the fleet network), so the standard peer-IP
mitigation can never be told apart from the attack - a legitimate fix would be
scored as still-vulnerable. The data-channel feature remains in `fmm.cpp`, just
no longer scored.) #7 and #8 are the two that actually deny
service to other callers, and do so by the same thread/pid exhaustion.

## Run it all in Docker

The compose file brings up `fmm` and a `poc` runner, both unpublished. The
default `poc` command runs PoC #1 (command injection):

```
docker compose -f vuln_tests/docker-compose.yml run --build --rm poc
```

Run any other PoC by overriding the command (service name `fmm`, port `2121`):

```
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 04_path_traversal.py fmm 2121
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 07_redos.py fmm 2121
```

When you're done: `docker compose -f vuln_tests/docker-compose.yml down`.

## Run it locally

`./fmm &` from the project directory (so relative paths like `ftproot/`
resolve correctly), then run each script from the same host:

```
./fmm &
python3 vuln_tests/01_command_injection.py
```

## Runtime secret

FMM writes a real, per-deployment secret at startup - `write_flag_files()`
in `fmm.cpp`, called from `main()` - sourced from the `FMM_FLAG` env var
(see `../../generate-secrets.sh`), falling back to
`FLAG{local-dev-default}` so a standalone `docker build && docker run` or
the unit tests keep working with zero setup. It lands in two places, both
outside `ftproot`:

- `secret/flag.txt` - fixed, well-known path; content is the flag. This is
  the target for #1's RCE, which reads it via `system()` and isn't limited
  to what the FTP protocol itself can return.
- `secret/<flag value>` - a second copy in the same directory, with the
  flag as the *filename* rather than the content. `LIST` only ever
  discloses directory entry names, never file contents (see
  `handle_list()`), so #4 (path traversal) recovers the flag from that
  entry's name once it walks into `secret/`.
- `ftproot/vault/manifest.dat` - a third copy, as file *content*, INSIDE
  the served root. `RETR` of a within-root path is correct, allowed
  behaviour, so this is the disclosure target for the auth/session PoCs
  (#2, #5): each becomes authorized a different illegitimate way, then
  `RETR`s this file. Because the read never leaves `ftproot`, a containment
  fix on `CWD`/`LIST` (#4) does NOT make these two report fixed - only
  fixing each one's own bug does.

## The list

| # | Vulnerability | Location | PoC |
|---|---|---|---|
| 1 | Command injection | `log_download()`, called from `handle_retr` | `01_command_injection.py` |
| 2 | Stack buffer overflow -> auth bypass | `handle_user()` | `02_buffer_overflow_auth_bypass.py` |
| 4 | Path traversal (directory listing disclosure) | `handle_cwd()` | `04_path_traversal.py` |
| 5 | Session hijacking via predictable tokens | `generate_token()`, `handle_sess()` | `05_session_hijack.py` |
| 7 | ReDoS (chained with #8 for a full outage) | `is_valid_filename()`, called from `handle_stor` | `07_redos.py` |
| 8 | Resource exhaustion DoS | `recv_line()` + the thread-per-connection accept loop | `08_resource_exhaustion.py` |

## Notes on how these interact

- **#1 is the only vuln that reads the secret's file content directly.**
  `log_download()`'s `system()` call bypasses the FTP protocol (and its
  `RETR` containment check) entirely, so it's the only PoC here that `cat`s
  `secret/flag.txt` outright. Every other disclosure vuln below is stuck
  with what `LIST` can hand back - directory entry *names*, never file
  bodies - which is exactly why the secret directory also carries a
  filename-encoded copy of the flag (see "Runtime secret" above).
- **#2 and #5 each disclose through an authenticated-only RETR,
  NOT through #4's containment gap.** Earlier these both cashed out by
  CWDing out of `ftproot` and `LIST`ing `secret/` - the exact gap #4 fixes -
  so a single `CWD`/`LIST` containment fix flipped them to "fixed" while
  the overflow and predictable tokens stayed exploitable. They now
  `RETR ftproot/vault/manifest.dat`, a read a genuinely logged-in client is
  *allowed* to do (`handle_retr`'s `is_path_within_root()` passes), so each
  proves its own primitive: #2 forges `authenticated` via the overflow, #5
  hijacks a predictable resume token - and then RETRs the within-root secret.
  Fixing #4 (containment on `CWD`/`LIST`) no longer touches either of them;
  each needs its own fix. #4's own PoC still uses `CWD ../secret` + `LIST` and
  is correctly the one thing a containment fix closes.
- **The use-after-free and `g_sessions` data race remain in `fmm.cpp` but
  no longer ship a PoC.** QUIT does `delete session` yet leaves the token in
  `g_sessions`, so a later `SESS` returns the dangling `Session*` and
  `strcpy`s out of `target->username` - a real, deterministic freed-memory
  read (a resumed identity sourced from freed heap). It did NOT reliably
  crash the shared process on the default glibc build, though: the instant
  the `Session` chunk is freed, glibc overwrites its first bytes with
  tcache/allocator metadata (a `NULL` next-pointer), so `target->username`
  starts with a `NUL` and the stray `strcpy` copies almost nothing rather
  than running off a mapped page - so it was not a scoreable bystander DoS
  as-shipped and its PoC (#3) was removed. The same map is also read/written
  from every connection's thread with no mutex, so concurrent
  `PASS`/`SESS`/`QUIT` can race on it independent of any UAF - a latent
  data-race bug (its old PoC, #6, was removed as too probabilistic). Both
  become deterministic, scoreable crashes only under AddressSanitizer or a
  hardened allocator that poisons/quarantines freed chunks (`g++ -std=c++17
  -g -fsanitize=address -pthread -o fmm_asan fmm.cpp`), so neither is scored
  in the shipped catalogue.
- **#7 only becomes a scoreable DoS by chaining with #8.** A single evil
  STOR (a ~40+ char run of allowed characters with no `.ext`) pins *one*
  worker thread in `regex_match()` at 100% CPU effectively forever, but fmm
  is thread-per-connection, so other clients keep being served - by the
  scoring contract, hanging your own connection costs the team nothing.
  Verified against the capped container (`cpus: "1.0"`): even with a thread
  pinned at 100% CPU, a normal client's login+PASV+RETR still completes in a
  few ms, because it is I/O-bound and the scheduler preemptively time-slices
  the CPU hog. `07_redos.py` phase 1 demonstrates exactly this - it pins one
  thread (the STOR never replies) and then shows a separate bystander
  sailing through. What takes the *whole module* down is the accept loop's
  uncapped `std::thread(...).detach()` (vuln #8) with no per-connection
  timeout: hold enough evil-STOR connections open and the process/container
  **thread (pid) budget** is exhausted - a few threads wedged in the regex,
  the rest starved behind them mid-handshake - so fmm stops accepting new
  connections entirely and every other client is locked out. This is
  thread/pid exhaustion, confirmed by the fact that the refusal point tracks
  the container's `pids_limit` (raise the cap and it rises with it), not the
  16-deep listen backlog. Phase 2 baselines a bystander, floods evil STORs
  until fmm refuses new connections, and re-probes the SEPARATE bystander:
  the DoS is confirmed only when that bystander is DENIED. The outage holds
  as long as the attacker sustains the flood and lifts once the pool drains
  (the starved threads free when their sockets close; a residual handful stay
  regex-pinned but a few CPU-hogs alone don't deny an I/O-bound client). At
  the hard edge of the cap, `std::thread`'s constructor can instead throw
  `std::system_error` (EAGAIN) uncaught, tripping `std::terminate()` on the
  whole process; the shipped `ota-agent.sh` supervisor does NOT respawn a
  crashed service (a crash/unexpected exit is deliberately not restarted), so
  that outage stands until an operator intervenes. (A *multi-MB* filename
  instead stresses `recv_line()`'s unbounded buffer - a different sink,
  also #8.)
- **The data channel reshaped several existing PoCs.** Because LIST/RETR/
  STOR payloads now flow over a separate connection, #1, #2, #4, and #5
  were updated to negotiate `PASV` first (#2 uses `PASV` itself as the
  auth-gated proof command - `530` unauthenticated, `227` once authenticated -
  before moving on to the within-root `RETR` flag fetch). The underlying bugs
  are unchanged; only the transport around them moved.

## Fix directions (brief - save the detail for when they ask)

1. Never build shell strings from untrusted input; use `fork`/`exec` with
   an argument vector, or drop the shell-out and log with plain file I/O.
2. Bound the copy (`strncpy`/`snprintf`) or use `std::string` with a
   length check before copying into any fixed buffer.
   (No #3 or #6: their PoCs - the use-after-free and the `g_sessions` data
   race - were removed from the scored set, but the bugs remain in
   `fmm.cpp`. Fix: return/break out of the connection loop the moment a
   session is freed and remove its token from `g_sessions` on logout (prefer
   smart pointers / clear single-owner semantics), and guard `g_sessions`
   with a `std::mutex` or a concurrent map, keeping the erase-from-map and
   delete-the-Session steps atomic.)
4. Canonicalize with `realpath()`/`std::filesystem::canonical` and verify
   containment before accepting a CWD target; apply the same containment
   check to `LIST`'s directory that `RETR` already applies to files.
5. Use a cryptographically secure random source for tokens
   (`/dev/urandom`, `std::random_device` seeding a CSPRNG - not `rand()`),
   make tokens long enough to resist brute force, and bind them to the
   connection/IP that requested them.
7. Avoid nested quantifiers in regexes over untrusted input, or use an
   engine/library with linear-time guarantees (e.g. RE2), or just replace
   the regex with a straightforward character-by-character validator.
8. Cap `recv_line()`'s buffer size and reject/disconnect oversized input;
   add a connection/thread limit and per-connection idle timeouts.
