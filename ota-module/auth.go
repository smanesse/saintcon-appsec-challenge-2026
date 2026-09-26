package main

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"net/http"
)

// defaultAPIKey is the zero-setup development key, used only when no
// OTA_API_KEY is configured (a warning is logged at startup). Once a real key
// is configured it is the ONLY key accepted - see checkPublishAuth.
const defaultAPIKey = "ota-default-key-2024"

// randomHex returns n bytes from the OS CSPRNG, hex-encoded.
func randomHex(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic("crypto/rand unavailable: " + err.Error())
	}
	return hex.EncodeToString(b)
}

// newDeviceToken returns a fresh 128-bit random device token. (VULNS.md #9
// was deriving tokens as sha256(compiled-in salt + ":" + id), which with
// sequential IDs made every device's token computable.)
func newDeviceToken() string {
	return randomHex(16)
}

// tokenEqual compares two secrets in constant time.
func tokenEqual(a, b string) bool {
	return a != "" && subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
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
	if !ok || !tokenEqual(tok, d.Token) {
		return false
	}
	return d.Trusted
}
