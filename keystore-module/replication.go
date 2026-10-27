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
		authenticated: true,
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
		switch strings.ToUpper(args[0]) {
		case "PING", "REPLCONF", "PSYNC", "OK", "FULLRESYNC", "CONTINUE":
			continue
		}
		sess.dispatch(args)
	}
}
