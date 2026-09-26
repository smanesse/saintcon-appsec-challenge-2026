
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include <string.h>
#include <strings.h>
#include <stdint.h>
#include <ctype.h>
#include <limits.h>
#include <unistd.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <limits.h>

static int   DNS_PORT      = 8053;
static int   ADMIN_PORT    = 8080;
static int   FORWARD_PORT  = 8054;
static char  UPSTREAM_HOST[256] = "8.8.8.8";
static int   UPSTREAM_PORT = 53;
static char  ZONE_FILE[512] = "./zones/example.zone";
static char  ZONE_DIR[512]  = "./zones";
static char  ADMIN_TOKEN[256] = "";

#define T_A     1
#define T_NS    2 
#define T_CNAME 5
#define T_SOA   6
#define T_MX    15
#define T_TXT   16
#define T_AAAA  28
#define T_AXFR  252
#define T_ANY   255
#define C_IN    1

#define MAXRECS 4096
#define MAX_ANS 1024

typedef struct {
    char           name[256];
    uint16_t       type;
    uint32_t       ttl;
    unsigned char *rdata;
    uint16_t       rdlen;
    char           target[256];
} rr_t;

typedef struct {
    rr_t  recs[MAXRECS];
    int   n;
    char  origin[256];
    uint32_t default_ttl;
} zone_t;

static zone_t          *g_zone = NULL;
static pthread_mutex_t  g_zone_mu = PTHREAD_MUTEX_INITIALIZER;

static zone_t *zone_get(void) {
    pthread_mutex_lock(&g_zone_mu);
    zone_t *z = g_zone;
    pthread_mutex_unlock(&g_zone_mu);
    return z;
}
static void zone_publish(zone_t *z) {
    pthread_mutex_lock(&g_zone_mu);
    g_zone = z;
    pthread_mutex_unlock(&g_zone_mu);
}

static void put16(unsigned char *b, int *p, uint16_t v) { b[(*p)++] = v >> 8; b[(*p)++] = v & 0xff; }
static void put32(unsigned char *b, int *p, uint32_t v) {
    b[(*p)++] = (v >> 24) & 0xff; b[(*p)++] = (v >> 16) & 0xff;
    b[(*p)++] = (v >> 8) & 0xff;  b[(*p)++] = v & 0xff;
}
static uint16_t get16(const unsigned char *b, int p) { return (uint16_t)((b[p] << 8) | b[p + 1]); }

static void lower_str(char *s) { for (; *s; s++) *s = (char)tolower((unsigned char)*s); }

static int encode_name(const char *name, unsigned char *out) {
    int pos = 0;
    const char *p = name;
    if (p[0] == '\0' || (p[0] == '.' && p[1] == '\0')) { out[0] = 0; return 1; }
    while (*p) {
        const char *dot = strchr(p, '.');
        int len = dot ? (int)(dot - p) : (int)strlen(p);
        if (len <= 0) break;
        if (len > 63) len = 63;
        out[pos++] = (unsigned char)len;
        memcpy(out + pos, p, len);
        pos += len;
        if (!dot) break;
        p = dot + 1;
    }
    out[pos++] = 0;
    return pos;
}

// ---------------------------------------------------------------------------
// DNS name decompression, bounds- and loop-checked.
//
// parse_name() expands a (possibly compression-pointer-using) name from an
// incoming message into the caller's fixed-size buffer. Every read is bounded
// against 'msglen', every write is bounded against 'outcap', and compression
// pointers are required to move STRICTLY BACKWARD (a pointer must target an
// offset before the byte it lives at), which makes forward progress impossible
// to loop: each jump strictly decreases 'pos', so the number of jumps is
// bounded by the message length. A hard jump cap backs that up. Any malformed
// or hostile name (out-of-bounds read, over-long expansion, forward/self
// pointer) makes the function return -1 so the caller drops the message
// instead of overrunning a buffer or spinning forever
// (see 01_compression_pointer_loop.py).
//
// Returns the number of message bytes consumed by the name at 'offset' (for
// following the wire past it), or -1 on any malformed/hostile input.
// ---------------------------------------------------------------------------
static int parse_name(const unsigned char *msg, int msglen, int offset, char *out, int outcap) {
    int outpos = 0;
    int pos = offset;
    int consumed = 0;
    int jumped = 0;
    int jumps = 0;

    if (outcap < 1) return -1;
    while (1) {
        if (pos < 0 || pos >= msglen) return -1;          // read bound on the length byte
        unsigned char len = msg[pos];
        if ((len & 0xC0) == 0xC0) {                        // compression pointer
            if (pos + 1 >= msglen) return -1;             // second pointer byte in bounds
            int ptr = ((len & 0x3F) << 8) | msg[pos + 1];
            if (!jumped) consumed = (pos + 2) - offset;
            if (ptr >= pos) return -1;                     // must move strictly backward -> no self/forward loop
            if (++jumps > 128) return -1;                  // backstop cap on jumps
            pos = ptr;
            jumped = 1;
            continue;
        }
        if (len == 0) {
            if (!jumped) consumed = (pos + 1) - offset;
            break;
        }
        pos++;
        if (pos + len > msglen) return -1;                 // read bound on the label bytes
        for (int i = 0; i < len; i++) {
            if (outpos >= outcap - 1) return -1;           // write bound (reserve room for '.')
            out[outpos++] = (char)tolower((unsigned char)msg[pos + i]);
        }
        if (outpos >= outcap - 1) return -1;               // write bound for the separator
        out[outpos++] = '.';
        pos += len;
    }
    out[outpos] = '\0';
    return consumed;
}

