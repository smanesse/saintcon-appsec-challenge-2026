package main

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"strconv"
)


type respReader struct {
	r *bufio.Reader
}

func newRESPReader(r io.Reader) *respReader {
	return &respReader{r: bufio.NewReader(r)}
}

func (rr *respReader) readCommand() ([]string, error) {
	b, err := rr.r.ReadByte()
	if err != nil {
		return nil, err
	}

	if b != '*' {
		if err := rr.r.UnreadByte(); err != nil {
			return nil, err
		}
		line, err := rr.readLine()
		if err != nil {
			return nil, err
		}
		return splitInline(line), nil
	}

	countLine, err := rr.readLine()
	if err != nil {
		return nil, err
	}
	count, err := strconv.Atoi(countLine)
	if err != nil {
		return nil, fmt.Errorf("Protocol error: invalid multibulk length")
	}
	if count <= 0 {
		return []string{}, nil
	}
	if count > maxMultibulkLen {
		return nil, fmt.Errorf("Protocol error: invalid multibulk length")
	}

	args := make([]string, 0, count)
	for i := 0; i < count; i++ {
		tb, err := rr.r.ReadByte()
		if err != nil {
			return nil, err
		}
		if tb != '$' {
			return nil, fmt.Errorf("Protocol error: expected '$', got '%c'", tb)
		}
		val, err := rr.readBulk()
		if err != nil {
			return nil, err
		}
		args = append(args, val)
	}
	return args, nil
}

// maxBulkLen bounds a single RESP bulk string, matching real Redis's
// proto-max-bulk-len default (512MB). A declared length outside [0, maxBulkLen]
// is rejected before any allocation.
const maxBulkLen = 512 * 1024 * 1024

// maxMultibulkLen bounds the argument count of one array-form command (real
// Redis's 1024*1024 limit), so a huge *<count> can't size an allocation.
const maxMultibulkLen = 1024 * 1024

// maxLineLen bounds a single protocol line (a length header or an inline
// command), so a client that never sends \n can't grow the buffer forever.
const maxLineLen = 64 * 1024

// bulkChunk is how much of a bulk payload is read (and allocated) at a time.
// Memory therefore tracks the bytes the client has actually sent, not the
// length it merely declared.
const bulkChunk = 64 * 1024

// readBulk reads the body of a bulk string whose leading '$' has already been
// consumed: <len>\r\n<len bytes>\r\n.
//
// FIX #4 (bounded bulk length): the declared length is validated before it is
// used to size any allocation. A negative length (which previously reached
// make([]byte, n) and panicked the whole process, an unrecovered crash) and an
// oversized one (> proto-max-bulk-len, previously an unbounded up-front
// allocation / memory-exhaustion) are both rejected here with a protocol error,
// dropping only the offending connection. The payload is then read in
// bulkChunk-sized pieces rather than allocated up front, so a large declared
// length costs nothing until the bytes actually arrive.
// See vuln_tests/04_bulklen_overflow_dos.py.
func (rr *respReader) readBulk() (string, error) {
	lenLine, err := rr.readLine()
	if err != nil {
		return "", err
	}
	n, err := strconv.Atoi(lenLine)
	if err != nil {
		return "", fmt.Errorf("Protocol error: invalid bulk length")
	}
	if n < 0 || n > maxBulkLen {
		return "", fmt.Errorf("Protocol error: invalid bulk length")
	}

	var buf bytes.Buffer
	for remaining := int64(n); remaining > 0; {
		step := remaining
		if step > bulkChunk {
			step = bulkChunk
		}
		if _, err := io.CopyN(&buf, rr.r, step); err != nil {
			return "", err
		}
		remaining -= step
	}
	if _, err := rr.readLine(); err != nil {
		return "", err
	}
	return buf.String(), nil
}

// readLine reads through the next \r\n and returns the line without it. A
// line longer than maxLineLen is a protocol error.
func (rr *respReader) readLine() (string, error) {
	var line []byte
	for {
		frag, err := rr.r.ReadSlice('\n')
		if len(line)+len(frag) > maxLineLen {
			return "", fmt.Errorf("Protocol error: line too long")
		}
		line = append(line, frag...)
		if err == bufio.ErrBufferFull {
			continue
		}
		if err != nil {
			return "", err
		}
		break
	}
	// Strip trailing \r\n (or bare \n).
	return trimCRLF(string(line)), nil
}

func trimCRLF(s string) string {
	for len(s) > 0 && (s[len(s)-1] == '\n' || s[len(s)-1] == '\r') {
		s = s[:len(s)-1]
	}
	return s
}

func splitInline(line string) []string {
	var out []string
	cur := make([]byte, 0, len(line))
	flush := func() {
		if len(cur) > 0 {
			out = append(out, string(cur))
			cur = cur[:0]
		}
	}
	for i := 0; i < len(line); i++ {
		c := line[i]
		if c == ' ' || c == '\t' {
			flush()
			continue
		}
		cur = append(cur, c)
	}
	flush()
	return out
}


func writeSimple(w io.Writer, s string) error {
	_, err := fmt.Fprintf(w, "+%s\r\n", s)
	return err
}

func writeError(w io.Writer, s string) error {
	_, err := fmt.Fprintf(w, "-%s\r\n", s)
	return err
}

func writeInt(w io.Writer, n int64) error {
	_, err := fmt.Fprintf(w, ":%d\r\n", n)
	return err
}

func writeBulk(w io.Writer, s string, present bool) error {
	if !present {
		_, err := io.WriteString(w, "$-1\r\n")
		return err
	}
	_, err := fmt.Fprintf(w, "$%d\r\n%s\r\n", len(s), s)
	return err
}

func writeArray(w io.Writer, items []string) error {
	if _, err := fmt.Fprintf(w, "*%d\r\n", len(items)); err != nil {
		return err
	}
	for _, it := range items {
		if err := writeBulk(w, it, true); err != nil {
			return err
		}
	}
	return nil
}

func writeRawArrayHeader(w io.Writer, n int) error {
	_, err := fmt.Fprintf(w, "*%d\r\n", n)
	return err
}
