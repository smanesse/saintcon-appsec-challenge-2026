# Challenge 02 — Cargo Manifest Terminal

**Language:** Node.js · **Difficulty:** ★★☆☆☆ (intermediate)

> **Standalone ship:** independent of the other ships — the cargo terminal is
> open, with its own flag.

The ship's cargo terminal retrieves manifest files by name. The terminal tries
to keep you inside its `manifests/` directory — see how far you trust it to.

## Run

```bash
docker build -t alien-cargo .
docker run --rm -p 8092:8080 alien-cargo
# open http://localhost:8092
```

## Goal

Read `/flag.txt`, which sits outside the `manifests/` directory.
