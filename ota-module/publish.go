package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

// allowedModules is the known fleet: the only modules this OTA server is
// meant to manage updates for. It's checked against the manifest's Module
// field on publish.
var allowedModules = map[string]bool{
	"fmm": true,
	"ipm": true,
	"log": true,
}

// versionPattern is the accepted shape of a Version: a single path-safe token
// (letters, digits, '.', '_', '+', '-'), starting with an alphanumeric.
var versionPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$`)

// validVersion reports whether v is safe to use as a directory name under a
// module's package directory: no separators and no ".." anywhere.
func validVersion(v string) bool {
	return versionPattern.MatchString(v) && !strings.Contains(v, "..")
}

// packagePath builds the on-disk location for a stored package. Callers must
// have validated module against allowedModules and version with
// validVersion(), so the result always stays inside <dataDir>/packages/<module>.
// (VULNS.md #5 was Version reaching this Join unvalidated: "../ipm/<v>" in a
// publish for "log" overwrote ipm's stored release.)
func packagePath(dataDir, module, version string) string {
	return filepath.Join(dataDir, "packages", module, version)
}

// publishPubKey returns the pinned publisher key (OTA_PUBLISH_PUBKEY: the raw
// 32-byte ed25519 public key, base64 - see ../generate-secrets.sh), or nil if
// none is configured. A configured but malformed key is fatal: failing open
// on a typo would silently disable signature checks.
var publishPubKey = sync.OnceValue(func() ed25519.PublicKey {
	b64 := os.Getenv("OTA_PUBLISH_PUBKEY")
	if b64 == "" {
		log.Printf("WARNING: OTA_PUBLISH_PUBKEY is not set - package signatures are NOT verified (dev mode)")
		return nil
	}
	raw, err := base64.StdEncoding.DecodeString(b64)
	if err != nil || len(raw) != ed25519.PublicKeySize {
		log.Fatalf("OTA_PUBLISH_PUBKEY must be a base64 32-byte ed25519 public key")
	}
	return ed25519.PublicKey(raw)
})

// verifyManifestSignature checks the publisher's ed25519 signature over
// "module:version:sha256" against the pinned key. The checksum binds the
// signature to the package bytes, so a package is accepted only if the holder
// of the publishing private key vouched for exactly this content. (VULNS.md #1
// was trusting a checksum carried inside the same attacker-supplied manifest.)
func verifyManifestSignature(m Manifest) bool {
	pub := publishPubKey()
	if pub == nil {
		return true // no key pinned: dev mode, warned about at startup
	}
	sig, err := base64.StdEncoding.DecodeString(m.Signature)
	if err != nil || len(sig) != ed25519.SignatureSize {
		return false
	}
	msg := []byte(m.Module + ":" + m.Version + ":" + m.SHA256)
	return ed25519.Verify(pub, msg, sig)
}

// Extraction limits enforced on a published archive (see
// validatePackageArchive).
const (
	maxArchiveEntries  = 10000
	maxArchiveUnpacked = 512 << 20
)

// validatePackageArchive inspects a package the way a device will extract it
// and rejects anything unsafe to unpack: every entry must be a regular file or
// a directory with a relative path that stays inside the extraction directory
// - no symlinks, hardlinks or device nodes, no absolute paths, no ".."
// segments - and the archive must stay within entry-count/size limits. A
// payload that isn't a tar archive at all is left opaque (devices only ever
// extract archives). bzip2/xz-wrapped tars, which devices would also open,
// are refused outright: packages are .tar.gz. (VULNS.md #3 was the fleet
// extracting whatever a package contained, so a "../" symlink entry planted a
// link to a host's secret.)
func validatePackageArchive(data []byte) error {
	var r io.Reader = bytes.NewReader(data)
	switch {
	case len(data) >= 2 && data[0] == 0x1f && data[1] == 0x8b:
		gz, err := gzip.NewReader(r)
		if err != nil {
			return errors.New("corrupt gzip stream")
		}
		defer gz.Close()
		r = gz
	case bytes.HasPrefix(data, []byte("BZh")), bytes.HasPrefix(data, []byte("\xfd7zXZ\x00")):
		return errors.New("unsupported compression: packages must be .tar.gz")
	}
	tr := tar.NewReader(io.LimitReader(r, maxArchiveUnpacked+1))
	var total int64
	for n := 0; ; n++ {
		hdr, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			if n == 0 {
				return nil // not a tar archive: opaque payload
			}
			return errors.New("corrupt archive")
		}
		if n >= maxArchiveEntries {
			return errors.New("archive has too many entries")
		}
		switch hdr.Typeflag {
		case tar.TypeReg, tar.TypeRegA, tar.TypeDir:
		default:
			return fmt.Errorf("archive entry %q is not a regular file or directory", hdr.Name)
		}
		name := strings.ReplaceAll(hdr.Name, "\\", "/")
		clean := path.Clean(name)
		if path.IsAbs(name) || clean == ".." || strings.HasPrefix(clean, "../") {
			return fmt.Errorf("archive entry %q escapes the extraction directory", hdr.Name)
		}
		total += hdr.Size
		if total > maxArchiveUnpacked {
			return errors.New("archive unpacks too large")
		}
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func handlePublish(store *Store, dataDir string, fetcher *SourceFetcher) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !checkPublishAuth(r, store) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}

		if err := r.ParseMultipartForm(64 << 20); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad multipart body: " + err.Error()})
			return
		}

		manifestText := r.FormValue("manifest")
		if manifestText == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing manifest field"})
			return
		}
		var m Manifest
		if err := json.Unmarshal([]byte(manifestText), &m); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid manifest JSON: " + err.Error()})
			return
		}
		if m.Module == "" || m.Version == "" || m.SHA256 == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "manifest requires module, version, sha256"})
			return
		}
		if !allowedModules[m.Module] {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unknown module (fleet is fmm, ipm, log)"})
			return
		}
		if !validVersion(m.Version) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid version (allowed: letters, digits, . _ + -)"})
			return
		}
		// post_install is a keyword, never a command: only the documented
		// values are accepted. (VULNS.md #4 was devices handing whatever
		// string the manifest carried to `sh -c`.)
		switch m.PostInstall {
		case "", "none", "restart":
		default:
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "post_install must be \"none\" or \"restart\""})
			return
		}
		// The manifest must carry a valid publisher signature (checked before
		// any source_url fetch); the bytes are then checked against the signed
		// checksum below.
		if !verifyManifestSignature(m) {
			writeJSON(w, http.StatusForbidden, map[string]string{"error": "missing or invalid package signature"})
			return
		}

		// Obtain the package bytes: either the uploaded multipart part, or -
		// if the manifest names a source_url - fetched server-side through the
		// SourceFetcher (http(s) or fmm:// only, loopback/link-local refused,
		// non-2xx is a failure). The fetched bytes are never reflected back:
		// they're only stored if they match the signed checksum. (VULNS.md #6
		// was an unrestricted fetch whose checksum-mismatch error echoed the
		// fetched bytes' SHA-256, letting a publisher learn it, re-publish with
		// that checksum and download an internal service's response.)
		var data []byte
		if m.SourceURL != "" {
			body, err := fetcher.Fetch(m.SourceURL)
			if err != nil {
				writeJSON(w, http.StatusBadGateway, map[string]string{"error": "source_url fetch failed: " + err.Error()})
				return
			}
			defer body.Close()
			data, err = io.ReadAll(io.LimitReader(body, 256<<20))
			if err != nil {
				writeJSON(w, http.StatusBadGateway, map[string]string{"error": "source_url read failed: " + err.Error()})
				return
			}
		} else {
			file, _, err := r.FormFile("package")
			if err != nil {
				writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing package file (or source_url)"})
				return
			}
			defer file.Close()
			data, err = io.ReadAll(io.LimitReader(file, 256<<20))
			if err != nil {
				writeJSON(w, http.StatusBadRequest, map[string]string{"error": "failed reading package: " + err.Error()})
				return
			}
		}

		sum := sha256.Sum256(data)
		got := hex.EncodeToString(sum[:])
		if got != m.SHA256 {
			// Never echo the computed digest: for a source_url package that
			// is a hash oracle over bytes the publisher was never shown.
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error":    "checksum mismatch",
				"expected": m.SHA256,
			})
			return
		}

		if err := validatePackageArchive(data); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "rejected package: " + err.Error()})
			return
		}

		dir := packagePath(dataDir, m.Module, m.Version)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		manifestBytes, _ := json.MarshalIndent(m, "", "  ")
		if err := os.WriteFile(filepath.Join(dir, "manifest.json"), manifestBytes, 0o644); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		if err := os.WriteFile(filepath.Join(dir, "package.tar.gz"), data, 0o644); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}

		pkg := &Package{Manifest: m, Size: len(data), PublishedAt: time.Now()}
		store.SetLatest(m.Module, m.Version, pkg)

		writeJSON(w, http.StatusCreated, pkg)
	}
}
