# File Management Module — API / Protocol Reference

FMM (`fmm`) is a small FTP-like file management module used for a
security/CTF course. It speaks a **simplified subset of FTP** over a plaintext
TCP **control connection** for commands and replies, plus a **separate data
connection** (negotiated per transfer via `PASV` or `PORT`) that carries
directory listings and file contents as an opaque byte stream — so binary
transfers are byte-exact.

> ⚠️ This service contains **intentional, deliberate vulnerabilities** for
> teaching. Do not deploy it on any network you don't fully control. This
> document describes the *functional* protocol so clients (and tests) can drive
> it.

---

## Connection

| Property | Value |
|----------|-------|
| Transport | TCP |
| Default bind | `0.0.0.0:2121` |
| Encoding | ASCII / raw bytes |
| Concurrency | one thread per connection |

On connect, the server immediately sends a greeting **before** any command:

```
220 Welcome to FMM (educational build)
```

### Framing

- **Commands** are single lines sent by the client, terminated by `\n` (a
  preceding `\r` is accepted and stripped, so `\r\n` works too).
- A command is `VERB` optionally followed by a single space and an argument:
  `VERB[ ARG]`. Everything after the first space is the argument (spaces are
  preserved). The verb is **case-insensitive** (`user`, `USER`, `User` all
  work); arguments are case-sensitive.
- **Replies** are single lines of the form `NNN text`, terminated by `\r\n`,
  where `NNN` is a 3-digit status code loosely following FTP conventions.
