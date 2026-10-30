# OTA - complete vulnerability list & PoCs

The seven PoCs below target the intentionally-vulnerable OTA server, and each
one lands on a scoreable impact - it steals a real per-deployment secret, or it
denies service to the fleet. OTA holds no secret of its own, so the disclosures
steal one of two genuine per-deployment values: the `log` sibling's minted
`LOG_FLAG_VALUE` (recovered by getting a fleet member to apply a malicious
package), or the internal `metadata` service's `OTA_FLAG` (recovered by SSRF).
Both are minted fresh per deployment by `../../generate-secrets.sh`, never baked
into the repo or image.

**Recommended: run everything in Docker**, which also brings up `fmm`, `ipm`,
and `log-module` as real fleet members - each running its own copy of
`ota-agent.sh`, so the publish-chain PoCs (#2, #3, #4, #7, #9) can prove
their bugs land on a real sibling container over the network, not just in a
simulated harness:

```
# builds the whole fleet, waits for OTA, runs the flagship RCE-chain PoC:
docker compose -f vuln_tests/docker-compose.yml run --build --rm poc

# run a different PoC (services already built):
docker compose -f vuln_tests/docker-compose.yml run --rm \
    poc python3 03_tar_slip.py ota 8090
```

Or point a script at an already-running OTA server directly:

```
python3 vuln_tests/03_tar_slip.py [host] [port]   # defaults 127.0.0.1 8090
```

If the deployment configured a real `OTA_API_KEY` (a harness that sourced
`../../generate-secrets.sh`, or a team that fixed vuln #2), the publish PoCs
(#3, #4, #5, #6) need that key to get past the API-key gate - export it, or they
fall back to the compiled-in default and get a `401` (they say so, and don't
mistake it for the vuln being fixed):

```
OTA_API_KEY=<the deployment's key> python3 vuln_tests/03_tar_slip.py [host] [port]
```

The docker-compose `poc` runner passes `OTA_API_KEY` in for you, so running via
compose needs no extra step. (#2 deliberately uses only the default key - a
`401` there genuinely means #2 is fixed. #7/#9 authenticate with device
credentials, not the API key, so they don't need it.)

PoC #5 only needs `ota` itself. PoC #6 additionally needs the shared `metadata`
service (its internal-only SSRF target; see `../../metadata-service`). PoCs #2,
#3, #4, #7, #9 also need the `log` sibling (its `ota-agent.sh` has to poll,
download, and apply the published package before the secret can be read back -
give them a little longer, the poll interval is a few seconds in the test
compose).

Each script prints what it did and whether it succeeded (`[+]` success,
`[-]` failure).

## The list

| # | Vulnerability | Location | PoC |
|---|---|---|---|
| 2 | Hardcoded default API-key backdoor (accepted alongside any configured key) → default-key publish applied by a fleet member steals its runtime secret | `apiKey()` / `checkPublishAuth()` in `auth.go` | `02_default_api_key.py` |
| 3 | Tar-slip on package extraction (agent side) → symlink plant discloses a fleet host's runtime secret | `ota-agent.sh` extraction step | `03_tar_slip.py` |
| 4 | Command injection via `post_install` → RCE steals a fleet host's runtime secret | `ota-agent.sh` post-install step | `04_post_install_command_injection.py` |
| 5 | Path traversal via the `version` field → cross-module overwrite destroys a module's stored release, DoSing that module's whole fleet | `packagePath()` in `publish.go` | `05_module_version_traversal.py` |
| 6 | SSRF via manifest `source_url` -> discloses the runtime secret from the internal-only metadata service | `handlePublish()` in `publish.go` | `06_source_url_ssrf.py` |
| 7 | Unsafe object-binding deserialization (mass assignment) → trust escalation to publish, applied by a fleet member, steals its runtime secret | `handleDeviceSync()` in `handlers.go` | `07_mass_assignment_trust_escalation.py` |
| 9 | Predictable device IDs and auth tokens → guessed-token publish applied by a fleet member steals its runtime secret | `RegisterDevice()` in `store.go`, `deviceToken()` in `auth.go` | `09_predictable_device_token.py` |

## Notes on how these interact

- **#2, #7, and #9 are three independent routes to unauthenticated publish,
  cashed into a fleet-member secret through the two delivery sinks - SPLIT so
  no single sink fix flips all three.** OTA holds no secret of its own, so a bug
  that only gets you *publish* rights isn't scoreable where it stops - it has to
  be carried through to a fleet member applying the package and leaking that
  host's secret. There are only two mechanisms a published package can leak a
  sibling secret with: `post_install` RCE (#4's sink) and a tar-slip symlink
  (#3's sink). Routing every demo PoC through `post_install` (as they once
  were) meant a single `post_install` fix flipped #2/#4/#7/#9 at once while
  the publish-auth bypasses stayed exploitable. They are now split:
  - **#2** - the compiled-in default API key alone authenticates, a backdoor
    valid even when a real `OTA_API_KEY` is configured (see below). Cashes out
    via **#4's `post_install`**.
  - **#7** - mass-assigning `trusted:true` via `/sync` lets a self-registered
    device publish with no API key. Cashes out via **#3's tar-slip symlink**.
  - **#9** - a device token derived from the public salt formula lets an
    attacker publish as a device they never registered. Cashes out via **#4's
    `post_install`**.

  So the two server-side sink fixes in `publish.go` land as: validating
  `post_install` against its enum flips {#2, #4, #9}; validating archive entries
  (no symlinks/`..`) flips {#3, #7}. Neither flips all three bypasses, and
  each bypass is still scored on its own primitive - fixing a route's own bug
  (drop the default-key backdoor / decode `/sync` through a DTO / use CSPRNG
  tokens) closes *that* route regardless of either sink. (A fully
  sink-independent cash-out would re-anchor each bypass to a shared-state DoS
  like #5's; only two leak mechanisms exist, so the 2+1 split is the best
  distribution while keeping the stronger secret-disclosure bar.)
- **Checksum-only trust (no publisher signature) is real but deliberately
  unscored, leaving a gap at #1.** The manifest's `sha256` is computed by the
  same party that supplies the package, so it proves nothing about provenance.
  It once shipped as #1, but a signature check sits in front of *every* publish,
  so requiring one would close #2-#7 and #9 for any attacker who doesn't hold
  the signing key. The only way to keep scoring those independently was to hand
  the private key to the other PoCs, which models an insider rather than the
  unauthenticated remote attacker every vuln here assumes. So it was dropped
  rather than kept as a one-fix-flips-everything switch. The documented
  manifest has no signature field, and the functional suite publishes unsigned
  manifests, so adding a mandatory signature is a protocol change, not a fix.
- **#2 is a backdoor, not merely a weak default - and that's deliberate, so it
  survives the scoring model.** Every credentialed module here mints a real
  per-deployment secret at deploy time (see `../../generate-secrets.sh`), and a
  scoring harness sources it before bringing the fleet up - OTA included, so the
  `ota` service runs behind a minted `OTA_API_KEY`. A vuln phrased as "uses the
  compiled-in key *only when `OTA_API_KEY` is unset*" would therefore sit in its
  *fixed* state in every scored deployment: the default is never reachable, and
  #2 could only ever report "fixed." So `checkPublishAuth()` accepts the default
  *in addition to* the configured key (`presented == apiKey() || presented ==
  defaultAPIKey`) - a hardcoded backdoor credential that stays live behind a
  real key. This is the same move as KVS #1 (a configured password that the
  server never enforces): mint the credential to make *other* vulns scoreable,
  but leave this one fail-open so it's still exploitable. The fix is to drop the
  `|| presented == defaultAPIKey` clause and ship no working default at all.
- **#3 and #4 share a stage but are independent bugs, and both are fixed in
  submittable Go, not in the agent.** Both fire from the same "download,
  extract, run post_install" sequence in `ota-agent.sh`, but #3 is in the
  *extraction* step and #4 is in the *post-install* step. `ota-agent.sh` is
  fixed infrastructure (a shell runner - not in `submission-policy.json`'s
  source allowlist, so a team's edits to it are ignored), so the *scoreable*
  fix for each is the server-side guard in `publish.go`, which every package
  flows through before any agent sees it: reject archive entries that are
  symlinks/hardlinks/absolute/`..`-escaping (#3), and reject a `post_install`
  that isn't the documented enum (#4). These are independent (one does nothing
  for the other) and both live in already-submittable Go. `tarfile.extractall()`
  on the agent restores symlink entries with no containment, so #3 plants a
  symlink `logs/<name>` -> `../secret/flag.txt` and reads the `log` host's
  minted flag back through a plain (non-`..`) `GET /logs/{name}` - disclosure
  attributable to the tar-slip itself, distinct from `log`'s own path-traversal
  bug.
- **The uncontained extraction has a second, uncapped dimension - no
  size/ratio cap - that no longer ships a PoC.** #3 is about *where* entries
  land (no path containment); the same `tarfile.extractall()` also caps
  nothing about *how much* an entry inflates to, so a 20KB archive can expand
  to fill the disk. That decompression-bomb variant once shipped as #8 but was
  removed from the scored set (a bounded-volume DoS that wasn't useful in the
  scoring scenario); the extraction bug remains in `ota-agent.sh` and both fix
  directions (containment for #3, a size/ratio cap) still apply, leaving a gap
  at #8.
- **#5 is scored as a DoS by destroying shared state, not as a disclosure.**
  It's a "which field did we forget to check" bug: the fleet's module allowlist
  is enforced on `Module`, but `Version` flows unvalidated into the same
  `filepath.Join`, so a publish naming `module="log"` with `version="../ipm/<v>"`
  walks back out of `log/` and clobbers ipm's already-stored package. That
  stored artifact is shared state every ipm device depends on: the PoC publishes
  a legitimate ipm release, confirms a normal consumer can download and open it
  (the exact step every `ota-agent.sh` runs), overwrites it via the traversal
  with bytes that aren't a valid archive, then shows the same consumer path now
  hands every ipm device an unusable package - the whole ipm fleet is denied a
  working update, through a publish that never named ipm and carried no
  authorization for it. Confirmation is by that consumer's failure, not by the
  attacker reading its own bytes back (which would only be a self-planted-state
  primitive). It runs against `ota` alone - no sibling needed - because the
  destroyed state is OTA's own on-disk package store.
- **The downgrade/rollback angle rides #5's missing validation but isn't its
  own scored PoC.** `Store.SetLatest()` (`store.go`) overwrites `latest[module]`
  on every successful publish with no monotonicity check, so an older,
  superseded (possibly vulnerable) version can simply be republished and become
  the advertised "latest" again. On its own that's just a state change - no
  secret disclosed, nothing crashes - so it isn't catalogued as a standalone
  scored vuln; but it compounds #5: a downgrade can be smuggled in sideways
  through a module that was never the stated target (#5's traversal), and with
  no signing key anywhere, nothing stops an attacker from resurrecting a
  known-vulnerable old package through the same routes #2/#7/#9 already use to
  reach publish.
- **#6 (SSRF) makes the checksum "verification" even less meaningful.** With
  `source_url` set, the publisher doesn't even need to transfer the package
  bytes themselves - OTA fetches them server-side from wherever it's
  pointed, including addresses only the OTA server itself can reach on the
  compose network. The checksum check still runs, but it's checking
  consistency with content OTA just fetched on the attacker's behalf, which
  proves nothing about provenance either way.
- **#6 turns that same fetch into a secret-disclosure.** OTA has no secret of
  its own, so the PoC points `source_url` at the shared `metadata` service on
  the `backend` network - an internal-only host the attacker can't reach
  directly - and exfiltrates its per-deployment `OTA_FLAG` *through* OTA. The
  checksum-mismatch error is the lever: it echoes `computed`, the sha256 of the
  bytes OTA just fetched, so the attacker republishes with that hash to make
  OTA store the internal secret as a package, then downloads it back (no auth
  on `GET /updates/.../package`). The one abused feature thus both proves the
  forgery and leaks a real per-deployment value - the strongest bar in the
  scoring contract - even though OTA itself holds nothing secret. Every other
  fleet SSRF (DNSM admin import, IPM convert-url, MTA webhook) points at the
  same `metadata` target; see `../../metadata-service`.
- **#7 is a second, independent way to reach the same privileged sink #2
  guards.** Trust escalation via `/sync`'s mass assignment doesn't need the
  static API key at all - it upgrades an ordinary, self-registered device
  into something `checkPublishAuth()` accepts as a publisher. Rotating the
  default key (fixing #2) does nothing about this path; they have to be
  fixed independently, and `handleDeviceReport()` sitting right next to
  `handleDeviceSync()` in the same file is a good illustration of why: one
  decodes into a narrow DTO, the other decodes onto the live model, and nothing
  else about the two endpoints looks different from the outside.
- **#9 is a third, independent route into the same outcome #7 reaches - via
  guessable credentials instead of a self-registered device's own.**
  Predictable device IDs and a fixed, compiled-in token salt mean an
  attacker never has to register anything: derive a stranger's token from
  the public formula, use it to mass-assign `trusted: true` on *that
  device* via `/sync` (#7's primitive, someone else's identity), then
  publish through it - no X-OTA-Api-Key, no legitimately-received token,
  ever presented. It also compounds everything else the same way #7 does
  once trusted: an attacker can spoof any device's status, including
  making a fleet-wide dashboard believe a tar-slip/RCE (#3/#4) never
  happened, by overwriting the victim device's own `version`/`status`
  fields back to something reassuring right after the real agent reports
  the compromise.

## Fix directions (brief - save the detail for when they ask)

1. **Checksum-only trust** *(unscored; see the notes above):* in a real
   system, publishers sign packages and OTA verifies against a pinned public
   key, with the checksum kept only as a corruption check. Not a fix here: the
   documented manifest has no signature.
2. **Default API-key backdoor:** drop the `|| presented == defaultAPIKey`
   clause in `checkPublishAuth()` so only the configured key is accepted, and
   refuse to start (or log a loud, unmissable warning) when `OTA_API_KEY` is
   unset; never ship a working default in source or image.
3. **Tar-slip:** reject the malicious package at `/publish` in `handlePublish()`
   (`publish.go`) - walk the archive and refuse any entry that is a symlink,
   hardlink, device node, absolute path, or escapes via `..`. This is the
   *submittable* fix; `ota-agent.sh` is fixed infrastructure (not in the source
   allowlist), so hardening only the agent's `tarfile.extractall()` changes
   nothing about your score. (Agent-side, the belt-and-braces version is
   Python 3.12+'s `tarfile.extractall(filter="data")`.)
4. **Command injection:** validate `post_install` against the documented enum
   (`none`/`restart`) at `/publish` in `handlePublish()` (`publish.go`) and
   reject anything else - again the submittable fix, since `ota-agent.sh` is
   fixed infrastructure. If richer actions are ever needed, map keywords to
   fixed, hardcoded implementations - never `sh -c` on field content.
5. **Version traversal:** validate `Version` with the same rigor as
   `Module` (an allow-list charset, no `/` or `..`) before it ever reaches
   `filepath.Join`. While there, also parse and compare versions (semver or
   similar) in `Store.SetLatest()` and reject a publish whose version is not
   greater than the current latest, unless an explicit rollback
   flag is presented - the same missing validation that lets a
   traversal land in the wrong module's directory is why nothing stops a
   downgrade either.
6. **SSRF:** drop `source_url` entirely, or allow-list schemes
   (`https` only) and resolve + reject loopback/link-local/private/
   metadata ranges before fetching.
7. **Mass assignment:** decode `/sync` (and every endpoint) into a narrow
   request DTO with only the fields it means to accept, then copy those
   specific fields onto the model - never `Decode` straight onto a
   persistent struct.
8. **Decompression bomb** *(PoC removed from the scored set; the uncapped
   extraction still applies if kept):* cap total bytes written and per-entry
   size during extraction, and abort the moment either limit is exceeded.
9. **Predictable tokens:** generate IDs and tokens from a CSPRNG
   (`crypto/rand`), long enough to resist guessing, with no derivation
   from a compiled-in constant or a sequential counter.