// Parse the single question at offset 12. Fills qname/qtype/qclass and returns
// the offset just past the question, or -1 on a malformed message (empty
// question section, truncated header, or a bad/hostile QNAME).
static int parse_question(const unsigned char *msg, int msglen, char *qname, int qnamecap,
                          uint16_t *qtype, uint16_t *qclass) {
    if (msglen < 12) return -1;                   // header must be present
    if (get16(msg, 4) < 1) return -1;             // QDCOUNT
    int consumed = parse_name(msg, msglen, 12, qname, qnamecap);
    if (consumed < 0) return -1;                  // malformed/hostile name -> drop
    int qpos = 12 + consumed;
    if (qpos + 4 > msglen) return -1;             // qtype/qclass must be in bounds
    *qtype  = get16(msg, qpos);
    *qclass = get16(msg, qpos + 2);
    return qpos + 4;
}

static int in_zone(const char *name, const char *origin) {
    size_t ln = strlen(name), lo = strlen(origin);
    if (ln == lo && strcasecmp(name, origin) == 0) return 1;
    if (ln > lo && strcasecmp(name + ln - lo, origin) == 0 && name[ln - lo - 1] == '.') return 1;
    return 0;
}

// Records owned by the reserved `_internal` label (e.g. the runtime-injected
// `_internal TXT` - see entrypoint.sh) are operator-only data that happen to
// live in the zone file. They are never served to DNS clients: not by a zone
// transfer (VULN #3) and not by a direct query, so the only way to read them
// is the zone file on the server itself.
static int is_internal_name(const char *name) {
    return strncasecmp(name, "_internal", 9) == 0 && (name[9] == '.' || name[9] == '\0');
}

// Collect the answer RRs for (name, qtype), following CNAME chains.
//
// VULN #6: the CNAME-following loop below has no depth limit and no
// visited-name set. A zone containing a self-referential chain
// (loop1 -> loop2 -> loop1) makes this spin forever for an A/AAAA/MX/etc.
// query. Combined with udp_server()'s uncapped thread-per-datagram dispatch,
// a burst of these leaks many permanently-spinning threads and pins every
// CPU core, degrading the shared service for every other client. See
// 06_cname_chain_dos.py.
static int collect(zone_t *z, const char *name, uint16_t qtype, rr_t **out, int outcap) {
    int n = 0;
    char cur[256];
    strncpy(cur, name, sizeof(cur) - 1);
    cur[sizeof(cur) - 1] = '\0';

    while (1) {
        rr_t *cn = NULL;
        for (int i = 0; i < z->n; i++)
            if (z->recs[i].type == T_CNAME && strcasecmp(z->recs[i].name, cur) == 0) { cn = &z->recs[i]; break; }

        if (cn && qtype != T_CNAME && qtype != T_ANY) {
            if (n < outcap) out[n++] = cn;
            strncpy(cur, cn->target, sizeof(cur) - 1);
            cur[sizeof(cur) - 1] = '\0';
            if (!in_zone(cur, z->origin)) break;
            continue;
        }
        break;
    }

    if (is_internal_name(cur)) return n;         // never answer internal-only records

    for (int i = 0; i < z->n; i++) {
        if (strcasecmp(z->recs[i].name, cur) != 0) continue;
        if (qtype == T_ANY || z->recs[i].type == qtype ||
            (qtype != T_CNAME && z->recs[i].type == T_CNAME)) {
            if (n < outcap) out[n++] = &z->recs[i];
        }
    }
    return n;
}

// ---------------------------------------------------------------------------
// Response assembly.
//
// append_rr() copies one record onto the wire, bounds-checked against 'outcap':
// it refuses (returns 0, writing nothing) if the record would not fit, so it
// can never run past the end of 'out'. assemble() uses that to truncate and
// set TC instead of overflowing, on EVERY path - UDP and TCP alike. (VULN #2
// was the old TCP path serializing into a fixed stack buffer with the space
// check disabled; the check is now unconditional and append_rr is safe by
// construction.)
// ---------------------------------------------------------------------------
static int rr_wire_size(const rr_t *r) { return (int)strlen(r->name) + 2 + 10 + r->rdlen; }

// Append one RR if it fits in the remaining space; returns 1 on success, 0 if
// there is not enough room (in which case nothing is written and *pos is left
// unchanged, so the caller can truncate cleanly).
static int append_rr(unsigned char *out, int *pos, int outcap, const rr_t *r) {
    if (*pos + rr_wire_size(r) > outcap) return 0;    // no room -> caller truncates
    *pos += encode_name(r->name, out + *pos);
    put16(out, pos, r->type);
    put16(out, pos, C_IN);
    put32(out, pos, r->ttl);
    put16(out, pos, r->rdlen);
    memcpy(out + *pos, r->rdata, r->rdlen);
    *pos += r->rdlen;
    return 1;
}

// Build a full response message into 'out'. Every RR is bounds-checked against
// outcap before it is appended; if the next RR would not fit the message is
// truncated and the TC (truncated) bit is set, per RFC 1035.
static int assemble(uint16_t id, int rd, const char *qname, uint16_t qtype, uint16_t qclass,
                    rr_t **ans, int nans, int rcode,
                    unsigned char *out, int outcap) {
    int pos = 0;
    int tc = 0;
    put16(out, &pos, id);
    int flags = 0x8000 | 0x0400 | (rd ? 0x0100 : 0);
    put16(out, &pos, flags | (rcode & 0x0f));
    put16(out, &pos, 1);
    int ancount_off = pos;
    put16(out, &pos, 0);
    put16(out, &pos, 0);
    put16(out, &pos, 0);

    pos += encode_name(qname, out + pos);
    put16(out, &pos, qtype);
    put16(out, &pos, qclass);

    int written = 0;
    for (int i = 0; i < nans; i++) {
        if (!append_rr(out, &pos, outcap, ans[i])) { tc = 1; break; }
        written++;
    }

    out[ancount_off]     = (written >> 8) & 0xff;
    out[ancount_off + 1] = written & 0xff;
    if (tc) out[2] |= 0x02;
    return pos;
}

