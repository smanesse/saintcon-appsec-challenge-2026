package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
)

type Config struct {
	mu          sync.Mutex
	dir         string
	dbfilename  string
	requirepass string
}

func (c *Config) get(param string) (string, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	switch strings.ToLower(param) {
	case "dir":
		return c.dir, true
	case "dbfilename":
		return c.dbfilename, true
	case "requirepass":
		return c.requirepass, true
	}
	return "", false
}

func (c *Config) set(param, value string) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	switch strings.ToLower(param) {
	case "dir":
		c.dir = value
		return true
	case "dbfilename":
		c.dbfilename = value
		return true
	case "requirepass":
		c.requirepass = value
		return true
	}
	return false
}

func (c *Config) password() string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.requirepass
}

func (s *Session) cmdConfig(args []string) bool {
	if len(args) < 2 {
		return s.arityErr("CONFIG")
	}
	switch strings.ToUpper(args[1]) {
	case "GET":
		if len(args) != 3 {
			return s.arityErr("CONFIG|GET")
		}
		val, ok := s.srv.cfg.get(args[2])
		if !ok {
			return s.reply(writeArray(s.conn, []string{}))
		}
		return s.reply(writeArray(s.conn, []string{strings.ToLower(args[2]), val}))
	case "SET":
		if len(args) != 4 {
			return s.arityErr("CONFIG|SET")
		}
		if !s.srv.cfg.set(args[2], args[3]) {
			return s.reply(writeError(s.conn, fmt.Sprintf("ERR Unknown option or number of arguments for CONFIG SET - '%s'", args[2])))
		}
		return s.reply(writeSimple(s.conn, "OK"))
	default:
		return s.reply(writeError(s.conn, "ERR Unknown CONFIG subcommand"))
	}
}

func (s *Session) cmdSave(args []string) bool {
	dir, _ := s.srv.cfg.get("dir")
	name, _ := s.srv.cfg.get("dbfilename")
	path := filepath.Join(dir, name)

	snap := s.srv.store.snapshot()

	var b strings.Builder
	keys := make([]string, 0, len(snap))
	for k := range snap {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		e := snap[k]
		if e.kind == typeString {
			fmt.Fprintf(&b, "%s %s\n", k, e.str)
		}
	}

	if err := os.WriteFile(path, []byte(b.String()), 0o644); err != nil {
		return s.reply(writeError(s.conn, "ERR "+err.Error()))
	}
	return s.reply(writeSimple(s.conn, "OK"))
}
