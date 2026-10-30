# IPM - complete vulnerability list & PoCs

All seven PoCs below target the intentionally-vulnerable Image Processing
Module. Bring the service up first (it needs the bundled ImageMagick and a
reachable FMM to STOR into), then run each script against it.

Every disclosure-class PoC targets the runtime flag file at
`/home/ctf/ipm/secret/flag.txt`, written at container start by
`entrypoint.sh` from the `IPM_FLAG` environment variable (see `../Dockerfile`;
generated fresh per deployment by the repo's `generate-secrets.sh`). It sits
outside every directory IPM's own convert/upload logic touches (ImageMagick
and Zip extraction both work in per-request temp dirs under `java.io.tmpdir`),
so recovering it only happens through one of the bugs below.

**Recommended: run everything in Docker** so neither the vulnerable service nor
the vulnerable ImageMagick build ever touches your host:

```
# builds IPM + FMM, waits for IPM, runs PoC #8 against the ipm container:
docker compose -f vuln_tests/docker-compose.yml run --build --rm poc

# run a different PoC (services already built) against the ipm container:
docker compose -f vuln_tests/docker-compose.yml run --rm \
    poc python3 01_command_injection.py ipm 8080
```

Or point a script at an already-running IPM directly:

```
python3 vuln_tests/01_command_injection.py [host] [port]     # defaults 127.0.0.1 8080
```

Each script prints what it did and whether it succeeded (`[+]` success,
`[-]` failure). A couple stand up a short-lived local HTTP listener to catch an
out-of-band callback - see their individual notes.

## The list

| # | Vulnerability | Location | PoC |
|---|---|---|---|
| 1 | Command injection (shell-out) | `ImageMagickService.convert()` | `01_command_injection.py` |
| 2 | Coder LFI / arbitrary file read | `ImageMagickService.convert()` | `02_coder_lfi.py` |
| 3 | Decompression-bomb / pixel-flood DoS | `ImageMagickService.convert()` (no `-limit`) | `03_decompression_bomb.py` |
| 6 | XXE (external-entity file read/SSRF) | `SvgMetadataService.parse()` | `06_xxe.py` |
| 7 | Billion Laughs (entity-expansion DoS) | `SvgMetadataService.parse()` | `07_billion_laughs.py` |
| 8 | CVE-2022-44268 PNG "Raw profile" file read | pinned ImageMagick `7.1.0-48` (`Dockerfile`), **not** IPM source | `08_cve_2022_44268_png_profile.py` |

### Pruned / reclassified in this pass

Several findings from earlier code-review passes were removed or folded into
the list above rather than kept as their own numbered entries:

