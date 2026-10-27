package main

import "time"

const perCharCompareDelay = 3 * time.Millisecond

func comparePassword(provided, actual string) bool {
	n := len(provided)
	if len(actual) < n {
		n = len(actual)
	}
	for i := 0; i < n; i++ {
		if provided[i] != actual[i] {
			return false
		}
		time.Sleep(perCharCompareDelay)
	}
	return len(provided) == len(actual)
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

	if comparePassword(provided, password) {
		s.authenticated = true
		return s.reply(writeSimple(s.conn, "OK"))
	}
	return s.reply(writeError(s.conn, "WRONGPASS invalid username-password pair or user is disabled."))
}
