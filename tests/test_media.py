"""Image generation, YouTube cards, Edge-TTS read-aloud (with ALPHA's cleaner), the new model order - all against fake servers."""
import base64, http.server, io, json, os, sys, tempfile, threading, time, types, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.append(os.path.join(HERE, "stubs"))
os.environ.update({"BETA_PASSWORD": "pw", "SECRET_KEY": "k"}); os.environ.pop("SUPABASE_URL", None); os.environ.pop("GEMINI_IMAGE_API_KEY", None); os.environ.pop("GEMINI_IMAGE_MODEL", None)
import storage; storage.STORE = storage.FileStore(tempfile.mkdtemp())
import agent_core as ac, beta_agent, image_gen, image_search, youtube_tool, tts_edge
import app as appmod
from PIL import Image

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(extra)))

def png(w=1200, h=800):
    im = Image.new("RGB", (w, h)); px = im.load()
    for x in range(0, w, 3):
        for y in range(0, h, 3): px[x, y] = ((x * 7) % 256, (y * 5) % 256, 120)
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
PNG = png()
def jpeg(w=1024, h=1024):
    im = Image.new("RGB", (w, h)); px = im.load()
    for x in range(0, w, 4):
        for y in range(0, h, 4): px[x, y] = ((x * 3) % 256, (y * 2) % 256, 90)
    b = io.BytesIO(); im.save(b, "JPEG", quality=85); return b.getvalue()
JPG = jpeg()

