package main

import (
	"sync"
	"time"
)

type valueType int

const (
	typeString valueType = iota
	typeList
	typeHash
)

func (t valueType) String() string {
	switch t {
	case typeString:
		return "string"
	case typeList:
		return "list"
	case typeHash:
		return "hash"
	default:
		return "none"
	}
}

type entry struct {
	kind   valueType
	str    string
	list   []string
	hash   map[string]string
	expire time.Time
}

type Store struct {
	mu   sync.Mutex
	data map[string]*entry
}

func NewStore() *Store {
	return &Store{data: make(map[string]*entry)}
}

func (s *Store) Seed(key, val string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data[key] = &entry{kind: typeString, str: val}
}

func (s *Store) Lock()   { s.mu.Lock() }
func (s *Store) Unlock() { s.mu.Unlock() }

func expiredLocked(e *entry) bool {
	return !e.expire.IsZero() && time.Now().After(e.expire)
}

func (s *Store) getLive(key string) (*entry, bool) {
	e, ok := s.data[key]
	if !ok {
		return nil, false
	}
	if expiredLocked(e) {
		delete(s.data, key)
		return nil, false
	}
	return e, true
}

func (s *Store) snapshot() map[string]*entry {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make(map[string]*entry, len(s.data))
	for k, e := range s.data {
		if expiredLocked(e) {
			continue
		}
		cp := *e
		if e.list != nil {
			cp.list = append([]string(nil), e.list...)
		}
		if e.hash != nil {
			cp.hash = make(map[string]string, len(e.hash))
			for hk, hv := range e.hash {
				cp.hash[hk] = hv
			}
		}
		out[k] = &cp
	}
	return out
}
