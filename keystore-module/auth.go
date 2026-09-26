package main

import (
	"crypto/sha256"
	"crypto/subtle"
)

// constantTimeMatch compares the provided password against the configured one
// without leaking timing information.
//
// FIX (non-constant-time AUTH compare): the old check compared byte-by-byte and
// returned on the first mismatch, so its running time grew with the length of
// the correct prefix — a side-channel that recovers the password one byte at a
// time (and it even amplified the leak with a per-character sleep). Both
// operands are now hashed to a fixed-width SHA-256 digest and compared with
// crypto/subtle.ConstantTimeCompare, so the comparison takes the same time
// regardless of how many leading bytes match (or of the passwords' lengths),
// revealing nothing about the correct value.
func constantTimeMatch(provided, actual string) bool {
	p := sha256.Sum256([]byte(provided))
	a := sha256.Sum256([]byte(actual))
	return subtle.ConstantTimeCompare(p[:], a[:]) == 1
}

func (s *Session) cmdAuth(args []string) bool {
	if len(args) < 2 || len(args) > 3 {
		return s.arityErr("AUTH")
	}
	provided := args[len(args)-1]

	password := s.srv.cfg.password()
	if password == "" {
		return s.reply(writeError(s.conn, "ERR Client sent AUTH, but no password is set. Did you mean AUTH <username> <password>?"))
	}

	if constantTimeMatch(provided, password) {
		s.authenticated = true
		return s.reply(writeSimple(s.conn, "OK"))
	}
	return s.reply(writeError(s.conn, "WRONGPASS invalid username-password pair or user is disabled."))
}
