package main

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

func handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func handleLatest(store *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		module := r.PathValue("module")
		pkg, ok := store.GetLatest(module)
		if !ok {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "no published version for this module"})
			return
		}
		writeJSON(w, http.StatusOK, pkg)
	}
}

func handleDownload(store *Store, dataDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		module := r.PathValue("module")
		version := r.PathValue("version")
		if !allowedModules[module] || !validVersion(version) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "no such module/version"})
			return
		}
		pkg, ok := store.GetVersion(module, version)
		if !ok {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "no such module/version"})
			return
		}
		data, err := os.ReadFile(filepath.Join(packagePath(dataDir, module, version), "package.tar.gz"))
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "package bytes missing on disk"})
			return
		}
		w.Header().Set("Content-Type", "application/gzip")
		w.Header().Set("Content-Length", strconv.Itoa(len(data)))
		w.Header().Set("X-OTA-SHA256", pkg.Manifest.SHA256)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(data)
	}
}

type registerRequest struct {
	Module string `json:"module"`
}

func handleDeviceRegister(store *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req registerRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.Module == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing module"})
			return
		}
		d := store.RegisterDevice(req.Module, "")
		d.Token = deviceToken(d.ID)
		writeJSON(w, http.StatusCreated, map[string]string{
			"id":     d.ID,
			"token":  d.Token,
			"module": d.Module,
		})
	}
}

type reportRequest struct {
	Version string `json:"version"`
	Status  string `json:"status"`
}

func handleDeviceReport(store *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		d, ok := store.GetDevice(id)
		if !ok {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "no such device"})
			return
		}
		tok := bearerToken(r)
		if tok == "" || tok != d.Token {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "bad or missing device token"})
			return
		}
		var req reportRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid body"})
			return
		}
		store.UpdateDeviceReport(id, req.Version, req.Status)
		writeJSON(w, http.StatusOK, map[string]string{"status": "recorded"})
	}
}

// syncRequest is the complete set of fields a device may self-report via
// /sync. Only fields present in the body are applied.
type syncRequest struct {
	Version *string `json:"version"`
	Status  *string `json:"status"`
}

// handleDeviceSync lets a device push richer self-reported metadata than the
// narrow report endpoint accepts. The body is decoded into the syncRequest
// DTO and only its fields are copied onto the device record, so server-owned
// fields (ID, module, Trusted, timestamps) can't be set by the device.
// (VULNS.md #7 was decoding the body straight onto the live *Device, letting
// any device token holder set "trusted": true and gain publish rights.)
func handleDeviceSync(store *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		d, ok := store.GetDevice(id)
		if !ok {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "no such device"})
			return
		}
		tok := bearerToken(r)
		if tok == "" || tok != d.Token {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "bad or missing device token"})
			return
		}
		var req syncRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid body"})
			return
		}
		store.mu.Lock()
		if req.Version != nil {
			d.Version = *req.Version
		}
		if req.Status != nil {
			d.Status = *req.Status
		}
		d.LastSeen = time.Now()
		out := *d
		store.mu.Unlock()
		writeJSON(w, http.StatusOK, out)
	}
}

func handleDevicesList(store *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !checkPublishAuth(r, store) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		writeJSON(w, http.StatusOK, store.ListDevices())
	}
}

func bearerToken(r *http.Request) string {
	h := r.Header.Get("Authorization")
	const p = "Bearer "
	if len(h) > len(p) && h[:len(p)] == p {
		return h[len(p):]
	}
	return ""
}
