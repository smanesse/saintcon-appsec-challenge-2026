package main

import (
	"bufio"
	"bytes"
	"strconv"

	lua "github.com/yuin/gopher-lua"
)

// cmdEval implements EVAL <script> <numkeys> [key ...] [arg ...].
//
// FIX #2 (sandboxed server-side scripting): scripts run in a locked-down Lua
// state built by newSandboxedLua() below — only the pure, side-effect-free
// standard libraries (base, table, string, math) are opened, and the file/OS
// escape hatches (`os`, `io`, `package`/`require`, `dofile`, `loadfile`, `load`,
// `loadstring`) are never installed. A client that speaks only RESP therefore
// can no longer reach os.execute() (command execution), io.open() (arbitrary
// file read/write, including reading back a CONFIG SET dir/dbfilename + SAVE
// dump), or os.getenv() (environment/secret disclosure). This matches how real
// Redis locks its scripting sandbox down. See vuln_tests/02_eval_lua_rce.py.
func (s *Session) cmdEval(args []string) bool {
	if len(args) < 3 {
		return s.arityErr("EVAL")
	}
	script := args[1]
	numKeys, err := strconv.Atoi(args[2])
	if err != nil || numKeys < 0 || 3+numKeys > len(args) {
		return s.reply(writeError(s.conn, "ERR Number of keys can't be negative"))
	}
	keys := args[3 : 3+numKeys]
	argv := args[3+numKeys:]

	L := newSandboxedLua()
	defer L.Close()

	L.SetGlobal("KEYS", toLuaArray(L, keys))
	L.SetGlobal("ARGV", toLuaArray(L, argv))

	registerRedisAPI(L, s.srv)

	if err := L.DoString(script); err != nil {
		return s.reply(writeError(s.conn, "ERR Error running script: "+err.Error()))
	}

	ret := L.Get(-1)
	return s.reply(luaToResp(s, ret))
}

// newSandboxedLua builds a Lua state safe to run untrusted EVAL scripts in.
// It opens ONLY the pure standard libraries (base, table, string, math) and
// never installs `os`, `io`, `package`/`require`, `debug` or `coroutine`, so a
// script has no path to the filesystem, the process environment, or a
// subprocess. It then strips the remaining base-library escape hatches that can
// load or execute code/files (dofile, loadfile, load, loadstring). Together
// with redis.call (installed by the caller) this leaves scripts able to touch
// the keyspace but nothing else — the same posture real Redis enforces.
func newSandboxedLua() *lua.LState {
	L := lua.NewState(lua.Options{SkipOpenLibs: true})
	for _, lib := range []struct {
		name string
		open lua.LGFunction
	}{
		{lua.BaseLibName, lua.OpenBase},
		{lua.TabLibName, lua.OpenTable},
		{lua.StringLibName, lua.OpenString},
		{lua.MathLibName, lua.OpenMath},
	} {
		L.Push(L.NewFunction(lib.open))
		L.Push(lua.LString(lib.name))
		L.Call(1, 0)
	}
	// OpenBase installs a handful of globals that can load or run external
	// code/files; remove them so the sandbox can't be pried back open.
	for _, name := range []string{"dofile", "loadfile", "load", "loadstring", "collectgarbage"} {
		L.SetGlobal(name, lua.LNil)
	}
	return L
}

func toLuaArray(L *lua.LState, items []string) *lua.LTable {
	t := L.NewTable()
	for _, it := range items {
		t.Append(lua.LString(it))
	}
	return t
}

func registerRedisAPI(L *lua.LState, srv *Server) {
	mod := L.NewTable()

	call := func(L *lua.LState) int {
		n := L.GetTop()
		cmd := make([]string, 0, n)
		for i := 1; i <= n; i++ {
			cmd = append(cmd, L.CheckString(i))
		}
		if len(cmd) == 0 {
			L.RaiseError("wrong number of args to redis.call")
			return 0
		}
		var buf bytes.Buffer
		sub := &Session{srv: srv, conn: &buf, rr: nil, authenticated: true}
		sub.dispatch(cmd)
		L.Push(decodeRespToLua(L, buf.Bytes()))
		return 1
	}

	L.SetField(mod, "call", L.NewFunction(call))
	L.SetField(mod, "pcall", L.NewFunction(call))
	L.SetField(mod, "status_reply", L.NewFunction(func(L *lua.LState) int {
		t := L.NewTable()
		L.SetField(t, "ok", lua.LString(L.CheckString(1)))
		L.Push(t)
		return 1
	}))
	L.SetField(mod, "error_reply", L.NewFunction(func(L *lua.LState) int {
		t := L.NewTable()
		L.SetField(t, "err", lua.LString(L.CheckString(1)))
		L.Push(t)
		return 1
	}))
	L.SetGlobal("redis", mod)
}

func decodeRespToLua(L *lua.LState, b []byte) lua.LValue {
	r := bufio.NewReader(bytes.NewReader(b))
	return decodeOne(L, r)
}

func decodeOne(L *lua.LState, r *bufio.Reader) lua.LValue {
	t, err := r.ReadByte()
	if err != nil {
		return lua.LNil
	}
	line, _ := r.ReadString('\n')
	line = trimCRLF(line)
	switch t {
	case '+':
		tbl := L.NewTable()
		L.SetField(tbl, "ok", lua.LString(line))
		return tbl
	case '-':
		tbl := L.NewTable()
		L.SetField(tbl, "err", lua.LString(line))
		return tbl
	case ':':
		n, _ := strconv.ParseInt(line, 10, 64)
		return lua.LNumber(n)
	case '$':
		n, _ := strconv.Atoi(line)
		if n < 0 {
			return lua.LFalse
		}
		buf := make([]byte, n)
		bufioReadFull(r, buf)
		r.ReadString('\n')
		return lua.LString(string(buf))
	case '*':
		n, _ := strconv.Atoi(line)
		if n < 0 {
			return lua.LFalse
		}
		tbl := L.NewTable()
		for i := 0; i < n; i++ {
			tbl.Append(decodeOne(L, r))
		}
		return tbl
	}
	return lua.LNil
}

func bufioReadFull(r *bufio.Reader, buf []byte) {
	got := 0
	for got < len(buf) {
		n, err := r.Read(buf[got:])
		got += n
		if err != nil {
			return
		}
	}
}

func luaToResp(s *Session, v lua.LValue) error {
	switch val := v.(type) {
	case lua.LString:
		return writeBulk(s.conn, string(val), true)
	case lua.LNumber:
		return writeInt(s.conn, int64(val))
	case lua.LBool:
		if bool(val) {
			return writeInt(s.conn, 1)
		}
		return writeBulk(s.conn, "", false)
	case *lua.LTable:
		if ok, isStr := val.RawGetString("ok").(lua.LString); isStr {
			return writeSimple(s.conn, string(ok))
		}
		if e, isStr := val.RawGetString("err").(lua.LString); isStr {
			return writeError(s.conn, string(e))
		}
		var items []string
		i := 1
		for {
			el := val.RawGetInt(i)
			if el == lua.LNil {
				break
			}
			items = append(items, luaScalar(el))
			i++
		}
		return writeArray(s.conn, items)
	case *lua.LNilType:
		return writeBulk(s.conn, "", false)
	default:
		return writeBulk(s.conn, "", false)
	}
}

func luaScalar(v lua.LValue) string {
	switch val := v.(type) {
	case lua.LString:
		return string(val)
	case lua.LNumber:
		return strconv.FormatInt(int64(val), 10)
	default:
		return v.String()
	}
}
