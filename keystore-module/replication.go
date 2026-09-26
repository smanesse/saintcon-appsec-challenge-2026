package main

import (
	"log"
	"net"
	"strings"
	"time"
)

type replicaConn struct {
	net.Conn
}

func (replicaConn) Write(p []byte) (int, error) { return len(p), nil }

// cmdReplicaOf handles REPLICAOF <host> <port> (and its SLAVEOF alias).
//
// The server dials out to the host:port the client names and applies the RESP
// command stream that peer sends back. Two things bound the trust that places
// in the peer: REPLICAOF itself sits behind the AUTH gate (only an
// authenticated client can point the server at a master), and the stream is
// filtered through replicableCommands below - a master may only replay plain
// keyspace writes, never scripting, configuration, persistence, replication or
// auth commands. (VULN #3 was the stream being dispatched as a fully trusted
// session, so a rogue master could run EVAL / CONFIG / SAVE over the link. See
// 03_replicaof_injection.py.)
//
// REPLICAOF NO ONE stops replication: it closes the active link (if any),
// which ends that goroutine's read loop, and starts nothing new. A fresh
// REPLICAOF <host> <port> likewise closes any existing link before dialing
// the new one, so at most one replication goroutine is ever running.
func (s *Session) cmdReplicaOf(args []string) bool {
	if len(args) != 3 {
		return s.arityErr("REPLICAOF")
	}
	host, port := args[1], args[2]
	s.srv.stopReplication()
	if strings.EqualFold(host, "no") && strings.EqualFold(port, "one") {
		return s.reply(writeSimple(s.conn, "OK"))
	}

	go s.srv.replicateFrom(net.JoinHostPort(host, port))
	return s.reply(writeSimple(s.conn, "OK"))
}

func (srv *Server) stopReplication() {
	srv.replMu.Lock()
	conn := srv.replConn
	srv.replConn = nil
	srv.replMu.Unlock()
	if conn != nil {
		conn.Close()
	}
}

// replicableCommands is the set of commands a replication master may stream.
// Anything else (EVAL, CONFIG, SAVE, REPLICAOF/SLAVEOF, AUTH, FLUSHALL/FLUSHDB,
// ...) is dropped: those are operator actions a replication peer has no
// business issuing on this server's behalf.
var replicableCommands = map[string]bool{
	"SET": true, "DEL": true, "EXPIRE": true, "PERSIST": true,
	"INCR": true, "DECR": true,
	"LPUSH": true, "RPUSH": true, "LPOP": true, "RPOP": true,
	"HSET": true, "HDEL": true,
	"SELECT": true,
}

// replicateFrom connects to a replication master and applies whatever command
// stream it sends. Runs in its own goroutine; registers itself as the active
// link so a later REPLICAOF (or REPLICAOF NO ONE) can stop it.
func (srv *Server) replicateFrom(addr string) {
	conn, err := net.DialTimeout("tcp", addr, 5*time.Second)
	if err != nil {
		log.Printf("replicaof: cannot connect to master %s: %v", addr, err)
		return
	}
	defer conn.Close()

	srv.replMu.Lock()
	srv.replConn = conn
	srv.replMu.Unlock()
	defer func() {
		srv.replMu.Lock()
		if srv.replConn == conn {
			srv.replConn = nil
		}
		srv.replMu.Unlock()
	}()

	log.Printf("replicaof: connected to master %s, applying its command stream", addr)

	conn.Write([]byte("PING\r\n"))
	conn.Write([]byte("REPLCONF listening-port 0\r\n"))
	conn.Write([]byte("PSYNC ? -1\r\n"))

	rc := replicaConn{Conn: conn}
	sess := &Session{
		srv:           srv,
		conn:          rc,
		rr:            newRESPReader(conn),
		authenticated: true, // bounded by replicableCommands above
	}

	for {
		conn.SetReadDeadline(time.Now().Add(30 * time.Second))
		args, err := sess.rr.readCommand()
		if err != nil {
			log.Printf("replicaof: master stream ended: %v", err)
			return
		}
		if len(args) == 0 {
			continue
		}
		// Skip handshake chatter a benign master might send back, and refuse
		// anything that isn't a plain keyspace write.
		name := strings.ToUpper(args[0])
		if !replicableCommands[name] {
			switch name {
			case "PING", "REPLCONF", "PSYNC", "OK", "FULLRESYNC", "CONTINUE":
			default:
				log.Printf("replicaof: dropping non-replicable command %q from master", name)
			}
			continue
		}
		sess.dispatch(args)
	}
}
