package main

import (
	"log"
	"net"
	"os"
	"sync"
)

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

type Server struct {
	store *Store
	cfg   *Config

	replMu   sync.Mutex
	replConn net.Conn
}

func main() {
	host := envOr("KVS_HOST", "0.0.0.0")
	port := envOr("KVS_PORT", "6379")
	if p := os.Getenv("SERVER_PORT"); p != "" {
		port = p
	}

	dir := envOr("KVS_DIR", ".")
	dbfilename := envOr("KVS_DBFILENAME", "dump.kvs")

	// KVS_REQUIREPASS configures the AUTH password. When it is set, the AUTH
	// gate in Session.dispatch() refuses every unauthenticated client (see the
	// session setup in handleConn()).
	requirepass := os.Getenv("KVS_REQUIREPASS")

	srv := &Server{
		store: NewStore(),
		cfg: &Config{
			dir:         dir,
			dbfilename:  dbfilename,
			requirepass: requirepass,
		},
	}

	flag := envOr("KVS_FLAG", "FLAG{local-dev-default}")
	flagKey := envOr("KVS_FLAG_KEY", "fleet:control:flag")
	srv.store.Seed(flagKey, flag)
	log.Printf("seeded startup secret into key %q", flagKey)

	addr := net.JoinHostPort(host, port)
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatalf("cannot listen on %s: %v", addr, err)
	}
	if requirepass == "" {
		log.Printf("kvs listening on %s (NO AUTH — KVS_REQUIREPASS unset)", addr)
	} else {
		log.Printf("kvs listening on %s (AUTH required)", addr)
	}

	for {
		conn, err := ln.Accept()
		if err != nil {
			log.Printf("accept error: %v", err)
			continue
		}
		go srv.handleConn(conn)
	}
}

func (srv *Server) handleConn(conn net.Conn) {
	defer conn.Close()

	sess := &Session{
		srv:  srv,
		conn: conn,
		rr:   newRESPReader(conn),
		// A session starts authenticated only when no password is configured.
		// With KVS_REQUIREPASS set, the AUTH gate in Session.dispatch() refuses
		// every command but AUTH until cmdAuth() accepts the password. (VULN #1
		// was every session starting authenticated regardless, so a configured
		// password was never enforced. See 01_no_auth_default.py.)
		authenticated: srv.cfg.password() == "",
	}

	for {
		args, err := sess.rr.readCommand()
		if err != nil {
			return
		}
		if len(args) == 0 {
			continue
		}
		if !sess.dispatch(args) {
			return
		}
	}
}