static uint16_t         g_fwd_txid = 0x0001;
static pthread_mutex_t  g_fwd_mu = PTHREAD_MUTEX_INITIALIZER;

static int forward_query(const char *qname, uint16_t qtype, uint16_t qclass,
                         uint16_t client_id, unsigned char *out, int outcap) {
    pthread_mutex_lock(&g_fwd_mu);
    int rc = -1;

    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) { pthread_mutex_unlock(&g_fwd_mu); return -1; }

    int opt = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in local;
    memset(&local, 0, sizeof(local));
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = INADDR_ANY;
    local.sin_port = htons(FORWARD_PORT);
    bind(s, (struct sockaddr *)&local, sizeof(local));

    uint16_t txid = g_fwd_txid++;

    unsigned char q[600];
    int qp = 0;
    put16(q, &qp, txid);
    put16(q, &qp, 0x0100);
    put16(q, &qp, 1); put16(q, &qp, 0); put16(q, &qp, 0); put16(q, &qp, 0);
    qp += encode_name(qname, q + qp);
    put16(q, &qp, qtype);
    put16(q, &qp, qclass);

    struct sockaddr_in up;
    memset(&up, 0, sizeof(up));
    up.sin_family = AF_INET;
    up.sin_port = htons(UPSTREAM_PORT);
    if (inet_pton(AF_INET, UPSTREAM_HOST, &up.sin_addr) != 1) {
        struct hostent *he = gethostbyname(UPSTREAM_HOST);
        if (he) memcpy(&up.sin_addr, he->h_addr_list[0], he->h_length);
    }
    sendto(s, q, qp, 0, (struct sockaddr *)&up, sizeof(up));

    struct timeval tv = { 6, 0 };
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    unsigned char buf[4096];
    time_t deadline = time(NULL) + 6;
    while (time(NULL) <= deadline) {
        struct sockaddr_in from;
        socklen_t fl = sizeof(from);
        ssize_t n = recvfrom(s, buf, sizeof(buf), 0, (struct sockaddr *)&from, &fl);
        if (n < 12) continue;
        if (get16(buf, 0) != txid) continue;
        buf[0] = (client_id >> 8) & 0xff;
        buf[1] = client_id & 0xff;
        int m = (int)n; if (m > outcap) m = outcap;
        memcpy(out, buf, m);
        rc = m;
        break;
    }

    close(s);
    pthread_mutex_unlock(&g_fwd_mu);
    return rc;
}

static int process_query(const unsigned char *msg, int msglen,
                         unsigned char *out, int outcap) {
    char qname[256] = {0};
    uint16_t qtype = 0, qclass = 0;
    if (parse_question(msg, msglen, qname, sizeof(qname), &qtype, &qclass) < 0) return 0;
    uint16_t id = get16(msg, 0);
    int rd = (msg[2] & 0x01);

    zone_t *z = zone_get();

    if (z && in_zone(qname, z->origin)) {
        rr_t *ans[MAX_ANS];
        int nans = collect(z, qname, qtype, ans, MAX_ANS);
        int rcode = (nans > 0) ? 0 : 3;                          // NXDOMAIN when empty
        return assemble(id, rd, qname, qtype, qclass, ans, nans, rcode, out, outcap);
    }

    int fl = forward_query(qname, qtype, qclass, id, out, outcap);
    if (fl > 0) return fl;

    rr_t *none[1];
    return assemble(id, rd, qname, qtype, qclass, none, 0, 2, out, outcap);
}

typedef struct { int sock; struct sockaddr_in cli; socklen_t clilen; unsigned char pkt[2048]; int len; } udp_job_t;

static void *udp_worker(void *arg) {
    udp_job_t *j = (udp_job_t *)arg;
    unsigned char resp[8192];
    int rlen = process_query(j->pkt, j->len, resp, sizeof(resp));
    if (rlen > 0)
        sendto(j->sock, resp, rlen, 0, (struct sockaddr *)&j->cli, j->clilen);
    free(j);
    return NULL;
}

static void *udp_server(void *arg) {
    int port = *(int *)arg;
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    int opt = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET; a.sin_addr.s_addr = INADDR_ANY; a.sin_port = htons(port);
    if (bind(s, (struct sockaddr *)&a, sizeof(a)) < 0) { perror("udp bind"); return NULL; }
    printf("[*] DNSM UDP listening on :%d\n", port); fflush(stdout);

    while (1) {
        udp_job_t *j = calloc(1, sizeof(udp_job_t));
        j->sock = s; j->clilen = sizeof(j->cli);
        ssize_t n = recvfrom(s, j->pkt, sizeof(j->pkt), 0,
                             (struct sockaddr *)&j->cli, &j->clilen);
        if (n <= 0) { free(j); continue; }
        j->len = (int)n;
        pthread_t t;
        if (pthread_create(&t, NULL, udp_worker, j) == 0) pthread_detach(t);
        else { udp_worker(j); }
    }
    return NULL;
}