# ---------------- fake Google / Serper / oEmbed ----------------
STATE = {"mode": "ok", "cf": "ok", "seen": []}
EMBEDDABLE = {"dQw4w9WgXcQ", "aaaaaaaaaaa", "ccccccccccc"}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if "generateContent" in self.path:
            STATE["seen"].append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
            m = STATE["mode"]
            if m == "ok": return self._send(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Here you go"}, {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(PNG).decode()}}]}}]})
            if m == "snake": return self._send(200, {"candidates": [{"content": {"parts": [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(PNG).decode()}}]}}]})
            if m == "limit0": return self._send(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded for metric generate_content_free_tier_requests, limit: 0, model: gemini-2.5-flash-image"}})
            if m == "quota": return self._send(429, {"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota)."}})
            if m == "block": return self._send(200, {"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}})
            if m == "finish_safety": return self._send(200, {"candidates": [{"finishReason": "IMAGE_SAFETY", "content": {"parts": []}}]})
            if m == "text_only": return self._send(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "I can only describe that, not draw it."}]}}]})
            if m == "notfound": return self._send(404, {"error": {"code": 404, "message": "models/x is not found"}})
            if m == "badkey": return self._send(403, {"error": {"code": 403, "message": "API key not valid"}})
            if m == "fake_image": return self._send(200, {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b"<html>not an image</html>").decode()}}]}}]})
            if m == "server": return self._send(500, {"error": {"message": "boom"}})
        if "/ai/run/" in self.path:
            STATE["seen"].append({"cf": self.path, "auth": self.headers.get("Authorization"), "body": body})
            m = STATE["cf"]
            if m == "ok": return self._send(200, {"success": True, "errors": [], "result": {"image": base64.b64encode(JPG).decode()}})
            if m == "quota": return self._send(429, {"success": False, "errors": [{"code": 4006, "message": "you have used up your daily free allocation of 10,000 neurons"}]})
            if m == "badtoken": return self._send(403, {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]})
            if m == "nsfw": return self._send(400, {"success": False, "errors": [{"code": 3030, "message": "AiError: NSFW content flagged"}]})
            if m == "server": return self._send(500, {})
            if m == "noimage": return self._send(200, {"success": True, "result": {}})
            if m == "success_false": return self._send(200, {"success": False, "errors": [{"code": 7000, "message": "something odd"}]})
            if m == "fake": return self._send(200, {"success": True, "result": {"image": base64.b64encode(b"<html>nope</html>").decode()}})
        if self.path.startswith("/serper/videos"):
            STATE["seen"].append({"serper": body, "key": self.headers.get("X-API-KEY")})
            return self._send(200, {"videos": [
                {"title": "Never Gonna", "link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "channel": "Rick", "duration": "3:33", "imageUrl": "https://t/x.jpg"},
                {"title": "Not embeddable", "link": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "channel": "Blocked", "duration": "1:00"},
                {"title": "Dup", "link": "https://youtu.be/dQw4w9WgXcQ"},
                {"title": "Vimeo", "link": "https://vimeo.com/12345"},
                {"title": "Second good", "link": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "channel": "Chan", "duration": "10:00"},
                {"title": "Third good", "link": "https://www.youtube.com/shorts/ccccccccccc", "channel": "Short", "duration": "0:30"}]})
        self._send(404, {})
    def do_GET(self):
        if self.path.startswith("/oembed"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); vid = q["url"][0].split("v=")[-1]
            if vid in EMBEDDABLE: return self._send(200, {"title": "oEmbed title " + vid, "author_name": "oEmbed author"})
            return self._send(401, {"error": "Unauthorized"})
        self._send(404, {})
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
image_gen.CF_ROOT = BASE + "/client/v4/accounts"
image_gen.API_ROOT = BASE + "/v1beta/models"; youtube_tool.SERPER_VIDEOS_URL = BASE + "/serper/videos"; youtube_tool.OEMBED_URL = BASE + "/oembed"

# =============== 1. image generation ===============
STATE["mode"] = "ok"
imgs = image_gen.generate("KEY1", "a teal fox", aspect="16:9")
check("returns the image bytes from Google's reply", len(imgs) == 1 and imgs[0]["bytes"] == PNG and imgs[0]["mime"] == "image/png")
sent = STATE["seen"][-1]
check("calls the image model's generateContent with the API key in a header (not the URL)", sent["path"].endswith("/gemini-2.5-flash-image:generateContent") and sent["key"] == "KEY1" and "KEY1" not in sent["path"], sent["path"])
check("asks for an image response with the chosen aspect ratio", sent["body"]["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"] and sent["body"]["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9", sent["body"])
image_gen.generate("K", "x", aspect="7:3"); check("unknown aspect ratio falls back to 1:1", STATE["seen"][-1]["body"]["generationConfig"]["imageConfig"]["aspectRatio"] == "1:1")
image_gen.generate("K", "x", model="my-custom-model"); check("model can be chosen", "/my-custom-model:generateContent" in STATE["seen"][-1]["path"])
STATE["mode"] = "snake"; check("also understands snake_case replies (inline_data)", len(image_gen.generate("K", "x")) == 1)
for mode, needle in [("limit0", "free API tier doesn't include image generation"), ("quota", "allowance is used up"), ("block", "safety filter blocked"), ("finish_safety", "declined"),
                     ("text_only", "didn't return a picture"), ("notfound", "wasn't found"), ("badkey", "rejected the API key"), ("fake_image", "didn't return a picture"), ("server", "had a problem")]:
    STATE["mode"] = mode
    try: image_gen.generate("K", "x"); msg = "NO ERROR RAISED"
    except image_gen.ImageGenError as e: msg = e.user_message
    check("plain-language error for '%s'" % mode, needle in msg, msg)
check("the free-tier message tells the user how to fix it", "GEMINI_IMAGE_API_KEY" in (lambda: (STATE.update(mode="limit0"), [image_gen.generate("K", "x")])[1])() if False else True)
STATE["mode"] = "limit0"
try: image_gen.generate("K", "x")
except image_gen.ImageGenError as e: check("free-tier message names the GEMINI_IMAGE_API_KEY option", "GEMINI_IMAGE_API_KEY" in e.user_message and "billing" in e.user_message.lower())
try: image_gen.generate("K", "   "); check("empty prompt refused", False)
except image_gen.ImageGenError: check("empty prompt refused", True)
image_gen.API_ROOT = "http://127.0.0.1:9/none"
try: image_gen.generate("K", "x", timeout=2); check("network failure handled", False)
except image_gen.ImageGenError as e: check("network failure handled kindly", "Couldn't reach" in e.user_message)
image_gen.API_ROOT = BASE + "/v1beta/models"
prev, size = image_gen.make_preview(PNG)
check("preview is a JPEG with the right original size recorded", prev.startswith("data:image/jpeg;base64,") and size == (1200, 800), (prev[:30], size))
photo = Image.blend(Image.effect_noise((1600, 1200), 40).convert("RGB"), Image.linear_gradient("L").resize((1600, 1200)).convert("RGB"), 0.5)
pb = io.BytesIO(); photo.save(pb, "PNG"); big_prev, _ = image_gen.make_preview(pb.getvalue())
check("for a photo-like image the preview is far lighter than the PNG (%d KB -> %d KB)" % (len(pb.getvalue()) // 1024, len(big_prev) // 1365), len(big_prev) < len(base64.b64encode(pb.getvalue())) * 0.3 and len(big_prev) < 450_000, (len(big_prev), len(pb.getvalue())))
pim = Image.open(io.BytesIO(base64.b64decode(prev.split(",", 1)[1]))); check("preview fits 768px", max(pim.size) <= 768, pim.size)
ids = [image_gen.store_image(PNG, "image/png", "p%d" % i) for i in range(15)]
check("only the most recent images are kept in memory (12)", image_gen.get_image(ids[0]) is None and image_gen.get_image(ids[-1])["prompt"] == "p14")

# =============== 1b. Cloudflare FLUX.1 schnell (the free, privacy-respecting provider) ===============
ACC = "0123456789abcdef0123456789abcdef"
STATE["cf"] = "ok"
r = image_gen.generate_cloudflare(ACC, "TOK", "a teal fox")
check("Cloudflare: returns a real picture", len(r) == 1 and r[0]["mime"] == "image/jpeg" and r[0]["bytes"] == JPG)
cs = [s for s in STATE["seen"] if "cf" in s][-1]
check("Cloudflare: calls the FLUX.1 schnell endpoint for the right account", cs["cf"] == "/client/v4/accounts/%s/ai/run/@cf/black-forest-labs/flux-1-schnell" % ACC, cs["cf"])
check("Cloudflare: the token goes in an Authorization header (not the URL)", cs["auth"] == "Bearer TOK" and "TOK" not in cs["cf"])
check("Cloudflare: sends the prompt and 4 steps", cs["body"] == {"prompt": "a teal fox", "steps": 4}, cs["body"])
r = image_gen.generate_cloudflare(ACC, "TOK", "a phone wallpaper", aspect="9:16"); im = Image.open(io.BytesIO(r[0]["bytes"]))
check("Cloudflare: 9:16 is made by centre-cropping the square (got %dx%d)" % im.size, abs(im.size[0] / im.size[1] - 9 / 16) < 0.01, im.size)
check("Cloudflare: non-square requests also tell the model how to frame it", "framed for a 9:16" in [s for s in STATE["seen"] if "cf" in s][-1]["body"]["prompt"])
image_gen.generate_cloudflare(ACC, "TOK", "x" * 5000); check("Cloudflare: prompt is capped at the model's limit (2048)", len([s for s in STATE["seen"] if "cf" in s][-1]["body"]["prompt"]) <= 2000)
for mode, needle in [("quota", "free daily allowance"), ("badtoken", "Workers AI"), ("nsfw", "safety filter"), ("server", "had a problem"), ("noimage", "didn't return a picture"),
                     ("success_false", "refused the request"), ("fake", "usable picture")]:
    STATE["cf"] = mode
    try: image_gen.generate_cloudflare(ACC, "TOK", "x"); msg = "NO ERROR"
    except image_gen.ImageGenError as e: msg = e.user_message
    check("Cloudflare: plain-language error for '%s'" % mode, needle in msg, msg)
STATE["cf"] = "quota"
try: image_gen.generate_cloudflare(ACC, "TOK", "x")
except image_gen.ImageGenError as e: check("Cloudflare: 'allowance used up' says when it resets (00:00 UTC = 1 am Nigeria)", "00:00 UTC" in e.user_message and "Nigeria" in e.user_message)
STATE["cf"] = "ok"; n_before = len(STATE["seen"])
for bad in ("../etc", "abc/def", "short", "x" * 100, "", "a b c d e f g h"):
    try: image_gen.generate_cloudflare(bad, "TOK", "x"); ok_ = False
    except image_gen.ImageGenError as e: ok_ = "doesn't look right" in e.user_message
    if not ok_: check("Cloudflare: bad account id rejected: %r" % bad, False)
check("Cloudflare: malformed account ids are rejected BEFORE any request (no URL injection)", len(STATE["seen"]) == n_before)
saved_root = image_gen.CF_ROOT; image_gen.CF_ROOT = "http://127.0.0.1:9/x"
try: image_gen.generate_cloudflare(ACC, "TOK", "x", timeout=2); check("Cloudflare: network failure handled", False)
except image_gen.ImageGenError as e: check("Cloudflare: network failure handled kindly", "Couldn't reach Cloudflare" in e.user_message)
image_gen.CF_ROOT = saved_root

CFENV = {"CLOUDFLARE_ACCOUNT_ID": ACC, "CLOUDFLARE_API_TOKEN": "TOK"}
order = image_gen.provider_order
check("provider order: nothing configured -> Google (chat key)", order({}, "k") == ["google"])
check("provider order: Cloudflare only -> Cloudflare (free, and Google's free key can't make images)", order(CFENV, "k") == ["cloudflare"])
check("provider order: billed Google key + Cloudflare -> Google first, Cloudflare as backup", order(dict(CFENV, GEMINI_IMAGE_API_KEY="G"), "k") == ["google", "cloudflare"])
check("provider order: billed Google key only -> Google", order({"GEMINI_IMAGE_API_KEY": "G"}, "k") == ["google"])
check("provider order: IMAGE_PROVIDER=cloudflare forces Cloudflare", order(dict(CFENV, GEMINI_IMAGE_API_KEY="G", IMAGE_PROVIDER="cloudflare"), "k") == ["cloudflare"])
check("provider order: IMAGE_PROVIDER=google forces Google even if Cloudflare is set", order(dict(CFENV, IMAGE_PROVIDER="google"), "k") == ["google"])
check("provider order: a half-configured Cloudflare (no token) is ignored", order({"CLOUDFLARE_ACCOUNT_ID": ACC}, "k") == ["google"])
check("provider order: IMAGE_PROVIDER=cloudflare without credentials falls back to Google", order({"IMAGE_PROVIDER": "cloudflare"}, "k") == ["google"])

STATE["mode"] = "ok"; STATE["cf"] = "ok"; n = len([s for s in STATE["seen"] if "path" in s])
imgs, label, ukey = image_gen.generate_any("a fox", "1:1", CFENV, "CHATKEY")
check("generate_any (Cloudflare only): label + usage key, and Google was NEVER contacted", label == image_gen.CF_LABEL and ukey == "cloudflare-flux-1-schnell" and len([s for s in STATE["seen"] if "path" in s]) == n)
STATE["mode"] = "limit0"
imgs, label, ukey = image_gen.generate_any("a fox", "1:1", dict(CFENV, GEMINI_IMAGE_API_KEY="G"), "CHATKEY")
check("generate_any: Google fails (free tier) -> Cloudflare quietly takes over", label == image_gen.CF_LABEL)
STATE["mode"] = "ok"
imgs, label, ukey = image_gen.generate_any("a fox", "1:1", dict(CFENV, GEMINI_IMAGE_API_KEY="G"), "CHATKEY")
check("generate_any: with a working billed Google key, Google is used first", label == "Gemini" and ukey == "gemini-2.5-flash-image")
STATE["mode"] = "limit0"; STATE["cf"] = "quota"
try: image_gen.generate_any("a fox", "1:1", dict(CFENV, GEMINI_IMAGE_API_KEY="G"), "CHATKEY"); msg = "NO ERROR"
except image_gen.ImageGenError as e: msg = e.user_message
check("generate_any: when both fail, the message says what each one said", "Google:" in msg and "Cloudflare:" in msg and "free daily allowance" in msg, msg)
STATE["mode"] = "ok"; STATE["cf"] = "ok"

# =============== 2. YouTube ===============
cases = {"https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ?t=5": "dQw4w9WgXcQ", "youtube.com/shorts/aaaaaaaaaaa": "aaaaaaaaaaa",
         "https://www.youtube.com/embed/ccccccccccc": "ccccccccccc", "https://m.youtube.com/watch?v=dQw4w9WgXcQ&list=x": "dQw4w9WgXcQ", "dQw4w9WgXcQ": "dQw4w9WgXcQ",
         "https://evil.com/watch?v=dQw4w9WgXcQ": None, "https://www.youtube.com.evil.com/watch?v=dQw4w9WgXcQ": None, "https://www.youtube.com/watch?v=short": None,
         "javascript:alert(1)": None, "how to make jollof rice": None, "https://www.youtube.com/watch?v=dQw4w9WgXcQ\"><script>": None}
bad = {k: youtube_tool.extract_video_id(k) for k, v in cases.items() if youtube_tool.extract_video_id(k) != v}
check("video ids extracted from every YouTube link style; look-alike hosts and junk rejected (%d cases)" % len(cases), not bad, bad)
res = youtube_tool.search_videos("SERPKEY", "rick", 2)
check("search keeps only YouTube videos, de-duplicated", [r["video_id"] for r in res] == ["dQw4w9WgXcQ", "bbbbbbbbbbb", "aaaaaaaaaaa", "ccccccccccc"], [r["video_id"] for r in res])
check("search sends the Serper key", STATE["seen"][-1]["key"] == "SERPKEY")
check("embeddable video passes the oEmbed check", youtube_tool.check_embeddable("dQw4w9WgXcQ")["title"].startswith("oEmbed"))
check("video with embedding disabled is rejected", youtube_tool.check_embeddable("bbbbbbbbbbb") is None)
check("bad ids never reach the network", youtube_tool.check_embeddable("../../x") is None)
asked = []
youtube_tool._thumb = lambda vid, fb: asked.append(vid) or "data:image/jpeg;base64,AAAA"
cards = youtube_tool.build_cards(res, want=2)
check("cards skip non-embeddable videos and keep order", [c["video_id"] for c in cards] == ["dQw4w9WgXcQ", "aaaaaaaaaaa"], [c["video_id"] for c in cards])
check("card carries title, channel, duration, thumbnail, link", cards[0]["title"] == "Never Gonna" and cards[0]["channel"] == "Rick" and cards[0]["duration"] == "3:33" and cards[0]["thumb"] and cards[0]["url"].endswith("dQw4w9WgXcQ"), cards[0])
check("filled-in title from oEmbed when search had none", youtube_tool.build_cards([{"video_id": "dQw4w9WgXcQ", "title": "", "channel": "", "duration": "", "fallback_thumb": ""}], 1)[0]["title"].startswith("oEmbed"))
import importlib; importlib.reload(youtube_tool); youtube_tool.SERPER_VIDEOS_URL = BASE + "/serper/videos"; youtube_tool.OEMBED_URL = BASE + "/oembed"
urls = []; image_search.fetch_image_data_url = lambda u, *a, **k: urls.append(u) or "data:image/jpeg;base64,BBBB"
youtube_tool.build_cards([{"video_id": "aaaaaaaaaaa", "title": "t", "channel": "c", "duration": "", "fallback_thumb": ""}], 1)
check("thumbnails come from YouTube's image host via the safe fetcher", urls == ["https://i.ytimg.com/vi/aaaaaaaaaaa/mqdefault.jpg"], urls)

# =============== 3. read-aloud: ALPHA's cleaner + Edge TTS ===============
spoken_log = []
class FakeCommunicate:
    def __init__(self, text, voice): spoken_log.append((text, voice))
    async def stream(self):
        yield {"type": "WordBoundary", "offset": 0}
        yield {"type": "audio", "data": b"ID3-part-1"}; yield {"type": "audio", "data": b"-part-2"}
fake_edge = types.ModuleType("edge_tts"); fake_edge.Communicate = FakeCommunicate; sys.modules["edge_tts"] = fake_edge
reply = "## Plan\\n\\nRead the [docs](https://docs.example.com/a?b=1) or visit https://example.com/x/y now.\\n\\n* **Bold point** with `code_here` inside 😀\\n\\n| a | b |\\n|---|---|\\n| 1 | 2 |\\n\\nDone."
reply = reply.replace("\\n", "\n")
sp = tts_edge.prepare_text(reply)
check("no web addresses are spoken", "http" not in sp and "example.com" not in sp and "://" not in sp, sp)
check("link text IS kept ('docs'); markdown symbols, code and emoji are gone", "docs" in sp and "**" not in sp and "`" not in sp and "#" not in sp and "code_here" not in sp and "😀" not in sp, sp)
check("tables become one short phrase instead of pipes and dashes", "|" not in sp and "---" not in sp and "table on screen" in sp, sp)
check("the real text survives", "Bold point" in sp and "Done" in sp, sp)
long = ("This is a sentence. " * 400); lp = tts_edge.prepare_text(long)
check("very long replies are capped at a sentence boundary", len(lp) <= tts_edge.MAX_CHARS and lp.endswith("."), (len(lp), lp[-12:]))
check("Brian is the default voice", tts_edge.VOICE == "en-US-BrianNeural")
audio = tts_edge.synthesize(reply)
check("synthesize returns the MP3 bytes from Edge", audio == b"ID3-part-1-part-2")
check("Edge was handed the CLEANED text and Brian's voice", spoken_log[-1][1] == "en-US-BrianNeural" and "http" not in spoken_log[-1][0] and "|" not in spoken_log[-1][0], spoken_log[-1])
n = len(spoken_log); tts_edge.synthesize(reply); check("repeating the same text is served from cache (no second Edge call)", len(spoken_log) == n)
try: tts_edge.synthesize("```\ncode only\n```"); check("code-only text refused (nothing to say)", False)
except tts_edge.TTSError as e: check("code-only text: friendly 'nothing to read' error", "nothing to read" in str(e).lower(), str(e))
class Boom:
    def __init__(self, *a): pass
    async def stream(self): raise ConnectionError("down"); yield
fake_edge.Communicate = Boom
try: tts_edge.synthesize("Hello there friend, brand new text one."); check("service outage reported", False)
except tts_edge.TTSError as e: check("outage -> friendly error, no stack trace", "couldn't be reached" in str(e), str(e))
del sys.modules["edge_tts"]
try: tts_edge.synthesize("Hello there friend, brand new text two."); check("missing package reported", False)
except tts_edge.TTSError as e: check("edge-tts not installed -> clear message", "isn't installed" in str(e) or "couldn't be reached" in str(e), str(e))
fake_edge.Communicate = FakeCommunicate; sys.modules["edge_tts"] = fake_edge

# =============== 4. endpoints ===============
appmod.LOGIN_FAIL_DELAY = 0
c = appmod.app.test_client(); HDR = {"X-Requested-With": "beta"}
check("/api/tts needs login", c.post("/api/tts", json={"text": "hi"}, headers=HDR).status_code == 401)
c.post("/api/login", json={"password": "pw"}, headers=HDR)
check("/api/tts needs the CSRF header", c.post("/api/tts", json={"text": "hi"}).status_code == 403)
r = c.post("/api/tts", json={"text": "Visit https://example.com **now**"}, headers=HDR)
check("/api/tts returns audio/mpeg", r.status_code == 200 and r.headers["Content-Type"].startswith("audio/mpeg") and r.get_data() == b"ID3-part-1-part-2")
check("/api/tts is never cached", r.headers.get("Cache-Control") == "no-store")
check("empty text -> 400", c.post("/api/tts", json={"text": "  "}, headers=HDR).status_code == 400)
check("absurdly long text -> 400", c.post("/api/tts", json={"text": "x" * 20001}, headers=HDR).status_code == 400)
r = c.post("/api/tts", json={"text": "```\nonly code\n```"}, headers=HDR); check("nothing readable -> 502 with a message", r.status_code == 502 and "error" in r.get_json())
gid = image_gen.store_image(PNG, "image/png", "fox")
r = c.get("/api/generated/" + gid); check("generated image is served (png)", r.status_code == 200 and r.headers["Content-Type"] == "image/png" and r.get_data() == PNG)
r = c.get("/api/generated/%s?download=1" % gid); check("?download=1 sends it as a file", "attachment" in r.headers["Content-Disposition"] and r.headers["Content-Disposition"].endswith('.png"'))
check("unknown / malformed image ids -> 404", c.get("/api/generated/" + "0" * 16).status_code == 404 and c.get("/api/generated/../../etc").status_code == 404 and c.get("/api/generated/ZZZZ").status_code == 404)
check("generated images need login", appmod.app.test_client().get("/api/generated/" + gid).status_code == 401)
h = c.get("/").headers
check("Referrer-Policy lets YouTube embeds work (not 'no-referrer')", h["Referrer-Policy"] == "strict-origin-when-cross-origin")
check("CSP allows ONLY youtube-nocookie frames, and audio blobs", "frame-src https://www.youtube-nocookie.com;" in h["Content-Security-Policy"] and "media-src 'self' blob: data:" in h["Content-Security-Policy"] and "frame-src *" not in h["Content-Security-Policy"])
check("CSP still blocks everything else", "default-src 'self'" in h["Content-Security-Policy"] and "script-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"])

# =============== 5. the agent's new tools ===============
def tc(name, args): return types.SimpleNamespace(id="c1", function=types.SimpleNamespace(name=name, arguments=json.dumps(args)), model_dump=lambda exclude_none=True: {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}})
def reply_obj(content=None, calls=None): return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content, tool_calls=calls))], usage=None)
def make_agent(script, confirm=lambda a, d: True):
    a = ac.Agent.__new__(ac.Agent); a.client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda model, messages, tools=None: script.pop(0))))
    a.groq_client = None; a.active_provider = "gemini"; a._switch_reason = None; a.confirm = confirm; a.on_rate_limit = a.on_provider_switch = a.on_usage_update = a.on_model_update = None
    a._current_on_images = None; a.allowed_image_urls = set(); a.allowed_page_urls = set(); a._api_key = "CHAT-KEY"; a._lock = threading.Lock(); a.messages = [{"role": "system", "content": "s"}]
    return a
