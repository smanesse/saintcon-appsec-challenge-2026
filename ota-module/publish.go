package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"
)

var allowedModules = map[string]bool{
	"fmm": true,
	"ipm": true,
	"log": true,
}

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
		// The manifest must carry a valid publisher signature (checked before
		// any source_url fetch); the bytes are then checked against the signed
		// checksum below.
		if !verifyManifestSignature(m) {
			writeJSON(w, http.StatusForbidden, map[string]string{"error": "missing or invalid package signature"})
			return
		}

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
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error":    "checksum mismatch",
				"expected": m.SHA256,
				"computed": got,
			})
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
