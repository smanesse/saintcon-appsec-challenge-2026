# KVS — KeyStore Module

KVS is a small in-memory key-value data store, in the spirit of Redis/Valkey.
It speaks the real **RESP** wire protocol (the REdis Serialization Protocol)
over a raw TCP socket, and implements a realistic slice of the Redis command
set: strings, expiries, counters, lists, hashes, keyspace scans, runtime
configuration, on-disk snapshots, replication, authentication, and server-side
Lua scripting.

> ⚠️ **This service is INTENTIONALLY VULNERABLE.** It exists to be attacked in
> a course setting. It contains deliberate, planted security bugs and disables
> protections a real data store would have. **Never deploy it, expose it to an
> untrusted network, or point it at infrastructure you don't fully control.**
> This functional reference does not discuss the planted security issues.

## Connection

| Property        | Value                                                     |
|-----------------|-----------------------------------------------------------|
| Transport       | Raw TCP                                                    |
| Protocol        | RESP (RESP2) — arrays of bulk strings in; typed replies out |
| Default bind    | `0.0.0.0:6379` (`KVS_HOST` / `KVS_PORT`, or `SERVER_PORT`) |
| Encoding        | Bytes; text examples are UTF-8                             |
| Concurrency     | Many simultaneous connections over one shared keyspace    |
| Authentication  | Off unless `KVS_REQUIREPASS` is set (then `AUTH` required) |
| Downstream deps | None — KVS is standalone                                   |

Clients may send commands in either RESP array form
(`*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n`) or the legacy inline form
(`SET foo bar\r\n`). `redis-cli -p 6379` works as a client.

### Configuration (environment variables)

| Variable          | Default            | Meaning                                   |
|-------------------|--------------------|-------------------------------------------|
| `KVS_HOST`        | `0.0.0.0`          | Bind address                              |
| `KVS_PORT`        | `6379`             | Bind port (`SERVER_PORT` overrides)       |
| `KVS_DIR`         | `.`                | Directory `SAVE` writes the dump into     |
| `KVS_DBFILENAME`  | `dump.kvs`         | Filename `SAVE` writes within `KVS_DIR`   |
| `KVS_REQUIREPASS` | *(unset)*          | If set, clients must `AUTH` before use    |

## Reply types

RESP replies are one of: **simple string** (`+OK`), **error** (`-ERR ...`),
**integer** (`:12`), **bulk string** (`$3\r\nbar` or the null bulk `$-1`), or
**array** (`*2\r\n...`).

## Command reference

### Connection / auth

| Command | Reply |
|---------|-------|
| `PING [msg]` | `+PONG`, or bulk `msg` if given |
| `ECHO msg` | bulk `msg` |
| `AUTH [user] pass` | `+OK` on success; `-WRONGPASS ...` on bad password; `-ERR ...no password is set` if none configured; `-NOAUTH ...` is returned by *other* commands until authenticated |
| `SELECT n` | `+OK` (single database; accepted and ignored) |
| `HELLO` | array describing the server (RESP2) |
| `QUIT` | `+OK`, then the connection closes |

### Strings & counters

| Command | Reply |
|---------|-------|
| `SET key value [EX secs] [PX ms]` | `+OK` |
| `GET key` | bulk value, or null bulk if missing |
| `DEL key [key ...]` | integer count removed |
| `EXISTS key [key ...]` | integer count that exist |
| `TYPE key` | `+string` / `+list` / `+hash` / `+none` |
| `INCR key` / `DECR key` | integer new value; `-ERR ...not an integer...` if the value isn't numeric |

### Expiry

| Command | Reply |
|---------|-------|
| `EXPIRE key secs` | `:1` if the key exists, `:0` otherwise |
| `TTL key` | remaining seconds; `:-1` if no expiry; `:-2` if no such key |
| `PERSIST key` | `:1` if an expiry was removed, `:0` otherwise |

### Lists