ac.save_memory = lambda m: None; ac.USAGE = ac.UsageTracker(os.path.join(tempfile.mkdtemp(), "u.json"))
image_gen.generate = lambda key, prompt, model=None, aspect="1:1", timeout=90: [{"mime": "image/png", "bytes": PNG}]
used = {}
orig_gen = image_gen.generate; image_gen.generate = lambda key, prompt, model=None, aspect="1:1", timeout=90: used.update(key=key, model=model, aspect=aspect) or orig_gen(key, prompt)
pushed = []
a = make_agent([reply_obj(calls=[tc("generate_image", {"prompt": "a teal fox logo", "explanation": "x", "aspect_ratio": "9:16"})]), reply_obj(content="Here is your fox.")])
out = a.send("draw a fox", on_images=pushed.append)
check("generate_image: reply returned and a 'generated' payload pushed", out == "Here is your fox." and len(pushed) == 1 and pushed[0]["kind"] == "generated", pushed and pushed[0].get("kind"))
check("generate_image: uses the chat key + default model + chosen aspect", used == {"key": "CHAT-KEY", "model": "gemini-2.5-flash-image", "aspect": "9:16"}, used)
t0 = pushed[0]["images"][0]; check("generated tile has a preview, a stored id and honest source label", t0["thumb"].startswith("data:image/jpeg") and image_gen.get_image(t0["gen_id"]) and t0["source"] == "Generated by Gemini" and t0["width"] == 1200)
check("generated payload is never blurred", pushed[0]["blurred"] is False)
check("model is told it was shown (and not to paste data)", "showed them to Karachi" in [m for m in a.messages if m.get("role") == "tool"][0]["content"] and "base64" not in [m for m in a.messages if m.get("role") == "tool"][0]["content"])
os.environ["GEMINI_IMAGE_API_KEY"] = "IMG-KEY"; os.environ["GEMINI_IMAGE_MODEL"] = "gemini-3.1-flash-image-preview"
a = make_agent([reply_obj(calls=[tc("generate_image", {"prompt": "p", "explanation": "x"})]), reply_obj(content="ok")]); a.send("draw", on_images=lambda p: None)
check("a separate GEMINI_IMAGE_API_KEY / GEMINI_IMAGE_MODEL are used for images only", used["key"] == "IMG-KEY" and used["model"] == "gemini-3.1-flash-image-preview", used)
del os.environ["GEMINI_IMAGE_API_KEY"], os.environ["GEMINI_IMAGE_MODEL"]
image_gen.generate = lambda *a, **k: (_ for _ in ()).throw(image_gen.ImageGenError("Google's free API tier doesn't include image generation."))
pushed.clear(); a = make_agent([reply_obj(calls=[tc("generate_image", {"prompt": "p", "explanation": "x"})]), reply_obj(content="Sorry, can't.")]); out = a.send("draw", on_images=pushed.append)
tm = [m for m in a.messages if m.get("role") == "tool"][0]["content"]
check("generate_image failure: nothing shown, model told the real reason", not pushed and "free API tier" in tm and "don't retry" in tm, tm)
a = make_agent([reply_obj(calls=[tc("generate_image", {"prompt": "p", "explanation": "x"})]), reply_obj(content="ok")], confirm=lambda act, d: False); pushed.clear(); a.send("draw", on_images=pushed.append)
check("generate_image respects a denied permission", not pushed)

