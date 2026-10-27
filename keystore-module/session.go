package main

import (
	"io"
	"sort"
	"strconv"
	"strings"
	"time"
)

type Session struct {
	srv           *Server
	conn          io.Writer
	rr            *respReader
	authenticated bool
}

func (s *Session) dispatch(args []string) bool {
	cmd := strings.ToUpper(args[0])

	if s.srv.cfg.password() != "" && !s.authenticated {
		switch cmd {
		case "AUTH", "QUIT", "HELLO":
		default:
			return s.reply(writeError(s.conn, "NOAUTH Authentication required."))
		}
	}

	switch cmd {
	case "PING":
		if len(args) > 1 {
			return s.reply(writeBulk(s.conn, args[1], true))
		}
		return s.reply(writeSimple(s.conn, "PONG"))
	case "ECHO":
		if len(args) != 2 {
			return s.arityErr(cmd)
		}
		return s.reply(writeBulk(s.conn, args[1], true))
	case "QUIT":
		s.reply(writeSimple(s.conn, "OK"))
		return false
	case "HELLO":
		return s.reply(writeArray(s.conn, []string{"server", "kvs", "proto", "2"}))
	case "COMMAND":
		return s.reply(writeArray(s.conn, []string{}))
	case "SELECT":
		return s.reply(writeSimple(s.conn, "OK"))
	case "AUTH":
		return s.cmdAuth(args)
	case "SET":
		return s.cmdSet(args)
	case "GET":
		return s.cmdGet(args)
	case "DEL":
		return s.cmdDel(args)
	case "EXISTS":
		return s.cmdExists(args)
	case "TYPE":
		return s.cmdType(args)
	case "EXPIRE":
		return s.cmdExpire(args)
	case "TTL":
		return s.cmdTTL(args)
	case "PERSIST":
		return s.cmdPersist(args)
	case "INCR":
		return s.cmdIncrBy(args, 1)
	case "DECR":
		return s.cmdIncrBy(args, -1)
	case "LPUSH":
		return s.cmdPush(args, true)
	case "RPUSH":
		return s.cmdPush(args, false)
	case "LPOP":
		return s.cmdPop(args, true)
	case "RPOP":
		return s.cmdPop(args, false)
	case "LRANGE":
		return s.cmdLRange(args)
	case "LLEN":
		return s.cmdLLen(args)
	case "HSET":
		return s.cmdHSet(args)
	case "HGET":
		return s.cmdHGet(args)
	case "HGETALL":
		return s.cmdHGetAll(args)
	case "HDEL":
		return s.cmdHDel(args)
	case "KEYS":
		return s.cmdKeys(args)
	case "SCAN":
		return s.cmdScan(args)
	case "DBSIZE":
		s.srv.store.Lock()
		n := int64(len(s.srv.store.data))
		s.srv.store.Unlock()
		return s.reply(writeInt(s.conn, n))
	case "FLUSHALL", "FLUSHDB":
		s.srv.store.Lock()
		s.srv.store.data = make(map[string]*entry)
		s.srv.store.Unlock()
		return s.reply(writeSimple(s.conn, "OK"))
	case "CONFIG":
		return s.cmdConfig(args)
	case "SAVE":
		return s.cmdSave(args)
	case "REPLICAOF", "SLAVEOF":
		return s.cmdReplicaOf(args)
	case "EVAL":
		return s.cmdEval(args)
	case "INFO":
		return s.reply(writeBulk(s.conn, "# Server\r\nkvs_version:1.0.0\r\n", true))
	default:
		return s.reply(writeError(s.conn, "ERR unknown command '"+args[0]+"'"))
	}
}

func (s *Session) reply(err error) bool { return err == nil }

func (s *Session) arityErr(cmd string) bool {
	return s.reply(writeError(s.conn, "ERR wrong number of arguments for '"+strings.ToLower(cmd)+"' command"))
}


