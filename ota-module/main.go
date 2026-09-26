package main

import (
	"log"
	"net/http"
	"os"
)

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func main() {
	port := envOr("OTA_PORT", "8090")
	dataDir := envOr("OTA_DATA_DIR", "./data")

	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		log.Fatalf("cannot create data dir %s: %v", dataDir, err)
	}

	publishPubKey() // validate OTA_PUBLISH_PUBKEY (or warn) at startup

	store := NewStore()
	fetcher := NewSourceFetcher()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", handleHealth)
	mux.HandleFunc("POST /publish", handlePublish(store, dataDir, fetcher))
	mux.HandleFunc("GET /updates/{module}/latest", handleLatest(store))
	mux.HandleFunc("GET /updates/{module}/{version}/package", handleDownload(store, dataDir))
	mux.HandleFunc("POST /devices/register", handleDeviceRegister(store))
	mux.HandleFunc("POST /devices/{id}/report", handleDeviceReport(store))
	mux.HandleFunc("POST /devices/{id}/sync", handleDeviceSync(store))
	mux.HandleFunc("GET /devices", handleDevicesList(store))

	addr := ":" + port
	log.Printf("ota listening on %s (data dir %s)", addr, dataDir)
	log.Fatal(http.ListenAndServe(addr, mux))
}