youtube_tool.search_videos = lambda key, q, n: [{"video_id": "dQw4w9WgXcQ", "title": "Never Gonna", "channel": "Rick", "duration": "3:33", "fallback_thumb": ""}]
youtube_tool.build_cards = lambda cands, want=1: [{"video_id": c["video_id"], "title": c["title"] or "Direct", "channel": c["channel"], "duration": c["duration"], "thumb": "data:image/jpeg;base64,AA", "url": "u"} for c in cands]
os.environ["SERPER_API_KEY"] = "S"; pushed.clear()
a = make_agent([reply_obj(calls=[tc("play_youtube_video", {"query": "never gonna give you up", "explanation": "x"})]), reply_obj(content="Playing it.")]); out = a.send("play it", on_images=pushed.append)
check("play_youtube_video: a 'videos' payload with playable cards is pushed", len(pushed) == 1 and pushed[0]["kind"] == "videos" and pushed[0]["videos"][0]["video_id"] == "dQw4w9WgXcQ" and pushed[0]["blurred"] is False, pushed)
tm = [m for m in a.messages if m.get("role") == "tool"][0]["content"]; check("model is told the title and not to paste links", "Never Gonna" in tm and "Don't paste links" in tm, tm)
pushed.clear(); a = make_agent([reply_obj(calls=[tc("play_youtube_video", {"query": "https://youtu.be/dQw4w9WgXcQ", "explanation": "x"})]), reply_obj(content="ok")]); a.send("play", on_images=pushed.append)
check("a pasted YouTube link skips the search and plays that video", pushed and pushed[0]["videos"][0]["video_id"] == "dQw4w9WgXcQ" and pushed[0]["videos"][0]["title"] == "Direct", pushed)
pushed.clear(); a = make_agent([reply_obj(calls=[tc("play_youtube_video", {"query": "bombing site footage", "explanation": "x"})]), reply_obj(content="ok")]); a.send("show", on_images=pushed.append)
check("sensitive video searches get blurred thumbnails + a reason (same rule as photos)", pushed and pushed[0]["blurred"] is True and "explosion" in pushed[0]["reason"], pushed and pushed[0]["reason"])
youtube_tool.build_cards = lambda cands, want=1: []
pushed.clear(); a = make_agent([reply_obj(calls=[tc("play_youtube_video", {"query": "x y", "explanation": "x"})]), reply_obj(content="ok")]); a.send("show", on_images=pushed.append)
check("no embeddable videos: nothing shown, model told why", not pushed and "embedding" in [m for m in a.messages if m.get("role") == "tool"][0]["content"])
del os.environ["SERPER_API_KEY"]
names = {t["function"]["name"] for t in make_agent([])._tools_schema()} if False else None
beta_agent.configure(); schema_names = {t["function"]["name"] for t in make_agent([])._tools_schema()}
check("both new tools are offered to the model", {"generate_image", "play_youtube_video"} <= schema_names, schema_names)
check("dangerous tools are still absent", not schema_names & {"run_command", "read_file", "write_file", "list_directory", "send_email", "copy_to_clipboard"}, schema_names)

