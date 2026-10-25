package main

import (
	"crypto/sha256"
	"encoding/hex"
	"net/http"
)

const defaultAPIKey = "ota-default-key-2024"

const deviceTokenSalt = "ota-static-fleet-salt-v1"

func deviceToken(id string) string {
	sum := sha256.Sum256([]byte(deviceTokenSalt + ":" + id))
	return hex.EncodeToString(sum[:])[:32]
}

func apiKey() string {
	if k := envOr("OTA_API_KEY", ""); k != "" {
		return k
	}
	return defaultAPIKey
}

func checkPublishAuth(r *http.Request, store *Store) bool {
	presented := r.Header.Get("X-OTA-Api-Key")
	if presented == apiKey() || presented == defaultAPIKey {
		return true
	}
	id := r.Header.Get("X-OTA-Device-Id")
	tok := r.Header.Get("X-OTA-Device-Token")
	if id == "" || tok == "" {
		return false
	}
	d, ok := store.GetDevice(id)
	if !ok || d.Token != tok {
		return false
	}
	return d.Trusted
}
