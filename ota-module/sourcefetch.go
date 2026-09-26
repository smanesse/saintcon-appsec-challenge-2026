package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"syscall"
	"time"
)

// blockInternalDial is a net.Dialer Control hook for every source_url
// connection (http and fmm alike). It runs on the resolved address, so a
// hostname can't smuggle one of these past it: loopback, unspecified,
// link-local (cloud instance metadata) and multicast destinations are
// refused. Private fleet addresses stay reachable - that's where the fleet's
// own origins and file server live.
func blockInternalDial(network, address string, _ syscall.RawConn) error {
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		return err
	}
	ip := net.ParseIP(host)
	if ip == nil || ip.IsLoopback() || ip.IsUnspecified() || ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() || ip.IsInterfaceLocalMulticast() || ip.IsMulticast() {
		return fmt.Errorf("source_url destination %s is not allowed", host)
	}
	return nil
}

// SourceFetcher obtains the package bytes named by a manifest's source_url. It
// speaks two schemes:
//
//   - http/https  -> fetched with the http.Client below (whose resolver honours
//     OTA_RESOLVER, see newSourceClient).
//   - fmm/ftp     -> pulled from the fleet file server over FTP, but only when
//     OTA_FMM is configured (see fmmfetch.go). Unset -> fmm:// URLs are an
//     error, so a standalone OTA behaves exactly as before.
//
// The scheme dispatch is the whole of the opt-in gate: existing callers only
// ever use http(s) URLs, so nothing about the default path changes.
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
	case "http", "https":
		resp, err := f.http.Get(rawurl)
		if err != nil {
			return nil, err
		}
		if resp.StatusCode < 200 || resp.StatusCode > 299 {
			resp.Body.Close()
			return nil, fmt.Errorf("source_url returned HTTP %d", resp.StatusCode)
		}
		return resp.Body, nil
	default:
		return nil, errors.New("unsupported source_url scheme")
	}
}

// newSourceClient builds the http.Client used to fetch a manifest's optional
// source_url. When OTA_RESOLVER is set (the fleet's DNS server, e.g.
// "dnsm:8053"), every hostname in a source_url is resolved by asking THAT
// server rather than the container's default resolver - this is how the OTA
// server takes part in the DNSM-run naming for the fleet.
//
// Whatever address is resolved, every connection goes through
// blockInternalDial, and a fetched body is only ever stored if it matches the
// publisher's signed checksum, so a poisoned record can't turn this into a
// read of an internal service.
func newSourceClient() *http.Client {
	dialer := &net.Dialer{Timeout: 10 * time.Second, Control: blockInternalDial}
	if resolverAddr := os.Getenv("OTA_RESOLVER"); resolverAddr != "" {
		// Accept "host" (default :53) or "host:port".
		if _, _, err := net.SplitHostPort(resolverAddr); err != nil {
			resolverAddr = net.JoinHostPort(resolverAddr, "53")
		}
		// Resolver whose queries are always dialed at resolverAddr. The dial of
		// the DNS server itself uses the default resolver, so "dnsm" is
		// bootstrapped via Docker DNS and every subsequent lookup goes to DNSM.
		dialer.Resolver = &net.Resolver{
			PreferGo: true,
			Dial: func(ctx context.Context, network, _ string) (net.Conn, error) {
				d := net.Dialer{Timeout: 5 * time.Second}
				return d.DialContext(ctx, network, resolverAddr)
			},
		}
	}
	return &http.Client{
		Timeout:   30 * time.Second,
		Transport: &http.Transport{DialContext: dialer.DialContext},
	}
}