static void send_tcp_msg(int fd, const unsigned char *msg, int len) {
    unsigned char lp[2];
    lp[0] = (len >> 8) & 0xff; lp[1] = len & 0xff;
    send(fd, lp, 2, 0);
    send(fd, msg, len, 0);
}

// AXFR: dump the zone (SOA first, all public records, SOA last).
//
// Records under the reserved `_internal` label are skipped (see
// is_internal_name()): a transfer hands a peer every public record in the
// zone, but operator-only data never leaves the server this way. (VULN #3 was
// this function dumping every record, including the runtime secret carried in
// the `_internal` TXT record, to any TCP client. See 03_axfr_no_acl.py.)
static void handle_axfr(int fd, uint16_t id, const char *qname, uint16_t qclass, zone_t *z) {
    rr_t *soa = NULL;
    for (int i = 0; i < z->n; i++) if (z->recs[i].type == T_SOA) { soa = &z->recs[i]; break; }

    unsigned char resp[16384];
    rr_t *ans[MAX_ANS];
    int n = 0;
    if (soa) ans[n++] = soa;
    for (int i = 0; i < z->n && n < MAX_ANS - 1; i++) {
        if (z->recs[i].type == T_SOA) continue;
        if (is_internal_name(z->recs[i].name)) continue;
        ans[n++] = &z->recs[i];
    }
    if (soa) ans[n++] = soa;

    int rlen = assemble(id, 0, qname, T_AXFR, qclass, ans, n, 0, resp, sizeof(resp));
    send_tcp_msg(fd, resp, rlen);
}

static void *tcp_worker(void *arg) {
    int fd = *(int *)arg;
    free(arg);

    unsigned char lp[2];
    if (recv(fd, lp, 2, MSG_WAITALL) != 2) { close(fd); return NULL; }
    int qlen = (lp[0] << 8) | lp[1];
    if (qlen <= 0 || qlen > 4096) { close(fd); return NULL; }

    unsigned char qbuf[4096];
    if (recv(fd, qbuf, qlen, MSG_WAITALL) != qlen) { close(fd); return NULL; }

    char qname[256] = {0};
    uint16_t qtype = 0, qclass = 0;
    if (parse_question(qbuf, qlen, qname, sizeof(qname), &qtype, &qclass) < 0) { close(fd); return NULL; }
    uint16_t id = get16(qbuf, 0);

    zone_t *z = zone_get();

    if (qtype == T_AXFR) {
        if (z) handle_axfr(fd, id, qname, qclass, z);
        close(fd);
        return NULL;
    }

    // Normal TCP query. The response is serialized into a buffer sized for the
    // maximum DNS-over-TCP message (a 16-bit length prefix -> 65535 bytes), and
    // assemble()/append_rr() bounds-check every record against that capacity,
    // truncating with TC rather than overflowing (VULN #2 was this path
    // building into a 1500-byte stack buffer with the space check disabled).
    unsigned char resp[65535];
    int rlen = process_query(qbuf, qlen, resp, sizeof(resp));
    if (rlen > 0) send_tcp_msg(fd, resp, rlen);
    close(fd);
    return NULL;
}

static void *tcp_server(void *arg) {
    int port = *(int *)arg;
    int s = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET; a.sin_addr.s_addr = INADDR_ANY; a.sin_port = htons(port);
    if (bind(s, (struct sockaddr *)&a, sizeof(a)) < 0) { perror("tcp bind"); return NULL; }
    if (listen(s, 16) < 0) { perror("tcp listen"); return NULL; }
    printf("[*] DNSM TCP listening on :%d\n", port); fflush(stdout);

    while (1) {
        int *fd = malloc(sizeof(int));
        *fd = accept(s, NULL, NULL);
        if (*fd < 0) { free(fd); continue; }
        pthread_t t;
        if (pthread_create(&t, NULL, tcp_worker, fd) == 0) pthread_detach(t);
        else { close(*fd); free(fd); }
    }
    return NULL;
}

static void make_fqdn(const char *tok, const char *origin, char *out) {
    if (strcmp(tok, "@") == 0) { strcpy(out, origin); lower_str(out); return; }
    size_t l = strlen(tok);
    if (l > 0 && tok[l - 1] == '.') { strcpy(out, tok); }
    else { snprintf(out, 256, "%s.%s", tok, origin); }
    lower_str(out);
}

static void strip_comment(char *line) {
    int inq = 0;
    for (char *p = line; *p; p++) {
        if (*p == '"') inq = !inq;
        else if (*p == ';' && !inq) { *p = '\0'; return; }
    }
}

static int build_txt_rdata(const char *rest, unsigned char *out) {
    int pos = 0;
    const char *p = rest;
    int emitted = 0;
    while (*p) {
        while (*p == ' ' || *p == '\t') p++;
        if (!*p) break;
        char seg[65536];
        int sl = 0;
        if (*p == '"') {
            p++;
            while (*p && *p != '"' && sl < (int)sizeof(seg) - 1) seg[sl++] = *p++;
            if (*p == '"') p++;
        } else {
            while (*p && sl < (int)sizeof(seg) - 1) seg[sl++] = *p++;
        }
        seg[sl] = '\0';
        emitted = 1;
        int off = 0;
        do {
            int chunk = sl - off; if (chunk > 255) chunk = 255;
            out[pos++] = (unsigned char)chunk;
            memcpy(out + pos, seg + off, chunk);
            pos += chunk;
            off += chunk;
        } while (off < sl);
    }
    if (!emitted) { out[pos++] = 0; }
    return pos;
}

