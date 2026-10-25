package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

type SourceFetcher struct {
	http *http.Client
	fmm  *fmmEndpoint
}

func NewSourceFetcher() *SourceFetcher {
	f := &SourceFetcher{http: newSourceClient()}
	if addr := os.Getenv("OTA_FMM"); addr != "" {
		host, port, err := net.SplitHostPort(addr)
		if err != nil {
			host, port = addr, "2121"
		}
		f.fmm = &fmmEndpoint{
			host:    host,
			port:    port,
			user:    envOr("OTA_FMM_USER", "alice"),
			pass:    envOr("OTA_FMM_PASS", "password123"),
			timeout: 20 * time.Second,
		}
	}
	return f
}

func (f *SourceFetcher) Fetch(rawurl string) (io.ReadCloser, error) {
	u, err := url.Parse(rawurl)
	if err != nil {
		return nil, fmt.Errorf("bad source_url: %w", err)
	}
	switch strings.ToLower(u.Scheme) {
	case "fmm", "ftp":
		if f.fmm == nil {
			return nil, fmt.Errorf("fmm source_url requires OTA_FMM to be configured")
		}
		body, err := f.fmm.retr(u)
		if err != nil {
			return nil, err
		}
		return io.NopCloser(bytes.NewReader(body)), nil
	default:
		resp, err := f.http.Get(rawurl)
		if err != nil {
			return nil, err
		}
		return resp.Body, nil
	}
}

func newSourceClient() *http.Client {
	resolverAddr := os.Getenv("OTA_RESOLVER")
	if resolverAddr == "" {
		return http.DefaultClient
	}
	if _, _, err := net.SplitHostPort(resolverAddr); err != nil {
		resolverAddr = net.JoinHostPort(resolverAddr, "53")
	}

	resolver := &net.Resolver{
		PreferGo: true,
		Dial: func(ctx context.Context, network, _ string) (net.Conn, error) {
			d := net.Dialer{Timeout: 5 * time.Second}
			return d.DialContext(ctx, network, resolverAddr)
		},
	}
	dialer := &net.Dialer{Timeout: 10 * time.Second, Resolver: resolver}
	return &http.Client{
		Timeout:   30 * time.Second,
		Transport: &http.Transport{DialContext: dialer.DialContext},
	}
}
