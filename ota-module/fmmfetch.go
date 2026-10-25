package main

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"strconv"
	"strings"
	"time"
)

type fmmEndpoint struct {
	host, port string
	user, pass string
	timeout    time.Duration
}

func (e *fmmEndpoint) retr(u *url.URL) ([]byte, error) {
	host, port := e.host, e.port
	if u.Host != "" {
		if h, p, err := net.SplitHostPort(u.Host); err == nil {
			host, port = h, p
		} else {
			host, port = u.Host, "2121"
		}
	}
	path := strings.TrimPrefix(u.Path, "/")
	if path == "" {
		return nil, fmt.Errorf("fmm source_url has no file path")
	}

	deadline := time.Now().Add(e.timeout)
	ctrl, err := net.DialTimeout("tcp", net.JoinHostPort(host, port), e.timeout)   
	if err != nil {
		return nil, fmt.Errorf("fmm connect: %w", err)
	}
	defer ctrl.Close()
	_ = ctrl.SetDeadline(deadline)
	br := bufio.NewReader(ctrl)
 
	if _, err := expect(br, "220"); err != nil {
		return nil, err
	}
	if err := say(ctrl, br, "USER "+e.user, "331"); err != nil {
		return nil, err
	}
	if err := say(ctrl, br, "PASS "+e.pass, "230"); err != nil {
		return nil, err
	}
	if err := say(ctrl, br, "TYPE I", "200"); err != nil {
		return nil, err
	}

	dataHost, dataPort, err := pasv(ctrl, br, host)
	if err != nil {
		return nil, err
	}
	data, err := net.DialTimeout("tcp", net.JoinHostPort(dataHost, dataPort), e.timeout)
	if err != nil {
		return nil, fmt.Errorf("fmm data connect: %w", err)
	}
	defer data.Close()
	_ = data.SetDeadline(deadline)

	if err := say(ctrl, br, "RETR "+path, "150"); err != nil {
		return nil, err
	}
	body, err := readToEOF(data)
	if err != nil {
		return nil, fmt.Errorf("fmm data read: %w", err)
	}
	if _, err := expect(br, "226"); err != nil {
		return nil, err
	}
	_, _ = ctrl.Write([]byte("QUIT\r\n"))
	return body, nil
}

func say(w net.Conn, br *bufio.Reader, line, code string) error {
	if _, err := w.Write([]byte(line + "\r\n")); err != nil {
		return err
	}
	_, err := expect(br, code)
	return err
}

func expect(br *bufio.Reader, code string) (string, error) {
	line, err := br.ReadString('\n')
	if err != nil {
		return "", fmt.Errorf("fmm read reply: %w", err)
	}
	line = strings.TrimRight(line, "\r\n")
	if !strings.HasPrefix(line, code) {
		return line, fmt.Errorf("fmm expected %s, got %q", code, line)
	}
	return line, nil
}

func pasv(w net.Conn, br *bufio.Reader, ctrlHost string) (string, string, error) {
	line, err := say2(w, br, "PASV", "227")
	if err != nil {
		return "", "", err
	}
	open := strings.IndexByte(line, '(')
	close := strings.IndexByte(line, ')')
	if open < 0 || close < 0 || close < open {
		return "", "", fmt.Errorf("fmm bad PASV reply: %q", line)
	}
	parts := strings.Split(line[open+1:close], ",")
	if len(parts) != 6 {
		return "", "", fmt.Errorf("fmm bad PASV tuple: %q", line)
	}
	nums := make([]int, 6)
	for i, p := range parts {
		n, err := strconv.Atoi(strings.TrimSpace(p))
		if err != nil {
			return "", "", fmt.Errorf("fmm bad PASV number %q: %w", p, err)
		}
		nums[i] = n
	}
	host := fmt.Sprintf("%d.%d.%d.%d", nums[0], nums[1], nums[2], nums[3])
	if host == "0.0.0.0" {
		host = ctrlHost
	}
	port := strconv.Itoa(nums[4]*256 + nums[5])
	return host, port, nil
}

func say2(w net.Conn, br *bufio.Reader, line, code string) (string, error) {
	if _, err := w.Write([]byte(line + "\r\n")); err != nil {
		return "", err
	}
	return expect(br, code)
}

func readToEOF(c net.Conn) ([]byte, error) {
	var out []byte
	buf := make([]byte, 64<<10)
	for {
		n, err := c.Read(buf)
		if n > 0 {
			out = append(out, buf[:n]...)
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				return out, nil
			}
			return out, err
		}
	}
}
