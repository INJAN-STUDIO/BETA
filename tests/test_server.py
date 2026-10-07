import base64, json, os, struct, sys, threading, time, types, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs"))   # stand-in for the openai package when it is not installed
os.environ["BETA_PASSWORD"] = "correct horse"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.pop("SUPABASE_URL", None); os.environ.pop("SUPABASE_KEY", None)
import tempfile; os.environ["BETA_DATA_DIR"] = tempfile.mkdtemp()
import storage
storage.STORE = storage.FileStore(tempfile.mkdtemp())     # isolate from ./data
import beta_agent
import app as appmod

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(extra)))

H = {"X-Requested-With": "beta"}
def png():
    def chunk(t, d): c = struct.pack(">I", len(d)) + t + d; return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"")
PNG = png()

class FakeAgent:
    def __init__(self):
        self.messages = [{"role": "system", "content": "s"}]
        self._lock = threading.Lock(); self.allowed_image_urls = {"https://img.example/ok.jpg"}
        self.last = None; self.delay = 0.0; self.fail = False
    def usage_snapshot(self): return {"provider": "gemini", "active": "gemini-3.8-flash", "resets_in": 100, "models": []}
    def send(self, text, image_paths=None, on_tool_result=None, on_images=None):
        self.last = {"text": text, "paths": list(image_paths or []), "exists": [os.path.exists(p) for p in (image_paths or [])]}
        self.messages.append({"role": "user", "content": text})
        if on_tool_result: on_tool_result("Searching the web - 'x'")
        if on_images: on_images({"query": "q", "blurred": True, "reason": "may show damage", "images": []})
        time.sleep(self.delay)
        if self.fail: raise RuntimeError("model exploded")
        self.messages.append({"role": "assistant", "content": "Hello **Karachi**"})
        return "Hello **Karachi**"
fake = FakeAgent(); appmod.AGENT = fake
c = appmod.app.test_client()

# ---- auth gate ----
check("health is public", c.get("/api/health").status_code == 200)
check("page itself is public", c.get("/").status_code == 200)
check("API closed without login", c.get("/api/state").status_code == 401)
check("send closed without login", c.post("/api/send", json={"text": "hi"}, headers=H).status_code == 401)
check("POST without CSRF header refused", c.post("/api/login", json={"password": "correct horse"}).status_code == 403)
r = c.post("/api/login", json={"password": "nope"}, headers=H)
check("wrong password -> 401", r.status_code == 401)
r = c.post("/api/login", json={"password": "correct horse"}, headers=H)
check("right password -> 200 + cookie", r.status_code == 200 and "beta_session" in r.headers.get("Set-Cookie", ""))
sc = r.headers.get("Set-Cookie", "")
check("cookie HttpOnly + SameSite=Lax", "HttpOnly" in sc and "SameSite=Lax" in sc, sc)
check("me -> authed", c.get("/api/me").get_json()["authed"] is True)
check("state works when logged in", c.get("/api/state").status_code == 200)

# forged / tampered cookie
c2 = appmod.app.test_client(); c2.set_cookie("beta_session", "forged.value.here")
check("forged cookie rejected", c2.get("/api/state").status_code == 401)
tok = appmod._serializer().dumps({"u": 1}); c3 = appmod.app.test_client(); c3.set_cookie("beta_session", tok[:-3] + "xyz")
check("tampered cookie rejected", c3.get("/api/state").status_code == 401)

# brute-force throttle
c4 = appmod.app.test_client(); appmod._login_fails.clear(); appmod.LOGIN_FAIL_DELAY = 0
codes = [c4.post("/api/login", json={"password": "bad%d" % i}, headers=H).status_code for i in range(7)]
check("login throttled after 5 failures", codes[:5] == [401] * 5 and codes[5] == 429 and codes[6] == 429, codes)
check("correct password also blocked while throttled", c4.post("/api/login", json={"password": "correct horse"}, headers=H).status_code == 429)
appmod._login_fails.clear()