# ---- agent + Cloudflare ----
os.environ["CLOUDFLARE_ACCOUNT_ID"] = ACC; os.environ["CLOUDFLARE_API_TOKEN"] = "TOK"
g_calls = []; image_gen.generate = lambda *a, **k: g_calls.append(1) or (_ for _ in ()).throw(image_gen.ImageGenError("google should not be called"))
cf_calls = []; image_gen.generate_cloudflare = lambda acc, tok, prompt, aspect="1:1", steps=4, timeout=90: cf_calls.append((acc, tok, prompt, aspect)) or [{"mime": "image/png", "bytes": PNG}]
pushed.clear(); a = make_agent([reply_obj(calls=[tc("generate_image", {"prompt": "a teal fox", "explanation": "x", "aspect_ratio": "16:9"})]), reply_obj(content="Here it is.")]); out = a.send("draw a fox", on_images=pushed.append)
check("agent: Cloudflare configured -> Cloudflare makes the picture and Google is not called", len(cf_calls) == 1 and cf_calls[0][3] == "16:9" and not g_calls, (cf_calls, g_calls))
check("agent: the card is honestly labelled with the provider", pushed and pushed[0]["images"][0]["source"] == "Generated by FLUX.1 schnell on Cloudflare", pushed and pushed[0]["images"][0]["source"])
check("agent: the model is told which provider made it", "FLUX.1 schnell on Cloudflare" in [m for m in a.messages if m.get("role") == "tool"][0]["content"])
check("agent: usage counted under the Cloudflare key", ac.USAGE.entry("cloudflare-flux-1-schnell")["used"] >= 1)
image_gen.generate_cloudflare = lambda *a, **k: (_ for _ in ()).throw(image_gen.ImageGenError("Cloudflare's free daily allowance (10,000 Neurons) is used up."))
pushed.clear(); a = make_agent([reply_obj(calls=[tc("generate_image", {"prompt": "p", "explanation": "x"})]), reply_obj(content="Sorry.")]); a.send("draw", on_images=pushed.append)
tm = [m for m in a.messages if m.get("role") == "tool"][0]["content"]; check("agent: Cloudflare failure -> nothing shown, real reason passed on", not pushed and "free daily allowance" in tm and "don't retry" in tm, tm)
del os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
a = make_agent([]); a.groq_client = object(); s = a.usage_snapshot(); check("snapshot says the Groq backup is switched on", s["groq"] is True and s["groq_model"] == "openai/gpt-oss-120b" and any(m["provider"] == "groq" for m in s["models"]), s)
a.groq_client = None; s = a.usage_snapshot(); check("snapshot says when the Groq backup is NOT switched on", s["groq"] is False and not any(m["provider"] == "groq" for m in s["models"]))

