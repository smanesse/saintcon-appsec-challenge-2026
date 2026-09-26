package main

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"net/http"
)

// defaultAPIKey is the zero-setup development key, used only when no
// OTA_API_KEY is configured (a warning is logged at startup). Once a real key
// is configured it is the ONLY key accepted - see checkPublishAuth.
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

// checkPublishAuth accepts the configured API key (compared in constant time)
// or a device that has been marked Trusted by the server.
func checkPublishAuth(r *http.Request, store *Store) bool {
	presented := r.Header.Get("X-OTA-Api-Key")
	// Only the configured key. (VULNS.md #2 was also accepting the compiled-in
	// defaultAPIKey ALWAYS, as a backdoor that stayed valid even when a real
	// OTA_API_KEY was minted.)
	if presented != "" && subtle.ConstantTimeCompare([]byte(presented), []byte(apiKey())) == 1 {
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