static void zone_add(zone_t *z, const char *name, uint16_t type, uint32_t ttl,
                     const unsigned char *rdata, int rdlen, const char *target) {
    if (z->n >= MAXRECS) return;
    rr_t *r = &z->recs[z->n++];
    strncpy(r->name, name, sizeof(r->name) - 1);
    r->type = type;
    r->ttl = ttl;
    r->rdlen = (uint16_t)rdlen;
    r->rdata = malloc(rdlen > 0 ? rdlen : 1);
    if (rdlen > 0) memcpy(r->rdata, rdata, rdlen);
    r->target[0] = '\0';
    if (target) strncpy(r->target, target, sizeof(r->target) - 1);
}

static void zone_parse_text(zone_t *z, const char *text) {
    char *copy = strdup(text);
    char *save = NULL;
    for (char *line = strtok_r(copy, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        char buf[70000];
        strncpy(buf, line, sizeof(buf) - 1);
        buf[sizeof(buf) - 1] = '\0';
        strip_comment(buf);

        char *s = buf;
        while (*s == ' ' || *s == '\t' || *s == '\r') s++;
        if (*s == '\0') continue;

        if (strncmp(s, "$ORIGIN", 7) == 0) {
            char o[256];
            if (sscanf(s + 7, " %255s", o) == 1) {
                strncpy(z->origin, o, sizeof(z->origin) - 1);
                lower_str(z->origin);
            }
            continue;
        }
        if (strncmp(s, "$TTL", 4) == 0) {
            unsigned long t;
            if (sscanf(s + 4, " %lu", &t) == 1) z->default_ttl = (uint32_t)t;
            continue;
        }

        char name[256], type[16];
        int off = 0;
        if (sscanf(s, " %255s %15s %n", name, type, &off) < 2) continue;
        char *rest = s + off;
        char fqdn[256];
        make_fqdn(name, z->origin, fqdn);
        uint32_t ttl = z->default_ttl ? z->default_ttl : 300;

        if (strcasecmp(type, "A") == 0) {
            struct in_addr ia;
            char ip[64]; if (sscanf(rest, " %63s", ip) != 1) continue;
            if (inet_pton(AF_INET, ip, &ia) == 1)
                zone_add(z, fqdn, T_A, ttl, (unsigned char *)&ia, 4, NULL);
        } else if (strcasecmp(type, "AAAA") == 0) {
            struct in6_addr ia;
            char ip[128]; if (sscanf(rest, " %127s", ip) != 1) continue;
            if (inet_pton(AF_INET6, ip, &ia) == 1)
                zone_add(z, fqdn, T_AAAA, ttl, (unsigned char *)&ia, 16, NULL);
        } else if (strcasecmp(type, "CNAME") == 0 || strcasecmp(type, "NS") == 0) {
            char tgt[256]; if (sscanf(rest, " %255s", tgt) != 1) continue;
            char tf[256]; make_fqdn(tgt, z->origin, tf);
            unsigned char rd[300]; int rl = encode_name(tf, rd);
            zone_add(z, fqdn, strcasecmp(type, "CNAME") == 0 ? T_CNAME : T_NS, ttl, rd, rl, tf);
        } else if (strcasecmp(type, "MX") == 0) {
            unsigned int pref; char tgt[256];
            if (sscanf(rest, " %u %255s", &pref, tgt) != 2) continue;
            char tf[256]; make_fqdn(tgt, z->origin, tf);
            unsigned char rd[300]; int rl = 0;
            put16(rd, &rl, (uint16_t)pref);
            rl += encode_name(tf, rd + rl);
            zone_add(z, fqdn, T_MX, ttl, rd, rl, tf);
        } else if (strcasecmp(type, "TXT") == 0) {
            unsigned char *rd = malloc(70000);
            int rl = build_txt_rdata(rest, rd);
            zone_add(z, fqdn, T_TXT, ttl, rd, rl, NULL);
            free(rd);
        } else if (strcasecmp(type, "SOA") == 0) {
            char mname[256], rname[256];
            unsigned long serial, refresh, retry, expire, minimum;
            if (sscanf(rest, " %255s %255s %lu %lu %lu %lu %lu",
                       mname, rname, &serial, &refresh, &retry, &expire, &minimum) != 7) continue;
            char mf[256], rf[256]; make_fqdn(mname, z->origin, mf); make_fqdn(rname, z->origin, rf);
            unsigned char rd[700]; int rl = 0;
            rl += encode_name(mf, rd + rl);
            rl += encode_name(rf, rd + rl);
            put32(rd, &rl, (uint32_t)serial); put32(rd, &rl, (uint32_t)refresh);
            put32(rd, &rl, (uint32_t)retry);  put32(rd, &rl, (uint32_t)expire);
            put32(rd, &rl, (uint32_t)minimum);
            zone_add(z, fqdn, T_SOA, ttl, rd, rl, NULL);
        }
    }
    free(copy);
}

static char *read_file(const char *path, long *outlen) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); long len = ftell(f); fseek(f, 0, SEEK_SET);
    if (len < 0) { fclose(f); return NULL; }
    char *buf = malloc(len + 1);
    long rd = (long)fread(buf, 1, len, f);
    fclose(f);
    buf[rd] = '\0';
    if (outlen) *outlen = rd;
    return buf;
}

static zone_t *zone_new(void) {
    zone_t *z = calloc(1, sizeof(zone_t));
    strcpy(z->origin, ".");
    z->default_ttl = 300;
    return z;
}

static zone_t *zone_load_file(void) {
    zone_t *z = zone_new();
    long len = 0;
    char *text = read_file(ZONE_FILE, &len);
    if (text) { zone_parse_text(z, text); free(text); }
    else fprintf(stderr, "[!] could not read zone file %s\n", ZONE_FILE);
    return z;
}

