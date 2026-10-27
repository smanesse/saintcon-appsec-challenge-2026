# A.L.I.E.N. campaign - scoring

The aliens are scored as a **separate track** from the vulnerable modules. You do
not patch source here; you **exploit** each ship and prove it by submitting a
script that prints the ship's flag.

## What you submit

One file per ship: `aliens/<NN-name>/exploit.py`. A ready-to-edit stub ships in
each ship directory. Fill in the payload; the rest of the scaffold (connecting to
the ship, printing the result) is already there.

A.L.I.E.N. submissions are **separate** from module submissions: the cockpit
grade panel's **Submit A.L.I.E.N. exploits** action packages every released
ship's `exploit.py` (and nothing else) into its own submission, graded on its
own daily budget. Your module patches are submitted separately via **Submit
modules**. The scoreboard combines both tracks.

## How a ship is graded

For each active ship, the harness:

1. rebuilds the ship from source with a **fresh, random flag** (so a hardcoded
   `print("SAINTCON{...}")` never matches - you must exploit the live ship),
2. brings it up on a private, no-internet network,
3. runs your `exploit.py` against it in a `python:3.12-slim` container (plus the
   allowlisted packages below) with a **~15 second timeout**,
4. greps your stdout/stderr for the freshly-minted flag: found -> **SOLVED**.

Only per-ship solved/not-solved is reported back. The flag and your script's
output are never returned to you (the full log is organizer-only).

The cockpit's local **Test** action mirrors this exactly: it runs your
`exploit.py` in the same `python:3.12-slim` + allowlist image, on a private
internet-less network, with the same `TARGET_*` env and ~15s timeout — so a
local pass predicts a remote pass (it checks against the ship's default campaign
flag rather than a fresh random one).

## What your script gets

Environment variables set for `exploit.py`:

| Var           | Meaning                                              |
|---------------|------------------------------------------------------|
| `TARGET_URL`  | base URL of the ship, e.g. `http://target:8080`      |
| `TARGET_HOST` | host only, e.g. `target`                             |
| `TARGET_PORT` | port only, e.g. `8080`                               |

Ships are **independent**: each stands alone with its own flag, no boarding pass
and no gate in front of the vulnerable surface, so every ship can be solved on
its own in any order.

## What you can import

Your script runs on **Python 3.12** with the **full standard library** plus a
small, fixed allowlist of third-party packages pre-installed. That is *all* that
is available: the grading network has **no internet**, so `pip install` from
inside your exploit cannot reach a package index and will fail. Write against the
list below. The exact allowlist is `aliens/grader/requirements.txt` — the single
source of truth both the harness and the cockpit's local test runner install.

| Package          | `import`                      | What it's for                     |
|------------------|-------------------------------|-----------------------------------|
| *(stdlib)*       | `json`, `urllib`, `http.client`, `socket`, `ssl`, `base64`, `hashlib`, `hmac`, `re`, `struct`, … | always available |
| `requests`       | `import requests`             | ergonomic HTTP client             |
| `pycryptodome`   | `from Crypto... import ...`   | AES/RSA/hashing primitives        |
| `beautifulsoup4` | `from bs4 import BeautifulSoup`| HTML/XML scraping                |
| `lxml`           | `import lxml`                 | fast XML/HTML parsing             |
| `PyYAML`         | `import yaml`                 | YAML parsing/emitting             |

If you need a package that isn't here, ask the organizers — the list is
deliberately small and may grow.

## Constraints

- **~15s** wall-clock per script. Be quick; no brute force that can't finish.
- Print the flag to stdout. Extra output is fine; the harness only looks for the
  flag.

## Adding / releasing ships (organizers)

One ship is released per day. Each release is a commit that:

- adds (or flips `active: true` on) the ship's row in
  `saintcon-appsec-harness/app/aliens.yaml`,
- ensures the ship dir and its `exploit.py` stub exist here.

Set `active: false` to hide a ship that isn't released yet. IDs are stable and
start at `202651`. See `app/aliens.yaml` for the field reference.