| Command | Reply |
|---------|-------|
| `LPUSH key v [v ...]` / `RPUSH key v [v ...]` | integer new length |
| `LPOP key` / `RPOP key` | bulk popped value, or null bulk if empty/missing |
| `LRANGE key start stop` | array of elements (negative indices count from the end) |
| `LLEN key` | integer length |

### Hashes

| Command | Reply |
|---------|-------|
| `HSET key f v [f v ...]` | integer count of *new* fields added |
| `HGET key field` | bulk value, or null bulk if missing |
| `HGETALL key` | array of `field, value, ...` (sorted by field) |
| `HDEL key f [f ...]` | integer count removed |

Operating on a key of the wrong kind yields `-WRONGTYPE Operation against a
key holding the wrong kind of value`.

### Keyspace

| Command | Reply |
|---------|-------|
| `KEYS pattern` | array of matching keys (glob: `*`, `?`, `[...]`) |
| `SCAN cursor [MATCH pattern] [COUNT n]` | two-element array `[cursor, [keys...]]`; this implementation returns cursor `0` and all matches in one pass |
| `DBSIZE` | integer number of keys |
| `FLUSHALL` / `FLUSHDB` | `+OK` |

### Server / admin

| Command | Reply |
|---------|-------|
| `CONFIG GET param` | array `[param, value]`; empty array for unknown params. Supported params: `dir`, `dbfilename`, `requirepass` |
| `CONFIG SET param value` | `+OK`; `-ERR Unknown option...` for unsupported params |
| `SAVE` | `+OK` after writing the keyspace snapshot to `<dir>/<dbfilename>` |
| `REPLICAOF host port` / `SLAVEOF host port` | `+OK`; the server connects to `host:port` as a replica and applies the command stream it receives. `REPLICAOF NO ONE` stops. |
| `INFO` | bulk info string |

### Scripting

| Command | Reply |
|---------|-------|
| `EVAL script numkeys [key ...] [arg ...]` | the script's return value, converted to RESP |

Scripts are Lua. `KEYS` and `ARGV` are available as 1-based tables, and
`redis.call(...)` / `redis.pcall(...)` execute a command against the keyspace
and return its reply. Lua return-value conversion follows Redis's rules
(number → integer, string → bulk, `false`/`nil` → null bulk, `{ok=...}` →
simple string, `{err=...}` → error, table → array).

## Status/reply summary

| Reply prefix | Meaning |
|--------------|---------|
| `+` | Simple string (e.g. `+OK`, `+PONG`) |
| `-` | Error (`ERR`, `WRONGTYPE`, `WRONGPASS`, `NOAUTH`) |
| `:` | Integer |
| `$` | Bulk string (`$-1` = null) |
| `*` | Array (`*-1` = null array) |

## Minimal client session

Using `redis-cli` (or `nc` with inline commands):

```
$ redis-cli -p 6379
127.0.0.1:6379> PING
PONG
127.0.0.1:6379> SET greeting "hello world"
OK
127.0.0.1:6379> GET greeting
"hello world"
127.0.0.1:6379> EXPIRE greeting 60
(integer) 1
127.0.0.1:6379> TTL greeting
(integer) 60
127.0.0.1:6379> RPUSH jobs a b c
(integer) 3
127.0.0.1:6379> LRANGE jobs 0 -1
1) "a"
2) "b"
3) "c"
127.0.0.1:6379> HSET user:1 name alice role admin
(integer) 2
127.0.0.1:6379> HGETALL user:1
1) "name"
2) "alice"
3) "role"
4) "admin"
127.0.0.1:6379> INCR counter
(integer) 1
127.0.0.1:6379> KEYS *
1) "counter"
2) "greeting"
3) "jobs"
4) "user:1"
127.0.0.1:6379> EVAL "return redis.call('GET', KEYS[1])" 1 greeting
"hello world"
```

## Build & run

```
docker build -t kvs .
docker run --rm -p 6379:6379 kvs      # for local poking only; never expose it

# functional tests, entirely in Docker (server never binds a host port):
./unit_tests/run-in-docker.sh
```
