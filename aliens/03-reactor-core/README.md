# Challenge 03 — Reactor Core Console

**Language:** PHP · **Difficulty:** ★★★☆☆ (advanced)

> **Standalone ship:** independent of the other ships — the engineering console
> is open, with its own flag.

The reactor console persists your session in a base64 `reactor_session` cookie
and restores it on every request. Study how that session round-trips and what
the codebase does with it.

## Run

```bash
docker build -t alien-reactor .
docker run --rm -p 8093:8080 alien-reactor
# open http://localhost:8093
```

## Goal

Read `/flag.txt`.