- **Convert-from-URL SSRF (Java-side, formerly #4), removed.**
  `UrlFetchService.fetch()` opens a user-supplied URL with no scheme allow-list
  and no host validation (`file://`, `ftp://`, link-local, cloud-metadata all
  reachable; redirects followed) - a real SSRF by code review. But it isn't
  *scoreable* here: `convert-url` pipes the fetched bytes straight into the same
  ImageMagick convert path as a normal upload, so non-image content is never
  reflected back to the caller. A plain-text flag file (or any config-blob
  secret) fails to decode and its bytes never reach the HTTP response, and the
  input coder is fixed from the URL path (`deriveName`), so there's no
  text-rendering-coder trick to force either. The old PoC could only prove
  *reachability* via an error-class oracle (`IOException` "decoded a real file
  but it wasn't an image" vs `FileNotFoundException` "file never opened") - it
  never exfiltrated the runtime flag, so it scored zero against the disclosure
  contract. The only way `convert-url` ever surfaces the flag is by fetching an
  *image-shaped* file-read payload (the #8 CVE-2022-44268 PNG), which just
  reuses #8's mechanism over a different delivery vector - not a materially
  distinct, cleanly-scoreable vuln. This is also why IPM is intentionally left
  off the shared `metadata-service` SSRF target (see its README): no
  byte-reflection channel exists to bring a fetched secret back. The `fetch()`
  weakness still lives in the code (fix direction #4 below still applies if the
  feature is kept), it just no longer ships a numbered PoC, leaving a gap at #4.
- **SVG/MVG delegate SSRF (ImageMagick's own delegate, formerly #3).**
  Real by code review (no `policy.xml`, no `-limit`), but not
  network-confirmable against this Dockerfile: the Debian `bookworm` builds of
  both `inkscape` (1.2.2, the delegate this build's SVG coder actually shells
  out to) and `librsvg`/`rsvg-convert` (2.54.7) have hardened against exactly
  this class of bug and silently refuse to fetch remote `<image>` hrefs, with
  no CLI flag to re-enable it (confirmed via `strace`: the URI resolver fails
  before any `connect()` is attempted). Demonstrating it live would need a
  delegate binary from *before* that hardening landed - out of scope for a
  dependency bump. Pruned rather than catalogued as "correct by code review,
  not confirmed by the network harness" (the root cause - missing
  `policy.xml`/`-limit` - is still real and still what fix direction #3 below
  targets, via the pixel-flood PoC that *does* fire).
- **Output/stored path traversal (formerly #4).** `ConvertController`'s
  unsanitised `name` lets a client steer ImageMagick's output filename (and
  the FMM STOR target) outside the temp working dir - a real arbitrary-file-
  *write* primitive - but on its own it has no observable-over-HTTP
  consequence: nothing reads the write back, and FMM's own STOR filename
  validator rejects the cross-network half of it. A disk-exhaustion reframing
  (repeated large writes via this primitive) would either need transferring
  genuinely large payloads over the wire per request, or would just reuse
  the same "no `-limit` on resize" amplification `03_decompression_bomb.py`
  already demonstrates - not a materially distinct, cleanly-verifiable DoS in
  the time available. (A Zip Slip variant once carried this "unsanitised
  traversal write" class as a disk-exhaustion DoS, #5, now also removed - see
  the next bullet.) Pruned rather than force a redundant or unconvincing PoC.
- **Zip Slip / disk-exhaustion DoS (formerly #5), removed.** `ZipService`'s
  uncontained, uncapped extraction let a small compressed upload write an
  attacker-directed, effectively unbounded amount of data to IPM's shared
  scratch (`java.io.tmpdir`), a genuine disk-exhaustion DoS against a bounded
  `/tmp`. It was dropped from the scored set as not useful in the scoring
  scenario; the underlying `ZipService` weakness still lives in the code (fix
  direction #5 below still applies if kept), it just no longer ships a numbered
  PoC, leaving a gap at #5.

## Notes on how these interact

- **#1 and #2 both come out of the same magick shell-out.** The command line is
  built by string concatenation and run via `sh -c`, and the input token is
  passed through verbatim. Metacharacters give command execution (#1); an
  ImageMagick coder token (`label:@<path>`) gives arbitrary file read (#2).
  One construction, two bug classes - fixing only the shell (argument vector)
  still leaves the coder read, and fixing only the coders still leaves the shell.
  #1's PoC uses the injected command to `cat` the runtime flag file into the
  converted output, so it proves disclosure, not just that a command ran.
- **#3 and #7 are both DoS but at different layers.** #3 exhausts CPU/process
  budget via *ImageMagick* (a tiny SVG that renders a gigapixel canvas because no
  `-limit`/policy is set). #7 exhausts memory inside *IPM's JVM XML parser*
  (nested entity expansion). A resource cap on one does nothing for the other.
  NOTE for #3: like #7, its PoC confirms by the fate of a SEPARATE victim, not
  by the attacking request's own slowness — a lone slow/500'd bomb only proves
  the attacker hurt themselves. Under the fleet's real envelope (`cpus=1.0`,
  `pids_limit=100`, `mem_limit=1g` — mirrored in `vuln_tests/docker-compose.yml`)
  a *barrage* of gigapixel conversions saturates the single CPU and pushes the
  magick/inkscape subprocess trees past the 100-pid ceiling; that starves the
  JVM of native threads and kills Tomcat's request poller, so a normal `/convert`
  from another client is denied (times out / errors) — and stays denied, since
  IPM is not auto-restarted. `/health` is deliberately NOT the probe here: it is
  a trivial handler the scheduler keeps servicing until the poller thread itself
  dies, so the PoC watches a real `/convert` instead. Confirmed only if that
  legitimate conversion collapses; a single gigapixel request on its own does
  not deny the service.
  NOTE for #7: an un-hardened `DocumentBuilderFactory` is *necessary but not
  sufficient* on a modern JVM — the JDK enforces default caps
  (`jdk.xml.entityExpansionLimit=64000`, `jdk.xml.totalEntitySizeLimit=5e7`)
  regardless of `FEATURE_SECURE_PROCESSING`, so the classic bomb otherwise 400s
  in <1s. This module is exploitable because the JVM is deliberately
  misconfigured to lift those caps (`JAVA_TOOL_OPTIONS` in the `Dockerfile`), and
  `-XX:+ExitOnOutOfMemoryError` turns the heap exhaustion into a process exit so
  the (non-auto-restarted) container actually goes down. The PoC confirms by
  *liveness* (`/health` stops answering), not by the bomb request's own fate.
- **#8 is not in IPM's code at all - it's a SUPPLY-CHAIN bug.** #2 (coder LFI)
  and #8 (CVE-2022-44268) are both "read a host file through ImageMagick", but
  #2 is reachable because *IPM* hands a client-controlled coder token to magick,
  while #8 is reachable purely because the *pinned ImageMagick build*
  (`7.1.0-48`, see `Dockerfile`) is a known-vulnerable version - a perfectly
  normal-looking PNG with a `profile` text chunk is enough. You can audit every
  line of `ImageMagickService.java` clean and still ship #8. The fix is a
  dependency bump (ImageMagick >= `7.1.0-52`) and/or a `policy.xml` that blocks
  profile reads - not a source edit. Lesson: track your components and their
  CVEs (SBOM), because the app you didn't write is still your attack surface.

## Fix directions (brief - save the detail for when they ask)

1. **Command injection:** never build a shell string from untrusted input.
   Exec ImageMagick with an argument vector (`new ProcessBuilder(magick,
   input, "-resize", size, output)` - no `sh -c`), so metacharacters are inert.
2. **Coder LFI:** install an ImageMagick `policy.xml` that disables the
   dangerous coders (`label`, `caption`, `text`, `msl`, `mvg`, `url`, `http`,
   `https`, `ephemeral`, `@`-indirect reads), and pass a validated, server-side
   filename as the input - never a client-controlled coder token.
3. **Decompression bomb:** set ImageMagick `-limit area/memory/disk/width/height`
   (and a `policy.xml` with the same caps), and pre-check declared dimensions
   before decoding. The same `policy.xml`/`-limit` pass also closes the
   (pruned, code-review-only) SVG/MVG delegate SSRF - disable the
   `url`/`https`/`http` delegates and the `MVG`/`MSL` coders too.
4. **Convert-URL SSRF** *(PoC removed from the scored set - no byte-reflection
   channel makes it unscoreable here; the `fetch()` weakness still applies if
   `convert-url` is kept):* allow-list schemes (`http`/`https` only) and
   resolve + validate the host against a deny-list of link-local/loopback/private
   and cloud-metadata ranges; disable redirects (or re-validate after each hop);
   never open `file://`/`ftp://`.
5. **Zip Slip / disk exhaustion** *(PoC removed from the scored set; the bug
   still applies if `ZipService` is kept):* resolve each entry against the
   destination and require the canonical resolved path to start with the
   canonical destination path; reject any entry whose name contains `..` or is
   absolute. Separately, cap total entries, per-entry size, and cumulative
   decompressed size per archive (reject once the compression ratio or running
   total exceeds a sane bound) - containment alone doesn't stop a
   same-directory disk-fill.
6. **XXE:** create the `DocumentBuilderFactory` with
   `setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)`,
   `setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true)`, and disable
   external general/parameter entities (`external-general-entities` /
   `external-parameter-entities` false, `setExpandEntityReferences(false)`).
7. **Billion Laughs:** remove the JVM misconfiguration that lifts the JDK's
   default entity caps (drop the `-Djdk.xml.entityExpansionLimit=0
   -Djdk.xml.totalEntitySizeLimit=0` from `JAVA_TOOL_OPTIONS` in the
   `Dockerfile`) — the stock JDK caps (64000 expansions / 50 MB) already stop the
   bomb. Defence in depth at the parser: `FEATURE_SECURE_PROCESSING` plus
   `disallow-doctype-decl=true` neutralises nested-entity expansion regardless of
   JVM flags; alternatively enforce a hard entity-expansion / input-size limit.
8. **CVE-2022-44268 (supply chain):** upgrade the pinned ImageMagick to a fixed
   release (>= `7.1.0-52`) - the real fix. Defence-in-depth: install a
   `policy.xml` that disables profile/indirect reads, and strip metadata
   profiles on output. Process-wise: generate an SBOM and scan dependencies
   (incl. bundled native tools) against a CVE feed so an outdated `magick` is
   caught before it ships, not by a student in the lab.
