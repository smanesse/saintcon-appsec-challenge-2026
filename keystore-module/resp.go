package main

import (
	"bufio"
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

func (rr *respReader) readBulk() (string, error) {
	lenLine, err := rr.readLine()
	if err != nil {
		return "", err
	}
	n, err := strconv.Atoi(lenLine)
	if err != nil {
		return "", fmt.Errorf("Protocol error: invalid bulk length")
	}

	buf := make([]byte, n)
	if _, err := io.ReadFull(rr.r, buf); err != nil {
		return "", err
	}
	if _, err := rr.readLine(); err != nil {
		return "", err
	}
	return string(buf), nil
}

func (rr *respReader) readLine() (string, error) {
	line, err := rr.r.ReadString('\n')
	if err != nil {
		return "", err
	}
	line = trimCRLF(line)
	return line, nil
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
