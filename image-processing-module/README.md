# Image Processing Module — API Reference

IPM (`ipm`) is a small HTTP image-conversion service used for a security/CTF
course. It accepts an image, normalises it to a standard-size PNG by shelling
out to a bundled ImageMagick, and **STORs the result into the sibling File
Management Module (FMM)** over FMM's simplified FTP protocol. Converted images
can be fetched back through IPM, which RETRs them from FMM on your behalf.

> ⚠️ This service contains **intentional, deliberate vulnerabilities** for
> teaching. Do not deploy it on any network you don't fully control. This
> document describes the *functional* API so clients (and tests) can drive it.

---

## Connection

| Property | Value |
|----------|-------|
| Transport | HTTP/1.1 |
| Default bind | `0.0.0.0:8080` |
| Request bodies | `multipart/form-data` (uploads) or form/query params |
| Response bodies | JSON, or raw image bytes for `GET /image/{name}` |
| Downstream store | FMM at `ipm.fmm.host:ipm.fmm.port` (default `localhost:2121`) |

All configuration is overridable via environment variables (Spring relaxed
binding), e.g. `IPM_FMM_HOST`, `IPM_FMM_PORT`, `IPM_FMM_USER`, `IPM_FMM_PASS`,
`IPM_MAGICK`, `IPM_STDSIZE`, `SERVER_PORT`.

Converted images are, by default, stored under a generated name
`img_<hex>.png`. Supply your own with the `name` parameter.

---

## Endpoints

### `POST /convert`
Convert an uploaded image to PNG and STOR it into FMM.

- **Body:** `multipart/form-data` with a file part named `image`.
- **Optional params** (query or form): `width`, `height`, `format`, `name`.
  - `width`/`height` — target box the image is fit within (aspect preserved).
    Default `ipm.stdsize` (512).
  - `format` — output coder. Default `png`.
  - `name` — stored filename. Default a generated `img_<hex>.png`.
- If the upload is an **SVG**, its declared `width`/`height` are first read by
  IPM's own XML parser (`SvgMetadataService`) and echoed back under `svg`
  before the image is handed to ImageMagick.

**Success — `200 OK`:**
```json
{ "stored": true, "name": "img_ab12cd34.png", "bytes": 4211 }
```

### `POST /convert-url`
Fetch the source image from a URL server-side, then convert as above.

- **Params** (query or form): `url` (required), plus the same optional
  `width`/`height`/`format`/`name`.

**Success — `200 OK`:** same JSON shape as `/convert`.

### `POST /convert-batch`
Convert every image in an uploaded `.zip` archive.

- **Body:** `multipart/form-data` with a file part named `archive` (a zip).

**Success — `200 OK`:**
```json
{
  "count": 2,
  "results": [
    { "stored": true, "name": "img_11.png", "bytes": 3120 },
    { "stored": true, "name": "img_22.png", "bytes": 5077 }
  ]
}
```

### `GET /image/{name}`
Retrieve a previously stored image back from FMM (IPM RETRs it for you).

- **Success — `200 OK`:** raw PNG bytes (`Content-Type: image/png`).
- **Not found — `404 Not Found`:** `{ "error": "..." }`.

### `GET /health`
Liveness probe.

- **Reply — `200 OK`:** `ok`

---

## Status code summary

| Code | Meaning in this service |
|------|--------------------------|
| `200` | Success (conversion done / image returned / healthy) |
| `400` | Bad request — conversion or fetch failed (JSON error body) |
| `404` | Requested image could not be retrieved from FMM |
| `500` | Unexpected server error |

Conversion successfully done but the downstream STOR failing is still a
`200` — the JSON reports `"stored": false` with a `storeError` field.

---

## Minimal client session

```
# health
$ curl -s http://localhost:8080/health
ok

# convert an upload, let IPM name it
$ curl -s -F image=@cat.jpg http://localhost:8080/convert
{"stored":true,"name":"img_ab12cd34.png","bytes":4211}

# convert with an explicit stored name and size
$ curl -s -F image=@cat.jpg "http://localhost:8080/convert?name=kitten.png&width=256&height=256"
{"stored":true,"name":"kitten.png","bytes":2088}

# fetch the stored result back out of FMM through IPM
$ curl -s http://localhost:8080/image/kitten.png -o roundtrip.png

# convert from a URL
$ curl -s "http://localhost:8080/convert-url" --data-urlencode "url=http://example.com/logo.png"
{"stored":true,"name":"img_77aa88bb.png","bytes":1904}

# convert a batch
$ curl -s -F archive=@images.zip http://localhost:8080/convert-batch
{"count":2,"results":[{"stored":true,"name":"img_11.png","bytes":3120}, ...]}
```
