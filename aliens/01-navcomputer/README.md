# Challenge 01 — A.L.I.E.N. Navcomputer (Command Injection)

**Language:** Python · **Difficulty:** ★☆☆☆☆ (beginner)

> **Standalone ship:** independent of the other ships — no boarding pass, just
> this ship's own flag.

A deliberately vulnerable CTF challenge themed as an alien spaceship console.
It contains **one** intended command injection vulnerability. Exploit it to
read the flag.

> ⚠️ This service is intentionally insecure. Only ever run it inside the
> provided Docker container. Never expose it to an untrusted network.

## Run it

With Docker Compose:

```bash
docker compose up --build
```

Or with plain Docker:

```bash
docker build -t alien-ship .
docker run --rm -p 8091:8080 --cap-drop ALL --cap-add NET_RAW \
  --security-opt no-new-privileges alien-ship
```

Then open http://localhost:8091

## The challenge (student view)

The ship's **Sector Scanner** lets you ping a nav beacon by its coordinates.
The pilot's input flows straight into a shell command, so anything you append
runs on the ship's computer.

Goal: read `/flag.txt`.

## Setting a custom flag

```bash
FLAG='SAINTCON{your_custom_flag}' docker compose build
# or
docker build --build-arg FLAG='SAINTCON{your_custom_flag}' -t alien-ship .
```

## Isolation

The container is the security boundary:

- Runs as an unprivileged `pilot` user (not root).
- `read_only` root filesystem, `cap_drop: ALL` (only `NET_RAW` added back for
  `ping`), `no-new-privileges`, and memory/PID limits.
- Exploiting the injection only gives shell access *inside* this locked-down
  container, so running the challenge does not affect the host.
