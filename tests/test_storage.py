import http.server, json, os, sys, tempfile, threading, time, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs"))
import storage

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(extra)))

# ---- a tiny fake of Supabase's PostgREST ----
DB, LOG, FAIL_NEXT = {}, [], {"n": 0}
SEEN = []
JWT_KEY = "eyJhbGciOi.legacy.service_role"
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _auth_ok(self):
        SEEN.append((self.headers.get("apikey"), self.headers.get("Authorization")))
        a = self.headers.get("Authorization")
        return self.headers.get("apikey") in ("SRK", JWT_KEY) and (a is None or a == "Bearer " + self.headers.get("apikey"))
    def do_GET(self):
        if not self._auth_ok(): self.send_response(401); self.end_headers(); return
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        LOG.append(("GET", u.path, q))
        key = q["key"][0][len("eq."):]
        body = json.dumps([{"value": DB[key]}] if key in DB else []).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if not self._auth_ok(): self.send_response(401); self.end_headers(); return
        if FAIL_NEXT["n"] > 0:
            FAIL_NEXT["n"] -= 1; self.send_response(503); self.end_headers(); return
        u = urllib.parse.urlparse(self.path); n = int(self.headers["Content-Length"]); rows = json.loads(self.rfile.read(n))
        LOG.append(("POST", u.path, urllib.parse.parse_qs(u.query), self.headers.get("Prefer")))
        for r in rows: DB[r["key"]] = r["value"]
        self.send_response(201); self.end_headers()
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"

# ---- SupabaseStore ----
s = storage.SupabaseStore(URL, "SRK")
check("missing key -> default", s.get("nothing", "dflt") == "dflt")
s.set("memory", [{"role": "system", "content": "hi"}]); s.flush()
check("set + flush writes via upsert", DB.get("memory") == [{"role": "system", "content": "hi"}], DB)
posts = [l for l in LOG if l[0] == "POST"]
check("upsert uses on_conflict=key + merge-duplicates", posts and posts[-1][2].get("on_conflict") == ["key"] and "merge-duplicates" in posts[-1][3], posts)
check("new-style (sb_) key: apikey header only, NO Bearer header", SEEN and all(k == "SRK" and a is None for k, a in SEEN), SEEN[:2])
SEEN.clear(); jwt_store = storage.SupabaseStore(URL, JWT_KEY); jwt_store.set("jwtcheck", 1); jwt_store.flush()
check("legacy JWT key: apikey + Bearer, still works", DB.get("jwtcheck") == 1 and SEEN and all(k == JWT_KEY and a == "Bearer " + JWT_KEY for k, a in SEEN), SEEN[:2])

# fresh store instance = a server restart: data must come back from Supabase
s2 = storage.SupabaseStore(URL, "SRK")
check("data survives a restart (new store reads it back)", s2.get("memory") == [{"role": "system", "content": "hi"}], s2.get("memory"))
check("weird keys are URL-encoded safely", s2.get("a b&c=d") is None and any("a%20b%26c%3Dd" in str(l) or "a b&c=d" in str(l[2]) for l in LOG if l[0] == "GET"))

# copies, not references
v = s2.get("memory"); v.append("mutated")
check("get() returns a copy (cache can't be corrupted by callers)", s2.get("memory") == [{"role": "system", "content": "hi"}])

# batching: 20 rapid sets -> far fewer writes, newest value wins
before = len([l for l in LOG if l[0] == "POST"])
for i in range(20): s2.set("counter", i)
time.sleep(2.8)
after = len([l for l in LOG if l[0] == "POST"]) - before
check("burst of 20 sets coalesced into few writes", 1 <= after <= 3, after)
check("latest value is what got stored", DB.get("counter") == 19, DB.get("counter"))

# retry on failure
FAIL_NEXT["n"] = 1
s2.set("flaky", "v"); s2.flush()
check("a failed write is retried and lands", DB.get("flaky") == "v", DB.get("flaky"))

# permanently failing -> stays dirty (retried later), never raises into a reply
FAIL_NEXT["n"] = 99
s2.set("later", "x")
try: s2.flush(); no_raise = True
except Exception: no_raise = False
check("storage outage never raises into the caller", no_raise)
check("unsaved data kept for the next cycle", "later" in s2._dirty)
FAIL_NEXT["n"] = 0; s2.flush()
check("...and saved once the outage ends", DB.get("later") == "x", DB.get("later"))

# wrong credentials: reads degrade to default, no crash
bad = storage.SupabaseStore(URL, "WRONG")
check("bad credentials -> read falls back to default", bad.get("memory", "fallback") == "fallback")

