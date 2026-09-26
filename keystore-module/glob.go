package main

// stringMatch is a Redis-style glob matcher supporting '*', '?', '[...]'
// character classes and '\' escaping.
//
// FIX #5 (algorithmic-complexity DoS): the old matcher was a faithful port of
// Redis's recursive stringmatchlen(), which recurses on every '*' and so
// backtracks exponentially on a many-'*' pattern against a non-matching key
// (KEYS a*a*...*b pegged a CPU core for seconds while holding the global
// keyspace lock). This replacement tokenizes the pattern once, then matches
// with the classic greedy single-backtrack two-pointer algorithm: each input
// byte is visited a bounded number of times, so matching is O(n*m) in the worst
// case instead of exponential, and no crafted pattern can blow it up. Semantics
// (literals, '?', '*', '[...]' with '^' negation and 'a-z' ranges, '\'
// escaping) are unchanged. See vuln_tests/05_keys_glob_dos.py.
func stringMatch(pattern, s string) bool {
	return stringMatchLen(pattern, s)
}

// globToken is one unit of a compiled pattern: either a '*' (star) or a
// single-character matcher (literal, '?', or a '[...]' class).
type globToken struct {
	star   bool
	any    bool   // '?' — matches any single byte
	isChar bool   // literal byte match
	ch     byte   // the literal byte, when isChar
	class  string // '[...]' body (between the brackets), when neither star/any/isChar
	negate bool   // class was introduced with '^'
}

// compileGlob turns a pattern into a token list. Consecutive '*' collapse into
// one, since they are equivalent for matching. ok is false for a pattern with
// an unterminated '[' class, which (as with the original matcher) matches
// nothing.
func compileGlob(pattern string) (toks []globToken, ok bool) {
	pLen := len(pattern)
	for p := 0; p < pLen; p++ {
		switch pattern[p] {
		case '*':
			if n := len(toks); n == 0 || !toks[n-1].star {
				toks = append(toks, globToken{star: true})
			}
		case '?':
			toks = append(toks, globToken{any: true})
		case '[':
			// Scan to the matching ']', capturing the class body verbatim so
			// classMatches can replay the same range/escape logic at match time.
			p++
			negate := false
			if p < pLen && pattern[p] == '^' {
				negate = true
				p++
			}
			start := p
			for p < pLen && pattern[p] != ']' {
				if pattern[p] == '\\' && p+1 < pLen {
					p++
				}
				p++
			}
			if p >= pLen {
				return nil, false
			}
			toks = append(toks, globToken{class: pattern[start:p], negate: negate})
			// p now indexes ']' (or end); the loop's p++ steps past it.
		case '\\':
			// Escape: the next byte is a literal.
			if p+1 < pLen {
				p++
			}
			toks = append(toks, globToken{isChar: true, ch: pattern[p]})
		default:
			toks = append(toks, globToken{isChar: true, ch: pattern[p]})
		}
	}
	return toks, true
}

// matchesByte reports whether a single-character token matches byte c. Star
// tokens never reach here.
func (t globToken) matchesByte(c byte) bool {
	switch {
	case t.any:
		return true
	case t.isChar:
		return t.ch == c
	default:
		return classMatches(t.class, t.negate, c)
	}
}

// classMatches evaluates a '[...]' class body (without the surrounding brackets
// or the leading '^') against byte c, honoring '\' escapes and 'a-z' ranges —
// the same logic the original inline scanner used.
func classMatches(body string, negate bool, c byte) bool {
	matched := false
	n := len(body)
	for i := 0; i < n; i++ {
		if body[i] == '\\' && i+1 < n {
			i++
			if body[i] == c {
				matched = true
			}
		} else if i+2 < n && body[i+1] == '-' && body[i+2] != ']' {
			lo, hi := body[i], body[i+2]
			if lo > hi {
				lo, hi = hi, lo
			}
			if c >= lo && c <= hi {
				matched = true
			}
			i += 2
		} else if body[i] == c {
			matched = true
		}
	}
	if negate {
		return !matched
	}
	return matched
}

// stringMatchLen matches str against the compiled pattern using a greedy
// two-pointer scan with a single remembered star position. This is the standard
// linear-time wildcard match: on a mismatch it backtracks only to just after
// the last '*', advancing the star's consumed span by one — never recursing —
// so worst-case work is bounded by O(len(pattern) * len(str)).
func stringMatchLen(pattern, str string) bool {
	toks, ok := compileGlob(pattern)
	if !ok {
		return false
	}

	ti, si := 0, 0
	starTi, starSi := -1, 0

	for si < len(str) {
		if ti < len(toks) && !toks[ti].star && toks[ti].matchesByte(str[si]) {
			ti++
			si++
		} else if ti < len(toks) && toks[ti].star {
			// Remember this star; tentatively let it match zero characters.
			starTi = ti
			starSi = si
			ti++
		} else if starTi != -1 {
			// Mismatch: let the last star consume one more character and retry.
			ti = starTi + 1
			starSi++
			si = starSi
		} else {
			return false
		}
	}

	// Any trailing tokens must all be stars for a full match.
	for ti < len(toks) && toks[ti].star {
		ti++
	}
	return ti == len(toks)
}