- **Bulk payloads** (a directory listing or a file's contents) travel over a
  **separate data connection**, not the control connection. The client sets one
  up first with `PASV` (server listens, client connects) or `PORT` (client
  listens, server connects). The transfer is bracketed by a `150` reply and a
  `226` reply **on the control connection**; the payload itself is raw bytes on
  the data connection, and **end-of-file is signalled by closing the data
  connection** (no in-band terminator). This makes payloads binary-safe.

An empty line / EOF from the client closes the connection.

### Data representation (`TYPE`)

`TYPE I` (image/binary, the **default**) and `TYPE A` (ASCII) are both accepted.
Transfers are always byte-exact regardless of type — no CRLF/newline translation
is performed.

---

## Authentication

Two ways to become authenticated:

1. **`USER` + `PASS`** — classic login against `credentials.txt`
   (`username:password`, one per line, `#` comments allowed).
2. **`SESS <token>`** — resume a previously issued session by its token.

A successful `PASS` returns a **resume token** in the reply. That token can be
handed to `SESS` on another connection to become authenticated without
re-entering credentials.

Sample credentials shipped for the exercise:

| Username | Password |
|----------|----------|
| `alice`  | `password123` |
| `bob`    | `hunter2` |

Commands that require authentication (`TYPE`, `PASV`, `PORT`, `LIST`, `RETR`,
`STOR`, `CWD`) reply `530 Please login first` when called on an unauthenticated
session. (`PWD` does **not** require authentication.)

---

## Commands

### `USER <username>`
Sets the username for the pending login. Always succeeds syntactically.

- **Reply:** `331 Password required for <username>`

### `PASS <password>`
Validates `<username>:<password>` against the credentials file. On success the
session becomes authenticated and a resume token is issued.

- **Success:** `230 Login successful token=<token>`
- **Failure:** `530 Login incorrect`

`<token>` is a 5-digit decimal string (e.g. `04217`).

### `SESS <token>`
Resumes an existing session identified by `<token>` (as issued by a prior
`PASS`). No password is required — the token alone authenticates.

- **Success:** `230 Session resumed as <username>`
- **Unknown token:** `530 Unknown or expired session token`

### `PWD`
Returns the session's current working directory. Does not require auth.

- **Reply:** `257 "<current-directory>"` (initial value: `./ftproot`)

### `CWD <dir>`
Changes the working directory to `<current>/<dir>`. The target must be an
openable directory.

- **Not authenticated:** `530 Please login first`
- **Empty argument:** `501 Syntax error in parameters`
- **Not a directory / cannot open:** `550 Failed to change directory`
- **Success:** `250 Directory successfully changed`

### `TYPE <code>`
Sets the data representation. Requires auth.

- **`TYPE I`:** `200 Type set to I` (binary — the default)
- **`TYPE A`:** `200 Type set to A` (ASCII; no translation is actually applied)
- **Any other code:** `504 Command not implemented for that parameter`
- **Empty argument:** `501 Syntax error in parameters`

### `PASV`
Requests **passive mode**: the server opens a listening socket for the next
transfer and tells the client where to connect. Requires auth.

- **Success:** `227 Entering Passive Mode (h1,h2,h3,h4,p1,p2)` where the data
  port is `p1*256 + p2`.
- **Cannot open data socket:** `425 Can't open data connection`

The client should connect to the advertised host:port **before** issuing the
following `LIST`/`RETR`/`STOR`. A new `PASV` (or `PORT`) is required per transfer.

### `PORT <h1,h2,h3,h4,p1,p2>`
Requests **active mode**: names an address the server should connect **out** to
for the next transfer's data connection. Requires auth.

- **Success:** `200 PORT command successful`
- **Malformed argument:** `501 Syntax error in parameters`

### `LIST`
Lists the entries of the current working directory over the data connection.
Requires auth, and a prior `PASV`/`PORT`.

- **Not authenticated:** `530 Please login first`
- **Cannot open directory:** `450 Could not open directory`
- **No data connection negotiated:** `425 Use PASV or PORT first`
- **Success:** control replies `150` then `226`, with the body on the data
  connection:
  ```
  control: 150 Here comes the directory listing
  data:    <name>\r\n<name>\r\n...   (one entry per line, includes . and ..)
  control: 226 Directory send OK
  ```

### `RETR <filename>`
Downloads a file from the current working directory over the data connection.
Requires auth, and a prior `PASV`/`PORT`. (Every call is also logged server-side,
regardless of outcome.) There is a deliberate ~200 ms delay between the
containment check and the open.

- **Not authenticated:** `530 Please login first`
- **Empty argument:** `501 Syntax error in parameters`
- **Path resolves outside the service root:** `550 Access denied`
- **File missing / not openable:** `550 File not found`
- **No data connection negotiated:** `425 Use PASV or PORT first`
- **Success:** control replies `150` then `226`; the raw file bytes are the
  entire data connection (EOF = server closes it).

### `STOR <filename>`
Uploads a file into the current working directory over the data connection.
Requires auth, and a prior `PASV`/`PORT`.

- **Not authenticated:** `530 Please login first`
- **Empty argument:** `501 Syntax error in parameters`
- **Invalid filename:** `553 Invalid filename`
- **Cannot create file:** `550 Could not create file`
- **No data connection negotiated:** `425 Use PASV or PORT first`
- **Ready to receive:** `150 Ok to send data`

Filenames must match `^([a-zA-Z0-9_]+)+\.[a-zA-Z0-9]+$` — i.e. a name of
letters/digits/underscores, a dot, then an alphanumeric extension
(e.g. `notes.txt`, `report_1.md`). No path separators are permitted.

After the `150` reply, the client sends the file's **raw bytes** on the data
connection and then **closes it** to signal end-of-data. The bytes are written
verbatim (binary-safe — no line framing, no `.` terminator).

- **On completion:** `226 Transfer complete`

```
control: STOR notes.txt
control: 150 Ok to send data
data:    <raw file bytes...>   (client then closes the data connection)
control: 226 Transfer complete
```

### `QUIT`
Ends the session and closes the connection.

- **Reply:** `221 Goodbye` (the server then closes the socket)

### Unknown commands
Any unrecognized verb:

- **Reply:** `502 Command not implemented`

---

## Status code summary

| Code | Meaning in this service |
|------|--------------------------|
| `200` | Command OK (TYPE / PORT) |
| `220` | Greeting on connect |
| `221` | Goodbye (QUIT) |
| `226` | Transfer / listing complete |
| `227` | Entering passive mode (PASV) |
| `230` | Login / session resume successful |
| `250` | Directory changed |
| `257` | Current directory (PWD) |
| `331` | Username accepted, password required |
| `425` | No data connection (need PASV/PORT) or couldn't open one |
| `450` | Could not open directory (LIST) |
| `501` | Syntax error in parameters (empty/malformed argument) |
| `502` | Command not implemented |
| `504` | Command not implemented for that parameter (TYPE) |
| `530` | Not logged in / bad credentials / bad token |
| `550` | Access denied, file/dir not found, or create failed |
| `553` | Invalid filename (STOR) |

---

## Minimal client session

```
C: (connect)
S: 220 Welcome to FMM (educational build)
C: USER alice
S: 331 Password required for alice
C: PASS password123
S: 230 Login successful token=04217
C: PWD
S: 257 "./ftproot"
C: TYPE I
S: 200 Type set to I
C: PASV
S: 227 Entering Passive Mode (127,0,0,1,8,74)
   (client opens a data connection to 127.0.0.1:2122)
C: LIST
S: 150 Here comes the directory listing
   (data) .\r\n..\r\nwelcome.txt\r\n     ← on the data connection
S: 226 Directory send OK
C: PASV
S: 227 Entering Passive Mode (127,0,0,1,8,75)
   (client opens a data connection to 127.0.0.1:2123)
C: RETR welcome.txt
S: 150 Opening data connection
   (data) This is a sample file students can RETR.\n   ← on the data connection
S: 226 Transfer complete
C: QUIT
S: 221 Goodbye
```