func (s *Session) cmdSet(args []string) bool {
	if len(args) < 3 {
		return s.arityErr("SET")
	}
	key, val := args[1], args[2]
	var expire time.Time
	for i := 3; i+1 < len(args); i += 2 {
		switch strings.ToUpper(args[i]) {
		case "EX":
			secs, err := strconv.Atoi(args[i+1])
			if err != nil {
				return s.reply(writeError(s.conn, "ERR value is not an integer or out of range"))
			}
			expire = time.Now().Add(time.Duration(secs) * time.Second)
		case "PX":
			ms, err := strconv.Atoi(args[i+1])
			if err != nil {
				return s.reply(writeError(s.conn, "ERR value is not an integer or out of range"))
			}
			expire = time.Now().Add(time.Duration(ms) * time.Millisecond)
		}
	}
	s.srv.store.Lock()
	s.srv.store.data[key] = &entry{kind: typeString, str: val, expire: expire}
	s.srv.store.Unlock()
	return s.reply(writeSimple(s.conn, "OK"))
}

func (s *Session) cmdGet(args []string) bool {
	if len(args) != 2 {
		return s.arityErr("GET")
	}
	s.srv.store.Lock()
	e, ok := s.srv.store.getLive(args[1])
	if ok && e.kind != typeString {
		s.srv.store.Unlock()
		return s.wrongType()
	}
	var val string
	if ok {
		val = e.str
	}
	s.srv.store.Unlock()
	return s.reply(writeBulk(s.conn, val, ok))
}

func (s *Session) cmdDel(args []string) bool {
	if len(args) < 2 {
		return s.arityErr("DEL")
	}
	var n int64
	s.srv.store.Lock()
	for _, k := range args[1:] {
		if _, ok := s.srv.store.getLive(k); ok {
			delete(s.srv.store.data, k)
			n++
		}
	}
	s.srv.store.Unlock()
	return s.reply(writeInt(s.conn, n))
}

func (s *Session) cmdExists(args []string) bool {
	if len(args) < 2 {
		return s.arityErr("EXISTS")
	}
	var n int64
	s.srv.store.Lock()
	for _, k := range args[1:] {
		if _, ok := s.srv.store.getLive(k); ok {
			n++
		}
	}
	s.srv.store.Unlock()
	return s.reply(writeInt(s.conn, n))
}

func (s *Session) cmdType(args []string) bool {
	if len(args) != 2 {
		return s.arityErr("TYPE")
	}
	s.srv.store.Lock()
	e, ok := s.srv.store.getLive(args[1])
	s.srv.store.Unlock()
	if !ok {
		return s.reply(writeSimple(s.conn, "none"))
	}
	return s.reply(writeSimple(s.conn, e.kind.String()))
}


func (s *Session) cmdExpire(args []string) bool {
	if len(args) != 3 {
		return s.arityErr("EXPIRE")
	}
	secs, err := strconv.Atoi(args[2])
	if err != nil {
		return s.reply(writeError(s.conn, "ERR value is not an integer or out of range"))
	}
	s.srv.store.Lock()
	e, ok := s.srv.store.getLive(args[1])
	if ok {
		e.expire = time.Now().Add(time.Duration(secs) * time.Second)
	}
	s.srv.store.Unlock()
	if ok {
		return s.reply(writeInt(s.conn, 1))
	}
	return s.reply(writeInt(s.conn, 0))
}

func (s *Session) cmdTTL(args []string) bool {
	if len(args) != 2 {
		return s.arityErr("TTL")
	}
	s.srv.store.Lock()
	e, ok := s.srv.store.getLive(args[1])
	s.srv.store.Unlock()
	if !ok {
		return s.reply(writeInt(s.conn, -2))
	}
	if e.expire.IsZero() {
		return s.reply(writeInt(s.conn, -1))
	}
	ttl := int64(time.Until(e.expire).Seconds())
	if ttl < 0 {
		ttl = 0
	}
	return s.reply(writeInt(s.conn, ttl))
}

