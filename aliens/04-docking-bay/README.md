# Challenge 04 — Docking Bay

**Language:** Java / Spring Boot + Varnish · **Difficulty:** ★★★★★ (expert)

> **Standalone ship:** independent of the other ships — the pilot area is open,
> with its own flag. The crew area still needs a crew session (that is part of
> the puzzle, below), but there is no boarding pass between ships.

The mothership launch is protected in depth, and nothing here is spelled out on
the wire. You will have to **recon** the ship carefully, figure out what the
crew can do that a mere pilot cannot, and find a way to make it happen for you —
and ignore the decoys along the way.

## Architecture

```
 attacker ──HTTP──►  EDGE cache (Varnish, :8080, exposed)
                         │
                         ▼
                     ORIGIN (Spring Boot on Tomcat, :9090, loopback)
                         ▲
                         │
                     CREW REVIEWER (in-container bot)
```

Only the Varnish edge is exposed. The origin and the crew reviewer live on
container-loopback. The launch code is reachable only with a flight-crew
session — which only the reviewer has.

## Run

```bash
docker build -t alien-docking .
docker run --rm -p 8094:8080 \
    --read-only --tmpfs /tmp:exec,mode=1777 alien-docking
```

(The `exec` tmpfs option matters: Varnish compiles its VCL to a shared object
and `dlopen()`s it from its work dir, which cannot be `noexec`.)
