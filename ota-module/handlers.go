package main

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
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
		store.mu.Lock()
		err := json.NewDecoder(r.Body).Decode(d)
		store.mu.Unlock()
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid body"})
			return
		}
		writeJSON(w, http.StatusOK, d)
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