static zone_t *zone_clone_plus(const char *text) {
    zone_t *cur = zone_get();
    zone_t *z = zone_new();
    if (cur) {
        strcpy(z->origin, cur->origin);
        z->default_ttl = cur->default_ttl;
        for (int i = 0; i < cur->n; i++) z->recs[z->n++] = cur->recs[i];
    }
    if (text) zone_parse_text(z, text);
    return z;
}

static void url_decode(const char *in, char *out, int outcap) {
    int o = 0;
    for (int i = 0; in[i] && o < outcap - 1; i++) {
        if (in[i] == '%' && isxdigit((unsigned char)in[i + 1]) && isxdigit((unsigned char)in[i + 2])) {
            char h[3] = { in[i + 1], in[i + 2], 0 };
            out[o++] = (char)strtol(h, NULL, 16);
            i += 2;
        } else if (in[i] == '+') out[o++] = ' ';
        else out[o++] = in[i];
    }
    out[o] = '\0';
}

static int query_param(const char *qs, const char *key, char *out, int outcap) {
    if (!qs) return 0;
    size_t kl = strlen(key);
    const char *p = qs;
    while (p && *p) {
        if (strncmp(p, key, kl) == 0 && p[kl] == '=') {
            const char *v = p + kl + 1;
            const char *amp = strchr(v, '&');
            char raw[4096];
            int n = amp ? (int)(amp - v) : (int)strlen(v);
            if (n > (int)sizeof(raw) - 1) n = sizeof(raw) - 1;
            memcpy(raw, v, n); raw[n] = '\0';
            url_decode(raw, out, outcap);
            return 1;
        }
        p = strchr(p, '&');
        if (p) p++;
    }
    return 0;
}

// Refuse fetch targets the DNS host should never be steered at: loopback,
// "this network", link-local (cloud instance metadata lives at 169.254.169.254),
// and multicast/reserved space.
static int fetch_addr_forbidden(struct in_addr ia) {
    uint32_t a = ntohl(ia.s_addr);
    if ((a >> 24) == 127) return 1;              // 127.0.0.0/8 loopback
    if ((a >> 24) == 0) return 1;                // 0.0.0.0/8
    if ((a >> 16) == 0xA9FE) return 1;           // 169.254.0.0/16 link-local
    if ((a >> 28) >= 0xE) return 1;              // 224.0.0.0/3 multicast + reserved
    return 0;
}

// Minimal HTTP GET client used by the "import zone from URL" ops feature.
//
// Only plain http:// is supported, the resolved destination is checked
// against fetch_addr_forbidden() before connecting, and a non-2xx reply is a
// failed fetch. The fetched body is only ever parsed as zone data - the admin
// handler never echoes it back to the caller - so pointing the import at an
// internal service can no longer read that service's response out through
// DNSM. (VULN #4 was a fetch-anything client whose body was reflected
// verbatim in the admin response. See 04_admin_ssrf.py.)
static int http_fetch(const char *url, char *out, int outcap) {
    if (strncasecmp(url, "http://", 7) != 0) return -1;
    const char *hp = url + 7;
    char host[256]; int port = 80; char path[1024] = "/";
    const char *slash = strchr(hp, '/');
    char hostport[300];
    int hl = slash ? (int)(slash - hp) : (int)strlen(hp);
    if (hl > (int)sizeof(hostport) - 1) hl = sizeof(hostport) - 1;
    memcpy(hostport, hp, hl); hostport[hl] = '\0';
    if (slash) { strncpy(path, slash, sizeof(path) - 1); }
    char *colon = strchr(hostport, ':');
    if (colon) { *colon = '\0'; port = atoi(colon + 1); }
    strncpy(host, hostport, sizeof(host) - 1);

    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    if (inet_pton(AF_INET, host, &a.sin_addr) != 1) {
        struct hostent *he = gethostbyname(host);
        if (!he) return -1;
        memcpy(&a.sin_addr, he->h_addr_list[0], he->h_length);
    }
    if (fetch_addr_forbidden(a.sin_addr)) return -1;
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return -1;
    struct timeval tv = { 5, 0 };
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    if (connect(s, (struct sockaddr *)&a, sizeof(a)) < 0) { close(s); return -1; }
    char req[1400];
    int rl = snprintf(req, sizeof(req),
                      "GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n", path, host);
    send(s, req, rl, 0);

    int total = 0;
    char raw[65536];
    while (total < (int)sizeof(raw) - 1) {
        ssize_t n = recv(s, raw + total, sizeof(raw) - 1 - total, 0);
        if (n <= 0) break;
        total += n;
    }
    close(s);
    raw[total] = '\0';
    int status = 0;
    if (sscanf(raw, "HTTP/%*s %d", &status) != 1 || status < 200 || status > 299) return -1;
    char *body = strstr(raw, "\r\n\r\n");
    body = body ? body + 4 : raw;
    int bl = (int)strlen(body);
    if (bl > outcap - 1) bl = outcap - 1;
    memcpy(out, body, bl); out[bl] = '\0';
    return bl;
}

static void http_send(int fd, const char *status, const char *body) {
    char hdr[256];
    int hl = snprintf(hdr, sizeof(hdr),
                      "HTTP/1.1 %s\r\nContent-Type: text/plain\r\nContent-Length: %zu\r\n"
                      "Connection: close\r\n\r\n", status, strlen(body));
    send(fd, hdr, hl, 0);
    send(fd, body, strlen(body), 0);
}