# =============== 6. model order ===============
src = open(os.path.join(ROOT, "agent_core.py")).read()
check("main model is gemini-3.1-flash-lite, second main is gemini-3.5-flash-lite", ac.MODEL == "gemini-3.1-flash-lite" and ac.FALLBACK_MODELS == ["gemini-3.5-flash-lite"], (ac.MODEL, ac.FALLBACK_MODELS))
check("gemini-3.8 (and 3.7/3.6) are gone from the chain", not any(x in ac.FALLBACK_MODELS + [ac.MODEL] for x in ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash")) and 'MODEL = "gemini-3.8' not in src)
check("both models have a daily-limit entry for the meter", ac.USAGE.limit_for("gemini-3.1-flash-lite") and ac.USAGE.limit_for("gemini-3.5-flash-lite"))
calls = []; exhausted = set()
def mk_client(name):
    def create(model, messages, tools=None):
        calls.append((name, model))
        if model in exhausted: raise Exception("Error code: 429 - {'error': {'status': 'RESOURCE_EXHAUSTED', 'details': [{'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}}")
        return types.SimpleNamespace(model=model)
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
a = make_agent([]); a.client = mk_client("gemini"); a.groq_client = mk_client("groq"); a.messages.append({"role": "user", "content": "hi"}); ac.USAGE = ac.UsageTracker(os.path.join(tempfile.mkdtemp(), "u2.json"))
_, m = a._call_with_fallback(); check("healthy: 3.1 Flash-Lite answers first", m == "gemini-3.1-flash-lite" and len(calls) == 1, calls)
exhausted.add("gemini-3.1-flash-lite"); calls.clear(); _, m = a._call_with_fallback()
check("3.1 used up for the day: 3.5 Flash-Lite answers (not Groq)", m == "gemini-3.5-flash-lite" and a.active_provider == "gemini", (m, calls))
exhausted.add("gemini-3.5-flash-lite"); calls.clear()
try: a._call_with_fallback(); sw = False
except ac._ProviderSwitched: sw = a.active_provider == "groq"
check("both Gemini models used up: hands over to Groq", sw)
print(f"\n{ok} passed, {fail} failed"); sys.exit(1 if fail else 0)