# ---- FileStore (local dev) ----
d = tempfile.mkdtemp(); f = storage.FileStore(d)
f.set("brain", {"facts": ["a"]}); f.flush()
check("FileStore persists", storage.FileStore(d).get("brain") == {"facts": ["a"]})
f.set("../../etc/passwd", 1); f.flush()
check("FileStore sanitises keys (no path traversal)", not os.path.exists(os.path.join(d, "..", "..", "etc", "passwd.json")) and any(n.startswith("etcpasswd") for n in os.listdir(d)), os.listdir(d))

# ---- make_store picks the right backend ----
for k in ("SUPABASE_URL", "SUPABASE_KEY"): os.environ.pop(k, None)
check("no env -> FileStore", isinstance(storage.make_store(), storage.FileStore))
os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"] = URL, "SRK"
check("env set -> SupabaseStore", isinstance(storage.make_store(), storage.SupabaseStore))

# ---- cloud agent plumbing: memory + usage survive a "restart" ----
storage.STORE = storage.SupabaseStore(URL, "SRK")
import beta_agent, agent_core as ac
beta_agent.configure()
msgs = [{"role": "system", "content": "p"}, {"role": "user", "content": "remember me"}, {"role": "assistant", "content": "ok"}]
ac.save_memory(msgs); storage.STORE.flush()
storage.STORE = storage.SupabaseStore(URL, "SRK")        # simulate Render restarting the service
loaded = beta_agent._load_memory()
check("conversation memory survives restart", [m["role"] for m in loaded] == ["system", "user", "assistant"] and loaded[1]["content"] == "remember me", loaded)
check("B.E.T.A. prompt in a fresh conversation", "B.E.T.A" in (lambda: (storage.STORE.set("memory", None), beta_agent._load_memory()[0]["content"])[1])())
for i in range(5): ac.save_memory([{"role": "system", "content": "p"}] + [{"role": "user", "content": str(i)}] * 60)
check("history trimmed to the cloud limit", len([m for m in storage.STORE.get("memory") if m["role"] != "system"]) <= beta_agent.MAX_REMEMBERED)

u = beta_agent.CloudUsage(storage.STORE)
for _ in range(7): u.record("gemini-3.1-flash-lite")
storage.STORE.flush(); storage.STORE = storage.SupabaseStore(URL, "SRK")
u2 = beta_agent.CloudUsage(storage.STORE)
check("daily request count survives restart", u2.entry("gemini-3.1-flash-lite")["used"] == 7, u2.entry("gemini-3.1-flash-lite"))
os.environ["BETA_DAILY_LIMITS"] = json.dumps({"gemini-3.1-flash-lite": 250})
check("limits configurable via BETA_DAILY_LIMITS", beta_agent.CloudUsage(storage.STORE).entry("gemini-3.1-flash-lite")["limit"] == 250)
os.environ["BETA_DAILY_LIMITS"] = "not json"
check("bad BETA_DAILY_LIMITS ignored, defaults kept", beta_agent.CloudUsage(storage.STORE).entry("gemini-3.1-flash-lite")["limit"] == 500)

# dispatch-level enforcement: a hallucinated call to a removed tool must not run
import types
ran = []
class B(ac.Agent):
    def __init__(self):
        self.output_callback = None
        self.tool_callback = None
        self.progress_callback = None
        self.messages = [{"role": "system", "content": "s"}]
        self.active_provider = "gemini"
        self._current_job_id = None
        self._cancel_flag = False
        self.tools_registry = {}  # Mocked empty tools registry for the test
    def _run_command(self, command, explanation): ran.append(command); return "RAN"
    def _start_airis(self, chain, messages, active_tool_schemas):
        # Mocking provider return to trigger run_command hallucination
        tc = types.SimpleNamespace(id="1", function=types.SimpleNamespace(name="run_command", arguments=json.dumps({"command": "rm -rf /", "explanation": "x"})))
        if not getattr(self, "_done", False):
            self._done = True
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=None, tool_calls=[tc]))]), "m"
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="done", tool_calls=None))]), "m"

ac.save_memory = lambda m: None
b = B()
b.send("do something bad")
tool_reply = [m for m in b.messages if m.get("role") == "tool"]
check("hallucinated run_command is refused at dispatch, never executed", not ran and tool_reply and ("Unknown tool" in tool_reply[0]["content"] or "not allowed" in tool_reply[0]["content"]), (ran, tool_reply))
print(f"\n{ok} passed, {fail} failed")
if __name__ == "__main__":
    sys.exit(1 if fail else 0)
