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
	dir         string // directory SAVE writes the dump into
	dbfilename  string // filename SAVE writes within dir
	requirepass string // if non-empty, AUTH is required
	baseDir     string // fixed, immutable data root SAVE must stay inside
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
		// CONFIG SET stays permissive (it only records a preference); the
		// security boundary is enforced at SAVE time, where cmdSave() confines
		// the resolved dump path to the fixed data root (c.baseDir). So a client
		// can still set this, but SAVE refuses to write outside the data dir.
		c.dir = value
		return true
	case "dbfilename":
		// As with dir, the dump filename is validated at SAVE time (no path
		// separators/traversal, fixed .kvs extension) rather than here.
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

// safeDumpPath resolves <dir>/<name> and confirms it is a legitimate dump
// target: <name> must be a bare *.kvs filename (no path separators, no ".."),
// and the fully-resolved path must stay inside the fixed data root baseDir.
// It returns an error otherwise, so SAVE can never write outside the data dir.
func (c *Config) safeDumpPath(dir, name string) (string, error) {
	if name == "" || name != filepath.Base(name) || strings.Contains(name, "..") {
		return "", fmt.Errorf("invalid dbfilename")
	}
	if filepath.Ext(name) != ".kvs" {
		return "", fmt.Errorf("dbfilename must end in .kvs")
	}

	base := c.baseDir
	if base == "" {
		base = "."
	}
	baseAbs, err := filepath.Abs(base)
	if err != nil {
		return "", fmt.Errorf("bad data dir")
	}
	// Canonicalize the base through any symlinks so the containment check can't
	// be fooled by a symlinked data root.
	if resolved, err := filepath.EvalSymlinks(baseAbs); err == nil {
		baseAbs = resolved
	}

	dirAbs, err := filepath.Abs(dir)
	if err != nil {
		return "", fmt.Errorf("bad dump dir")
	}
	// Canonicalize the requested dir the same way (when it exists) so a
	// symlinked or "."-relative dir is compared on equal footing; a
	// non-existent dir keeps its cleaned absolute form and simply won't match.
	if resolved, err := filepath.EvalSymlinks(dirAbs); err == nil {
		dirAbs = resolved
	}
	if dirAbs != baseAbs {
		return "", fmt.Errorf("dump path escapes the data directory")
	}
	return filepath.Join(dirAbs, name), nil
}

// cmdSave dumps the whole keyspace to <dir>/<dbfilename>.
//
// FIX (arbitrary file write, folded into the VULN #2 EVAL writeup): dir and
// dbfilename are still client-settable via CONFIG SET, but safeDumpPath()
// confines the resolved target to the fixed data root (cfg.baseDir) and rejects
// a dbfilename that carries path separators/traversal or a non-.kvs extension.
// A client can no longer redirect the dump to a web root, ~/.ssh, a cron dir,
// etc., so the "Redis writes a webshell / authorized_keys" primitive is closed;
// SAVE only ever writes a *.kvs file inside the data directory.
func (s *Session) cmdSave(args []string) bool {
	dir, _ := s.srv.cfg.get("dir")
	name, _ := s.srv.cfg.get("dbfilename")
	path, err := s.srv.cfg.safeDumpPath(dir, name)
	if err != nil {
		return s.reply(writeError(s.conn, "ERR "+err.Error()))
	}

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