# ---- security headers ----
r = c.get("/api/state")
check("no-store on API", r.headers.get("Cache-Control") == "no-store")
check("CSP + nosniff + frame deny", "default-src 'self'" in r.headers["Content-Security-Policy"] and r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY")
check("noindex header", "noindex" in r.headers["X-Robots-Tag"])
check("robots disallows all", "Disallow: /" in c.get("/robots.txt").get_data(as_text=True))

# ---- send / poll flow ----
fake.delay = 0.6
r = c.post("/api/send", json={"text": "hello there"}, headers=H); job = r.get_json()["job"]
check("send returns a job id immediately", r.status_code == 200 and job)
check("second send while busy -> 409", c.post("/api/send", json={"text": "again"}, headers=H).status_code == 409)
check("state reports the active job", c.get("/api/state").get_json()["active_job"] == job)
events, after, done = [], 0, False
for _ in range(40):
    p = c.get(f"/api/poll?job={job}&after={after}").get_json()
    events += p["events"]; after = p["next"]
    if p["done"]: done = True; break
    time.sleep(0.1)
types_ = [e["type"] for e in events]
check("poll delivers activity, images, reply in order", types_ == ["activity", "images", "reply"], types_)
check("reply text intact", events[-1]["text"] == "Hello **Karachi**")
check("poll finishes (done=true)", done)
check("usage snapshot included in poll", p.get("usage", {}) and p["usage"]["active"] == "gemini-3.8-flash")
check("unknown job -> 404", c.get("/api/poll?job=nope").status_code == 404)
hist = c.get("/api/state").get_json()["history"]
check("history lists user + assistant", [m["role"] for m in hist] == ["user", "assistant"], hist)
check("no active job afterwards", c.get("/api/state").get_json()["active_job"] is None)

# ---- errors in the agent are shown, not swallowed ----
fake.delay = 0; fake.fail = True
job = c.post("/api/send", json={"text": "boom"}, headers=H).get_json()["job"]; time.sleep(0.4)
p = c.get(f"/api/poll?job={job}&after=0").get_json()
check("agent error surfaces as an error event", any(e["type"] == "error" and "model exploded" in e["text"] for e in p["events"]), p)
fake.fail = False

# ---- validation ----
check("empty message rejected", c.post("/api/send", json={"text": "  "}, headers=H).status_code == 400)
check("overlong message rejected", c.post("/api/send", json={"text": "x" * 9000}, headers=H).status_code == 400)

# ---- attachments ----
def att(name, raw): return {"name": name, "data": base64.b64encode(raw).decode()}
job = c.post("/api/send", json={"text": "look", "files": [att("pic.png", PNG), att("notes.md", b"# hi")]}, headers=H).get_json()["job"]
time.sleep(0.3)
check("attachments reach the agent as temp files", fake.last and len(fake.last["paths"]) == 2 and all(fake.last["exists"]), fake.last)
check("client filenames never used on disk", all("pic" not in os.path.basename(p) and "notes" not in os.path.basename(p) for p in fake.last["paths"]))
time.sleep(0.5)
check("temp files deleted after the job", not any(os.path.exists(p) for p in fake.last["paths"]))
check("fake image (wrong bytes) refused", c.post("/api/send", json={"text": "x", "files": [att("evil.png", b"<html>hi</html>")]}, headers=H).status_code == 400)
check("executable type refused", c.post("/api/send", json={"text": "x", "files": [att("run.exe", b"MZ....")]}, headers=H).status_code == 400)
check("svg refused (scripts)", c.post("/api/send", json={"text": "x", "files": [att("a.svg", b"<svg/>")]}, headers=H).status_code == 400)
check("too many files refused", c.post("/api/send", json={"text": "x", "files": [att("a.txt", b"a")] * 5}, headers=H).status_code == 400)
check("oversize file refused", c.post("/api/send", json={"text": "x", "files": [att("big.txt", b"a" * (5 * 1024 * 1024 + 1))]}, headers=H).status_code in (400, 413))
check("bad base64 refused", c.post("/api/send", json={"text": "x", "files": [{"name": "a.txt", "data": "***not base64***"}]}, headers=H).status_code == 400)

# ---- memory panel ----
from personal_brain import brain_manager
brain_manager.add_fact("Karachi builds INJAN Technologies"); brain_manager.add_fact("Phone is a Honor 8X")
m = c.get("/api/memory").get_json()["entries"]
check("memory lists saved facts", [e["text"] for e in m] == ["Karachi builds INJAN Technologies", "Phone is a Honor 8X"], m)
check("delete a memory", c.post("/api/memory/delete", json={"id": 0}, headers=H).status_code == 200 and [e["text"] for e in c.get("/api/memory").get_json()["entries"]] == ["Phone is a Honor 8X"])
check("delete bad id -> 404", c.post("/api/memory/delete", json={"id": 99}, headers=H).status_code == 404)
check("search_facts finds by keyword", brain_manager.search_facts("which phone does he have") == ["Phone is a Honor 8X"], brain_manager.search_facts("which phone does he have"))

# ---- full image: only URLs from shown galleries ----
check("full_image refuses unknown URL", c.post("/api/full_image", json={"url": "http://169.254.169.254/x"}, headers=H).get_json()["data"] is None)

# ---- clear chat ----
fake.messages += [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
import agent_core; agent_core.save_memory = lambda m: None
check("clear chat resets history", c.post("/api/clear", headers=H).status_code == 200 and c.get("/api/state").get_json()["history"] == [])

# ---- logout ----
c.post("/api/logout", headers=H)
check("logout closes the API", c.get("/api/state").status_code == 401)

# ---- misconfiguration safety ----
os.environ["BETA_PASSWORD"] = ""
c5 = appmod.app.test_client()
check("no BETA_PASSWORD -> login disabled, never open", c5.post("/api/login", json={"password": ""}, headers=H).status_code == 503 and c5.get("/api/state").status_code == 503)
os.environ["BETA_PASSWORD"] = "correct horse"

print(f"\n{ok} passed, {fail} failed"); sys.exit(1 if fail else 0)
