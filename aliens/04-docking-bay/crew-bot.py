#!/usr/bin/env python3
"""
Flight-crew reviewer. Runs inside the container as the crew. It signs in once to
obtain a crew session, then works the docking bay the way a crew member on shift
would: it keeps an eye on bay status and diagnostics, checks berths, and — as it
drains the pilot docking queue — pulls up each submitted path to "review" it.

Everything it fetches goes through the edge on loopback, carrying its crew
cookie.
"""
import os
import random
import time
import urllib.parse
import urllib.request
import http.cookiejar

EDGE = os.environ.get("VARNISH_URL", "http://127.0.0.1:8080")
CREW_USER = os.environ.get("CREW_USER", "flight-crew")
CREW_PASS = os.environ.get("CREW_PASS", "orbital-wrench")

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Routine shift activity — the reviewer touches these as it goes about its work.
ROUNDS = [
    ("GET", "/"),
    ("GET", "/static/console.js"),
    ("GET", "/static/console.css"),
    ("GET", "/status"),
    ("GET", "/actuator/health"),
    ("GET", "/actuator/info"),
    ("GET", "/dock/berth?id=A1"),
    ("GET", "/dock/berth?id=A2"),
    ("GET", "/dock/berth?id=B7"),
    ("GET", "/dock/whoami"),
    ("GET", "/robots.txt"),
]

SAMPLE_MANIFEST = (
    '<?xml version="1.0"?>'
    "<manifest><berth>A2</berth><vessel>supply-drone</vessel></manifest>"
)


def _req(method, path, data=None, content_type=None):
    r = urllib.request.Request(EDGE + path, data=data, method=method)
    r.add_header("User-Agent", "alien-crew-reviewer/1.0")
    if data is not None:
        r.add_header("Content-Type", content_type or "application/x-www-form-urlencoded")
    return opener.open(r, timeout=5)


def visit(method, path, data=None, content_type=None):
    try:
        with _req(method, path, data, content_type) as resp:
            resp.read()
            return resp.status
    except Exception:
        return None


def login():
    body = urllib.parse.urlencode({"user": CREW_USER, "pass": CREW_PASS}).encode()
    try:
        with _req("POST", "/login", body) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for_edge():
    for _ in range(120):
        if visit("GET", "/status") is not None:
            return
        time.sleep(0.5)


def do_rounds():
    """A little organic background activity each tick."""
    for method, path in random.sample(ROUNDS, k=random.randint(1, 3)):
        visit(method, path)
    if random.random() < 0.2:
        visit("POST", "/manifest/validate", SAMPLE_MANIFEST.encode(), "application/xml")


def review_queue():
    with _req("GET", "/crew/pending") as resp:
        paths = resp.read().decode("utf-8", "replace").splitlines()
    for p in paths:
        p = p.strip()
        if p:
            visit("GET", p)


def main():
    wait_for_edge()
    while not login():
        time.sleep(1)
    while True:
        try:
            review_queue()
            do_rounds()
        except Exception:
            # session may have expired; re-establish it
            login()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
