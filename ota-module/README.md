# OTA - Fleet Update Module

OTA is a small over-the-air (OTA) update distribution server for a fleet of
devices/services. A publisher pushes a versioned **update package** (a
`.tar.gz`) for a named module along with a manifest describing it; device
agents in the fleet poll the server, discover when a new version is
available for their module, and download it. It's modeled on real
embedded/IoT update backends (Mender, balena, SWUpdate): a lightweight,
protocol-first "check for updates, then fetch" backend, not a full
device-management console.

> ⚠️ **This service is intentionally, deliberately vulnerable.** It must
> never be deployed or exposed to any network you don't fully control.
> Nothing below documents or hints at the planted security issues.

## Connection

| | |
|---|---|
| Transport | HTTP/1.1 |
| Default bind | `:8090` (override with `OTA_PORT`) |
| Encoding | JSON bodies, except `POST /publish` (`multipart/form-data`) and the package download (`application/gzip`) |
| Concurrency | One process, one goroutine per request (Go's standard `net/http`) |
| Storage | Published packages/manifests are written under `OTA_DATA_DIR` (default `./data`) |
| Downstream dependency | None to run standalone. Composes with any module that ships an OTA agent (`file-management-module`, `image-processing-module`, `log-module` each poll this server for their own updates) |
| Name resolution | Optional: set `OTA_RESOLVER` (`host` or `host:port`, e.g. `dnsm:8053`) to resolve manifest `source_url` hosts through the fleet DNS server instead of the container default. Unset -> default resolver (standalone) |
| File-server source | Optional: set `OTA_FMM` (`host` or `host:port`, e.g. `fmm:2121`) to allow `fmm://`/`ftp://` manifest `source_url`s, pulled from the fleet file server over FTP. `OTA_FMM_USER`/`OTA_FMM_PASS` supply the login (default `alice`/`password123`). Unset -> `fmm://` URLs are rejected (standalone) |

## Fleet

OTA manages updates for a fixed, known set of modules: `fmm`, `ipm`, `log`.
`POST /publish` only accepts one of these as the target `module`.

## Manifest

Every publish is described by a small JSON manifest:

```json
{
  "module": "log",
  "version": "1.2.3",
  "sha256": "<hex sha-256 of the package bytes>",
  "post_install": "restart",
  "source_url": "https://example.internal/builds/log-1.2.3.tar.gz"
}
```

| Field | Required | Meaning |
|---|---|---|
| `module` | yes | Target module - one of `fmm`, `ipm`, `log` |
| `version` | yes | Free-form version string for this release |
| `sha256` | yes | SHA-256 checksum of the package bytes, used to catch transfer corruption |
| `post_install` | no | A maintenance keyword to run after the package is applied. Documented values: `"none"` (default) or `"restart"` |
| `source_url` | no | If set, OTA fetches the package bytes itself from this URL instead of requiring an uploaded file. `http(s)://` is always supported (host resolved through the fleet DNS server when `OTA_RESOLVER` is set); `fmm://[host[:port]]/path` pulls from the fleet file server over FTP, but only when `OTA_FMM` is configured |

## Endpoints

### `POST /publish`

Publish a new version of a module. `multipart/form-data` body:

- `manifest` - the manifest JSON, as text.
- `package` - the `.tar.gz` file (omit only if the manifest sets `source_url`).

Header: `X-OTA-Api-Key: <key>` is required (see your deployment's configured
key; the environment variable is `OTA_API_KEY`).

| Status | Meaning |
|---|---|
| `201 Created` | Stored; body is the published package record |
| `400 Bad Request` | Missing/invalid manifest, unknown module, missing package/source, or checksum mismatch |
| `401 Unauthorized` | Missing or wrong `X-OTA-Api-Key` |
| `405 Method Not Allowed` | Anything but `POST` |
| `502 Bad Gateway` | `source_url` was set but couldn't be fetched |
| `500 Internal Server Error` | Local storage failure |

### `GET /updates/{module}/latest`

Returns the package record currently advertised as the latest version for
`module`. This is what a device agent polls.

| Status | Meaning |
|---|---|
| `200 OK` | Package record (manifest + size + published_at) |
| `404 Not Found` | Nothing has been published for this module yet |

### `GET /updates/{module}/{version}/package`

Downloads the raw `.tar.gz` bytes for a specific published version.
Response headers include `Content-Type: application/gzip`,
`Content-Length`, and `X-OTA-SHA256` (the manifest's checksum).

| Status | Meaning |
|---|---|
| `200 OK` | Package bytes |
| `404 Not Found` | No such module/version |

### `POST /devices/register`

Register a new fleet device/agent. Body: `{"module": "log"}` (which module
this device runs). No authentication required - this is how a fresh agent
introduces itself to the fleet.

| Status | Meaning |
|---|---|
| `201 Created` | `{"id", "token", "module"}` - keep the token, it authenticates this device from now on |
| `400 Bad Request` | Missing `module` |
| `405 Method Not Allowed` | Anything but `POST` |

### `POST /devices/{id}/report`

A device reports its currently-installed version and status. Header:
`Authorization: Bearer <token>` (the token from registration). Body:
`{"version": "1.2.3", "status": "applied"}`.

| Status | Meaning |
|---|---|
| `200 OK` | `{"status": "recorded"}` |
| `400 Bad Request` | Invalid body |
| `401 Unauthorized` | Missing/wrong token |
| `404 Not Found` | No such device |
| `405 Method Not Allowed` | Anything but `POST` |

### `POST /devices/{id}/sync`

Attach additional self-reported metadata to a device's record beyond the
narrow fields `/report` accepts (for example free-text status detail).
Same header (`Authorization: Bearer <token>`) as `/report`. Body: any JSON
object; recognised fields are merged onto the device's record.

| Status | Meaning |
|---|---|
| `200 OK` | The device's full, updated record |
| `400 Bad Request` | Invalid body |
| `401 Unauthorized` | Missing/wrong token |
| `404 Not Found` | No such device |
| `405 Method Not Allowed` | Anything but `POST` |

### `GET /devices`

List every registered device and its last-known state. Header:
`X-OTA-Api-Key: <key>` required.

| Status | Meaning |
|---|---|
| `200 OK` | JSON array of device records |
| `401 Unauthorized` | Missing/wrong `X-OTA-Api-Key` |

### `GET /health`

Liveness check, no authentication.

| Status | Meaning |
|---|---|
| `200 OK` | `{"status": "ok"}` |

## Status code summary

| Code | Used by |
|---|---|
| 200 | `GET /updates/.../package`, `/devices/.../report`, `/devices/.../sync`, `GET /devices`, `/health` |
| 201 | `POST /publish`, `POST /devices/register` |
| 400 | `POST /publish`, `POST /devices/register`, `/devices/.../report`, `/devices/.../sync` |
| 401 | `POST /publish`, `/devices/.../report`, `/devices/.../sync`, `GET /devices` |
| 404 | `GET /updates/...`, `/devices/.../report`, `/devices/.../sync` |
| 405 | Any wrong-method request to a `POST`-only or `GET`-only route |
| 500 | `POST /publish` (local storage failure) |
| 502 | `POST /publish` (bad `source_url`) |

## Minimal client session

```
# A device agent introduces itself to the fleet
$ curl -s -X POST http://ota:8090/devices/register -d '{"module":"log"}'
{"id":"device-1","token":"9f2c...","module":"log"}

# A publisher pushes a new version of "log"
$ sha256sum log-1.0.0.tar.gz
b5b3...  log-1.0.0.tar.gz
$ curl -s -X POST http://ota:8090/publish \
    -H 'X-OTA-Api-Key: <key>' \
    -F 'manifest={"module":"log","version":"1.0.0","sha256":"b5b3...","post_install":"restart"}' \
    -F 'package=@log-1.0.0.tar.gz'
{"manifest":{...},"size":18421,"published_at":"..."}

# The device polls for its module's latest version
$ curl -s http://ota:8090/updates/log/latest
{"manifest":{"module":"log","version":"1.0.0",...},"size":18421,...}

# ...and downloads it
$ curl -s http://ota:8090/updates/log/1.0.0/package -o package.tar.gz

# ...then reports back once applied
$ curl -s -X POST http://ota:8090/devices/device-1/report \
    -H 'Authorization: Bearer 9f2c...' \
    -d '{"version":"1.0.0","status":"applied"}'
{"status":"recorded"}
```
