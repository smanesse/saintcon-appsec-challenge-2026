# 👽 A.L.I.E.N. — Vulnerable Spaceship CTF Suite

A **suite** of deliberately vulnerable "alien spaceship" microservices for
hands-on security training (SAINTCON). Each challenge is a single,
self-contained service with **one intended vulnerability (class)**, runs in its
own Docker container, and hides a `SAINTCON{...}` flag reachable only by
exploiting the bug.

The ships are **independent**: each hides its own flag and stands alone — there
is no boarding pass and no dependency between ships. Solve them in any order.

> ⚠️ These services are intentionally insecure. Only run them inside their
> containers on a trusted network. Never expose them to the public internet.

## Challenges

| # | Service | Language | Difficulty |
|---|---------|----------|------------|
| 01 | Navcomputer (`01-navcomputer`) | Python | ★☆☆☆☆ |
| 02 | Cargo Manifests (`02-cargo-manifests`) | Node.js | ★★☆☆☆ |
| 03 | Reactor Core (`03-reactor-core`) | PHP | ★★★☆☆ |
| 04 | Docking Bay (`04-docking-bay`) | Java/Spring + Varnish | ★★★★★ |

Each directory has its own `Dockerfile` and a short `README.md` describing the
ship and its goal. Finding the way in is the challenge.

## Run one challenge

Each ship stands alone — build and run just the one you want:

```bash
cd 02-cargo-manifests && docker build -t alien-02 .
docker run --rm -p 8092:8080 alien-02
```

```bash
cd 01-navcomputer && docker build -t alien-01 .
docker run --rm -p 8091:8080 --cap-drop ALL --cap-add NET_RAW alien-01
```

## Run all four at once

```bash
docker compose up --build
```

| Challenge | URL |
|-----------|-----|
| 01 Navcomputer     | http://localhost:8091 |
| 02 Cargo Manifests | http://localhost:8092 |
| 03 Reactor Core    | http://localhost:8093 |
| 04 Docking Bay     | http://localhost:8094 |

(Ports are in the 8091–8094 range to avoid clashing with other local services;
change them in `docker-compose.yml` as needed.)

## Custom flags

Each ship's flag is an independent `FLAG` build arg. Override any of them:

```bash
FLAG1='SAINTCON{a}' FLAG2='SAINTCON{b}' \
FLAG3='SAINTCON{c}' FLAG4='SAINTCON{d}' docker compose build
```

## Isolation model

The **container is the security boundary** for every challenge. Winning an
exploit yields code execution or file read *inside* the container only, as an
unprivileged user, so running these does not affect the host. The Docking Bay
challenge additionally keeps its origin server and crew reviewer on
container-loopback, exposing only the Varnish edge.

## Difficulty ladder

The ships are numbered roughly by difficulty. Each step raises the bar, from a
gentle warm-up to multi-stage exploitation of the kind seen in real
engagements. Ship 01 is the beginner "hello world" ship and its README walks
you through the idea; the rest are for you to figure out. Play them in any
order you like.
