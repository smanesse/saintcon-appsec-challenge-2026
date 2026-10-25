package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
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