static int http_header(const char *req, const char *name, char *out, int outcap) {
    size_t nl = strlen(name);
    const char *p = req;
    while ((p = strcasestr(p, name)) != NULL) {
        int at_line_start = (p == req) || (p[-1] == '\n');
        if (at_line_start && p[nl] == ':') {
            const char *v = p + nl + 1;
            while (*v == ' ' || *v == '\t') v++;
            int i = 0;
            while (*v && *v != '\r' && *v != '\n' && i < outcap - 1) out[i++] = *v++;
            out[i] = '\0';
            return 1;
        }
        p += nl;
    }
    return 0;
}

static void *admin_worker(void *arg) {
    int fd = *(int *)arg;
    free(arg);

    char req[65536];
    int total = 0;
    char *header_end = NULL;
    while (total < (int)sizeof(req) - 1) {
        ssize_t n = recv(fd, req + total, sizeof(req) - 1 - total, 0);
        if (n <= 0) break;
        total += n;
        req[total] = '\0';
        if ((header_end = strstr(req, "\r\n\r\n"))) break;
    }
    req[total] = '\0';

    if (header_end) {
        long content_length = 0;
        const char *cl = strcasestr(req, "Content-Length:");
        if (cl && cl < header_end) content_length = atol(cl + strlen("Content-Length:"));
        long body_have = total - (long)(header_end + 4 - req);
        while (body_have < content_length && total < (int)sizeof(req) - 1) {
            ssize_t n = recv(fd, req + total, sizeof(req) - 1 - total, 0);
            if (n <= 0) break;
            total += n;
            body_have += n;
            req[total] = '\0';
        }
    }

    char method[16] = {0}, target[4096] = {0};
    sscanf(req, "%15s %4095s", method, target);

    char *body = strstr(req, "\r\n\r\n");
    body = body ? body + 4 : (char *)"";

    char path[2048]; strncpy(path, target, sizeof(path) - 1); path[sizeof(path) - 1] = '\0';
    char *qs = strchr(path, '?');
    if (qs) { *qs = '\0'; qs++; }

    int is_get = strcmp(method, "GET") == 0;
    int is_post = strcmp(method, "POST") == 0;

    if (strncmp(path, "/admin/", 7) == 0 && ADMIN_TOKEN[0]) {
        char tok[256] = {0};
        if (http_header(req, "X-Admin-Token", tok, sizeof(tok)) && strcmp(tok, ADMIN_TOKEN) != 0) {
            http_send(fd, "403 Forbidden", "invalid admin token\n");
            close(fd);
            return NULL;
        }
    }

    if (strcmp(path, "/health") == 0) {
        if (!is_get) { http_send(fd, "405 Method Not Allowed", "GET only\n"); close(fd); return NULL; }
        http_send(fd, "200 OK", "ok\n");
    } else if (strcmp(path, "/zone") == 0) {
        // Public zone-file transparency endpoint: returns the text of a loaded
        // zone file by name, the HTTP sibling of AXFR. No auth, by design - the
        // served files hold no secret.
        // Path-traversal fix: reject absolute paths and any ".." segment, then
        // canonicalize and confirm the resolved file still lives inside
        // ZONE_DIR before reading it (so "../secret/flag.txt" cannot escape).
        if (!is_get) { http_send(fd, "405 Method Not Allowed", "GET only\n"); close(fd); return NULL; }
        char name[4096] = {0};
        if (!query_param(qs, "name", name, sizeof(name))) {
            http_send(fd, "400 Bad Request", "need name=\n"); close(fd); return NULL;
        }
        char full[8192];
        char real_zone[PATH_MAX], real_full[PATH_MAX];
        snprintf(full, sizeof(full), "%s/%s", ZONE_DIR, name);
        size_t zl = 0;
        int ok = name[0] != '/' && strstr(name, "..") == NULL
                 && realpath(ZONE_DIR, real_zone) != NULL
                 && realpath(full, real_full) != NULL;
        if (ok) {
            zl = strlen(real_zone);
            ok = strncmp(real_full, real_zone, zl) == 0
                 && (real_full[zl] == '/' || real_full[zl] == '\0');
        }
        long len = 0;
        char *content = ok ? read_file(real_full, &len) : NULL;
        if (!ok) { http_send(fd, "403 Forbidden", "invalid zone file path\n"); }
        else if (!content) { http_send(fd, "404 Not Found", "no such zone file\n"); }
        else {
            char *out = malloc(len + 256);
            int hl = snprintf(out, 200, "--- %s ---\n", real_full);
            if (hl < 0 || hl > 199) hl = 199;           // snprintf reports the untruncated length
            memcpy(out + hl, content, len); out[hl + len] = '\0';
            http_send(fd, "200 OK", out);
            free(out); free(content);
        }
    } else if (strcmp(path, "/admin/reload") == 0) {
        if (!is_post) { http_send(fd, "405 Method Not Allowed", "POST only\n"); close(fd); return NULL; }
        zone_t *z = zone_load_file();
        zone_publish(z);
        char msg[128]; snprintf(msg, sizeof(msg), "reloaded %d records from %s\n", z->n, ZONE_FILE);
        http_send(fd, "200 OK", msg);
    } else if (strcmp(path, "/admin/import") == 0) {
        if (!is_get && !is_post) { http_send(fd, "405 Method Not Allowed", "GET or POST only\n"); close(fd); return NULL; }
        char srcurl[4096] = {0}, fpath[4096] = {0};
        if (query_param(qs, "source_url", srcurl, sizeof(srcurl))) {
            // Pull a zone update from a config-management URL. Only the record
            // count is reported; the fetched body is never reflected.
            char fetched[65536];
            int fl = http_fetch(srcurl, fetched, sizeof(fetched));
            if (fl < 0) { http_send(fd, "502 Bad Gateway", "fetch failed\n"); }
            else {
                zone_t *z = zone_clone_plus(fetched);
                zone_publish(z);
                char out[4400];
                snprintf(out, sizeof(out), "imported from %s (%d records total)\n", srcurl, z->n);
                http_send(fd, "200 OK", out);
            }
        } else if (query_param(qs, "path", fpath, sizeof(fpath))) {
            // Import a zone from a named file in the zone dir.
            // VULN #5 fix: reject absolute paths and any ".." segment, then
            // canonicalize and confirm the resolved file still lives inside
            // ZONE_DIR before reading it (so "../../etc/passwd" cannot escape).
            char full[8192];
            char real_zone[PATH_MAX], real_full[PATH_MAX];
            snprintf(full, sizeof(full), "%s/%s", ZONE_DIR, fpath);
            size_t zl = 0;
            int ok = fpath[0] != '/' && strstr(fpath, "..") == NULL
                     && realpath(ZONE_DIR, real_zone) != NULL
                     && realpath(full, real_full) != NULL;
            if (ok) {
                zl = strlen(real_zone);
                ok = strncmp(real_full, real_zone, zl) == 0
                     && (real_full[zl] == '/' || real_full[zl] == '\0');
            }
            long len = 0;
            char *content = ok ? read_file(real_full, &len) : NULL;
            if (!ok) { http_send(fd, "403 Forbidden", "invalid zone file path\n"); }
            else if (!content) { http_send(fd, "404 Not Found", "no such zone file\n"); }
            else {
                zone_t *z = zone_clone_plus(content);
                zone_publish(z);
                char *out = malloc(len + 256);
                int hl = snprintf(out, 200, "imported %s (%d records total)\n--- content ---\n", real_full, z->n);
                if (hl < 0 || hl > 199) hl = 199;           // snprintf reports the untruncated length
                memcpy(out + hl, content, len); out[hl + len] = '\0';
                http_send(fd, "200 OK", out);
                free(out); free(content);
            }
        } else if (*body && !is_post) {
            http_send(fd, "405 Method Not Allowed", "inline body import requires POST\n");
        } else if (*body) {
            zone_t *z = zone_clone_plus(body);
            zone_publish(z);
            char msg[128]; snprintf(msg, sizeof(msg), "imported inline body (%d records total)\n", z->n);
            http_send(fd, "200 OK", msg);
        } else {
            http_send(fd, "400 Bad Request", "need source_url=, path=, or a request body\n");
        }
    } else {
        http_send(fd, "404 Not Found", "unknown endpoint\n");
    }

    close(fd);
    return NULL;
}