func (s *Session) cmdPersist(args []string) bool {
	if len(args) != 2 {
		return s.arityErr("PERSIST")
	}
	s.srv.store.Lock()
	e, ok := s.srv.store.getLive(args[1])
	changed := false
	if ok && !e.expire.IsZero() {
		e.expire = time.Time{}
		changed = true
	}
	s.srv.store.Unlock()
	if changed {
		return s.reply(writeInt(s.conn, 1))
	}
	return s.reply(writeInt(s.conn, 0))
}


func (s *Session) cmdIncrBy(args []string, delta int64) bool {
	if len(args) != 2 {
		return s.arityErr(args[0])
	}
	key := args[1]
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(key)
	var cur int64
	if ok {
		if e.kind != typeString {
			return s.wrongTypeLocked()
		}
		var err error
		cur, err = strconv.ParseInt(e.str, 10, 64)
		if err != nil {
			return s.reply(writeError(s.conn, "ERR value is not an integer or out of range"))
		}
	}
	cur += delta
	if ok {
		e.str = strconv.FormatInt(cur, 10)
	} else {
		s.srv.store.data[key] = &entry{kind: typeString, str: strconv.FormatInt(cur, 10)}
	}
	return s.reply(writeInt(s.conn, cur))
}


func (s *Session) cmdPush(args []string, left bool) bool {
	if len(args) < 3 {
		return s.arityErr(args[0])
	}
	key := args[1]
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(key)
	if !ok {
		e = &entry{kind: typeList}
		s.srv.store.data[key] = e
	} else if e.kind != typeList {
		return s.wrongTypeLocked()
	}
	for _, v := range args[2:] {
		if left {
			e.list = append([]string{v}, e.list...)
		} else {
			e.list = append(e.list, v)
		}
	}
	return s.reply(writeInt(s.conn, int64(len(e.list))))
}

func (s *Session) cmdPop(args []string, left bool) bool {
	if len(args) != 2 {
		return s.arityErr(args[0])
	}
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(args[1])
	if !ok {
		return s.reply(writeBulk(s.conn, "", false))
	}
	if e.kind != typeList {
		return s.wrongTypeLocked()
	}
	if len(e.list) == 0 {
		return s.reply(writeBulk(s.conn, "", false))
	}
	var v string
	if left {
		v, e.list = e.list[0], e.list[1:]
	} else {
		v, e.list = e.list[len(e.list)-1], e.list[:len(e.list)-1]
	}
	if len(e.list) == 0 {
		delete(s.srv.store.data, args[1])
	}
	return s.reply(writeBulk(s.conn, v, true))
}

func (s *Session) cmdLLen(args []string) bool {
	if len(args) != 2 {
		return s.arityErr("LLEN")
	}
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(args[1])
	if !ok {
		return s.reply(writeInt(s.conn, 0))
	}
	if e.kind != typeList {
		return s.wrongTypeLocked()
	}
	return s.reply(writeInt(s.conn, int64(len(e.list))))
}

func (s *Session) cmdLRange(args []string) bool {
	if len(args) != 4 {
		return s.arityErr("LRANGE")
	}
	start, err1 := strconv.Atoi(args[2])
	stop, err2 := strconv.Atoi(args[3])
	if err1 != nil || err2 != nil {
		return s.reply(writeError(s.conn, "ERR value is not an integer or out of range"))
	}
	s.srv.store.Lock()
	e, ok := s.srv.store.getLive(args[1])
	if !ok {
		s.srv.store.Unlock()
		return s.reply(writeArray(s.conn, []string{}))
	}
	if e.kind != typeList {
		s.srv.store.Unlock()
		return s.wrongType()
	}
	n := len(e.list)
	if start < 0 {
		start = n + start
	}
	if stop < 0 {
		stop = n + stop
	}
	if start < 0 {
		start = 0
	}
	if stop >= n {
		stop = n - 1
	}
	var out []string
	if start <= stop {
		out = append(out, e.list[start:stop+1]...)
	}
	s.srv.store.Unlock()
	return s.reply(writeArray(s.conn, out))
}


