# metadata-service — shared internal-only target

Benign fleet infrastructure, **not a vulnerable module**. A tiny stdlib HTTP
server that stands in for the metadata / secrets endpoint a real fleet keeps on
its trusted network (cloud instance metadata, a config-management server, a
secrets sidecar). It has no vulnerabilities of its own — its only job is to be
**reachable only from inside the trusted network**, so that reaching it from
outside means a trust boundary was crossed.

Like `bridge/`, this is a supporting app rather than a scored module.

## Secrets come from the environment

Never hardcoded. A stale value in the repo can't be mistaken for a real
disclosure. Configure via env:

| Var | Effect |
|---|---|
| `META_SECRET` | default secret, served at `/secret` |
| `META_SECRET_<NAME>` | named secret, served at `/secret/<name>` (name lowercased) |
| `META_PORT` | listen port (default `9000`; `argv[1]` overrides) |

If no `META_SECRET*` var is set it falls back to the first `*_FLAG` env var it
finds, then to `FLAG{local-dev-default}`, so a bare local run still works.

## Endpoints

| Path | Returns |
|---|---|
| `GET /` | index of available secret paths (names only, no values) |
| `GET /health` | `ok` |
| `GET /secret` | the default secret (`META_SECRET`), 404 if unset |
| `GET /secret/<name>` | a named secret, 404 if unknown |

Each secret renders as a small config-shaped blob. The line carries a stable,
greppable `internal-secret=` marker plus the real value:

```
# fleet-metadata-service :: internal-only, do not expose
service=dns
internal-secret=FLAG{...}
```

## Run it standalone

```
META_SECRET_DNS='FLAG{demo}' python3 metadata_service.py 9000
curl -s localhost:9000/secret/dns
```

## Wiring a module in

The service is meant to sit on an **internal-only** Docker network that outside
clients are not attached to — only fleet modules bridge to it:

```yaml
services:
  metadata:
    image: python:3.12-slim
    working_dir: /srv
    volumes:
      - ../metadata-service:/srv:ro
    environment:
      META_SECRET_<MOD>: "${<MOD>_FLAG:-FLAG{local-dev-default}}"
    command: ["python3", "metadata_service.py", "9000"]
    networks: [backend]        # internal-only

  <module>:
    networks: [dmz, backend]   # a fleet module bridges both

  client:
    networks: [dmz]            # outside client only on dmz -> cannot reach metadata
```