static void *admin_server(void *arg) {
    int port = *(int *)arg;
    int s = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET; a.sin_addr.s_addr = INADDR_ANY; a.sin_port = htons(port);
    if (bind(s, (struct sockaddr *)&a, sizeof(a)) < 0) { perror("admin bind"); return NULL; }
    if (listen(s, 16) < 0) { perror("admin listen"); return NULL; }
    printf("[*] DNSM admin HTTP listening on :%d\n", port); fflush(stdout);

    while (1) {
        int *fd = malloc(sizeof(int));
        *fd = accept(s, NULL, NULL);
        if (*fd < 0) { free(fd); continue; }
        pthread_t t;
        if (pthread_create(&t, NULL, admin_worker, fd) == 0) pthread_detach(t);
        else { close(*fd); free(fd); }
    }
    return NULL;
}

static void env_int(const char *k, int *v) { const char *e = getenv(k); if (e) *v = atoi(e); }
static void env_str(const char *k, char *v, size_t n) { const char *e = getenv(k); if (e) { strncpy(v, e, n - 1); v[n - 1] = '\0'; } }

int main(void) {
    env_int("DNSM_PORT", &DNS_PORT);
    env_int("DNSM_ADMIN_PORT", &ADMIN_PORT);
    env_int("DNSM_FORWARD_PORT", &FORWARD_PORT);
    env_str("DNSM_ZONE_FILE", ZONE_FILE, sizeof(ZONE_FILE));
    env_str("DNSM_ZONE_DIR", ZONE_DIR, sizeof(ZONE_DIR));
    env_str("DNSM_ADMIN_TOKEN", ADMIN_TOKEN, sizeof(ADMIN_TOKEN));

    char upstream[300] = {0};
    env_str("DNSM_UPSTREAM", upstream, sizeof(upstream));
    if (upstream[0]) {
        char *colon = strrchr(upstream, ':');
        if (colon) { *colon = '\0'; UPSTREAM_PORT = atoi(colon + 1); }
        strncpy(UPSTREAM_HOST, upstream, sizeof(UPSTREAM_HOST) - 1);
    }

    srand((unsigned)time(NULL));

    zone_t *z = zone_load_file();
    zone_publish(z);
    printf("[*] DNSM loaded zone '%s' with %d records from %s\n", z->origin, z->n, ZONE_FILE);
    fflush(stdout);

    static int dport, aport;
    dport = DNS_PORT; aport = ADMIN_PORT;

    pthread_t tu, tt, ta;
    pthread_create(&tu, NULL, udp_server, &dport);
    pthread_create(&tt, NULL, tcp_server, &dport);
    pthread_create(&ta, NULL, admin_server, &aport);

    pthread_join(tu, NULL);
    pthread_join(tt, NULL);
    pthread_join(ta, NULL);
    return 0;
}
