package main

import (
	"fmt"
	"sync"
	"time"
)

type Manifest struct {
	Module      string `json:"module"`
	Version     string `json:"version"`
	SHA256      string `json:"sha256"`
	PostInstall string `json:"post_install,omitempty"`
	SourceURL   string `json:"source_url,omitempty"`
}

type Package struct {
	Manifest    Manifest  `json:"manifest"`
	Size        int       `json:"size"`
	PublishedAt time.Time `json:"published_at"`
}

type Device struct {
	ID         string    `json:"id"`
	Token      string    `json:"-"`
	Module     string    `json:"module"`
	Version    string    `json:"version"`
	Status     string    `json:"status"`
	LastSeen   time.Time `json:"last_seen"`
	Trusted    bool      `json:"trusted"`
	Registered time.Time `json:"registered_at"`
}

type Store struct {
	mu sync.Mutex

	latest map[string]string

	packages map[string]map[string]*Package

	devices   map[string]*Device
	deviceSeq int
}

func NewStore() *Store {
	return &Store{
		latest:   make(map[string]string),
		packages: make(map[string]map[string]*Package),
		devices:  make(map[string]*Device),
	}
}

func (s *Store) SetLatest(module, version string, pkg *Package) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.packages[module] == nil {
		s.packages[module] = make(map[string]*Package)
	}
	s.packages[module][version] = pkg
	s.latest[module] = version
}

func (s *Store) GetLatest(module string) (*Package, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	v, ok := s.latest[module]
	if !ok {
		return nil, false
	}
	pkg, ok := s.packages[module][v]
	return pkg, ok
}

func (s *Store) GetVersion(module, version string) (*Package, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	byVer, ok := s.packages[module]
	if !ok {
		return nil, false
	}
	pkg, ok := byVer[version]
	return pkg, ok
}

func (s *Store) RegisterDevice(module, token string) *Device {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.deviceSeq++
	d := &Device{
		ID:         fmt.Sprintf("device-%d", s.deviceSeq),
		Token:      token,
		Module:     module,
		Status:     "registered",
		Registered: time.Now(),
		LastSeen:   time.Now(),
	}
	s.devices[d.ID] = d
	return d
}

func (s *Store) GetDevice(id string) (*Device, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	d, ok := s.devices[id]
	return d, ok
}

func (s *Store) ListDevices() []*Device {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]*Device, 0, len(s.devices))
	for _, d := range s.devices {
		out = append(out, d)
	}
	return out
}

func (s *Store) UpdateDeviceReport(id, version, status string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	d, ok := s.devices[id]
	if !ok {
		return false
	}
	d.Version = version
	d.Status = status
	d.LastSeen = time.Now()
	return true
}
