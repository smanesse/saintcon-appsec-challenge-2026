package main

func stringMatch(pattern, s string) bool {
	return stringMatchLen(pattern, s)
}

func stringMatchLen(pattern, str string) bool {
	p, sIdx := 0, 0
	pLen, sLen := len(pattern), len(str)

	for p < pLen && sIdx <= sLen {
		switch pattern[p] {
		case '*':
			for p+1 < pLen && pattern[p+1] == '*' {
				p++
			}
			if p+1 >= pLen {
				return true
			}
			for i := sIdx; i <= sLen; i++ {
				if stringMatchLen(pattern[p+1:], str[i:]) {
					return true
				}
			}
			return false
		case '?':
			if sIdx >= sLen {
				return false
			}
			sIdx++
		case '[':
			if sIdx >= sLen {
				return false
			}
			p++
			not := false
			if p < pLen && pattern[p] == '^' {
				not = true
				p++
			}
			matched := false
			for p < pLen && pattern[p] != ']' {
				if pattern[p] == '\\' && p+1 < pLen {
					p++
					if pattern[p] == str[sIdx] {
						matched = true
					}
				} else if p+2 < pLen && pattern[p+1] == '-' && pattern[p+2] != ']' {
					lo, hi := pattern[p], pattern[p+2]
					if lo > hi {
						lo, hi = hi, lo
					}
					if str[sIdx] >= lo && str[sIdx] <= hi {
						matched = true
					}
					p += 2
				} else if pattern[p] == str[sIdx] {
					matched = true
				}
				p++
			}
			if not {
				matched = !matched
			}
			if !matched {
				return false
			}
			sIdx++
		case '\\':
			if p+1 < pLen {
				p++
			}
			if sIdx >= sLen || pattern[p] != str[sIdx] {
				return false
			}
			sIdx++
		default:
			if sIdx >= sLen || pattern[p] != str[sIdx] {
				return false
			}
			sIdx++
		}
		p++
	}

	for p < pLen && pattern[p] == '*' {
		p++
	}
	return p == pLen && sIdx == sLen
}