func (s *Session) cmdHSet(args []string) bool {
	if len(args) < 4 || (len(args)%2) != 0 {
		return s.arityErr("HSET")
	}
	key := args[1]
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(key)
	if !ok {
		e = &entry{kind: typeHash, hash: make(map[string]string)}
		s.srv.store.data[key] = e
	} else if e.kind != typeHash {
		return s.wrongTypeLocked()
	}
	var added int64
	for i := 2; i+1 < len(args); i += 2 {
		if _, exists := e.hash[args[i]]; !exists {
			added++
		}
		e.hash[args[i]] = args[i+1]
	}
	return s.reply(writeInt(s.conn, added))
}

func (s *Session) cmdHGet(args []string) bool {
	if len(args) != 3 {
		return s.arityErr("HGET")
	}
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(args[1])
	if !ok {
		return s.reply(writeBulk(s.conn, "", false))
	}
	if e.kind != typeHash {
		return s.wrongTypeLocked()
	}
	v, exists := e.hash[args[2]]
	return s.reply(writeBulk(s.conn, v, exists))
}

func (s *Session) cmdHGetAll(args []string) bool {
	if len(args) != 2 {
		return s.arityErr("HGETALL")
	}
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(args[1])
	if !ok {
		return s.reply(writeArray(s.conn, []string{}))
	}
	if e.kind != typeHash {
		return s.wrongTypeLocked()
	}
	keys := make([]string, 0, len(e.hash))
	for k := range e.hash {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make([]string, 0, len(keys)*2)
	for _, k := range keys {
		out = append(out, k, e.hash[k])
	}
	return s.reply(writeArray(s.conn, out))
}

func (s *Session) cmdHDel(args []string) bool {
	if len(args) < 3 {
		return s.arityErr("HDEL")
	}
	s.srv.store.Lock()
	defer s.srv.store.Unlock()
	e, ok := s.srv.store.getLive(args[1])
	if !ok {
		return s.reply(writeInt(s.conn, 0))
	}
	if e.kind != typeHash {
		return s.wrongTypeLocked()
	}
	var n int64
	for _, f := range args[2:] {
		if _, exists := e.hash[f]; exists {
			delete(e.hash, f)
			n++
		}
	}
	if len(e.hash) == 0 {
		delete(s.srv.store.data, args[1])
	}
	return s.reply(writeInt(s.conn, n))
}


func (s *Session) cmdKeys(args []string) bool {
	if len(args) != 2 {
		return s.arityErr("KEYS")
	}
	pattern := args[1]
	s.srv.store.Lock()
	var out []string
	for k, e := range s.srv.store.data {
		if expiredLocked(e) {
			continue
		}
		if stringMatch(pattern, k) {
			out = append(out, k)
		}
	}
	s.srv.store.Unlock()
	sort.Strings(out)
	return s.reply(writeArray(s.conn, out))
}

func (s *Session) cmdScan(args []string) bool {
	if len(args) < 2 {
		return s.arityErr("SCAN")
	}
	pattern := "*"
	for i := 2; i+1 < len(args); i += 2 {
		if strings.ToUpper(args[i]) == "MATCH" {
			pattern = args[i+1]
		}
	}
	s.srv.store.Lock()
	var keys []string
	for k, e := range s.srv.store.data {
		if expiredLocked(e) {
			continue
		}
		if stringMatch(pattern, k) {
			keys = append(keys, k)
		}
	}
	s.srv.store.Unlock()
	sort.Strings(keys)
	if err := writeRawArrayHeader(s.conn, 2); err != nil {
		return false
	}
	if err := writeBulk(s.conn, "0", true); err != nil {
		return false
	}
	return s.reply(writeArray(s.conn, keys))
}


func (s *Session) wrongType() bool {
	return s.reply(writeError(s.conn, "WRONGTYPE Operation against a key holding the wrong kind of value"))
}

func (s *Session) wrongTypeLocked() bool {
	return s.reply(writeError(s.conn, "WRONGTYPE Operation against a key holding the wrong kind of value"))
}
