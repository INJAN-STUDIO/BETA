"""Starts the real Flask app with a fake model and drives it in a phone-sized Chromium."""
import base64, io, json, os, subprocess, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.append(os.path.join(HERE, "stubs"))
os.environ.update({"BETA_PASSWORD": "pw123", "SECRET_KEY": "k"}); os.environ.pop("SUPABASE_URL", None)
import storage; storage.STORE = storage.FileStore(tempfile.mkdtemp())
import beta_agent, app as appmod
appmod.LOGIN_FAIL_DELAY = 0
from PIL import Image

def photo(i):
    im = Image.new("RGB", (240, 180), [(40,70,130),(120,60,60),(50,110,80),(110,90,40)][i % 4]); b = io.BytesIO(); im.save(b, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

REPLY = """## Flask vs FastAPI

For ALPHA I'd stay on **Flask** for now. Docs: https://flask.palletsprojects.com/, and try `pip install flask`.

| Feature | Flask | FastAPI |
|---|---|---|
| Style | Sync | Async |
| Docs | Manual | Auto |
| Fit | Already used | Needs rewrite |

* **Safe:** no rewrite needed
* **Later:** revisit async

```
pip install fastapi uvicorn
```"""

class FakeAgent:
    def __init__(self):
        import threading
        self.messages = [{"role": "system", "content": "s"}]; self._lock = threading.Lock(); self.allowed_image_urls = set(); self.got = []
    def usage_snapshot(self): return {"provider": "gemini", "active": "gemini-3.8-flash", "resets_in": 7200, "models": [{"model": "gemini-3.8-flash", "used": 7, "limit": 20, "remaining": 13, "exhausted": False}]}
    def send(self, text, image_paths=None, on_tool_result=None, on_images=None):
        self.got.append((text, [os.path.basename(p) for p in (image_paths or [])]))
        self.messages.append({"role": "user", "content": text})
        if on_tool_result: on_tool_result("Searching the web - 'flask vs fastapi'")
        time.sleep(1.2 if "slow" in text else 0.5)
        if "photos" in text and on_images:
            on_images({"query": "warehouse photos", "blurred": True, "reason": "may show bomb damage", "images": [
                {"id": i, "thumb": photo(i), "full_url": "https://x.example/%d.jpg" % i, "title": "Photo %d" % i, "source": "Example News", "page_url": "https://x.example/p%d" % i, "width": 800, "height": 600} for i in range(4)]})
            reply = "I blurred them because they may show bomb damage."
        else:
            reply = REPLY
        self.messages.append({"role": "assistant", "content": reply}); return reply
agent = FakeAgent(); appmod.AGENT = agent
from personal_brain import brain_manager
brain_manager.add_fact("Karachi builds INJAN Technologies")

from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, appmod.app, threaded=True); port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{port}"

from playwright.sync_api import sync_playwright
out = {}; errs = []
def wait_js(page, fn, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate(fn): return True
        time.sleep(0.1)
    raise TimeoutError(fn)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 360, "height": 780}, device_scale_factor=2, is_mobile=True, has_touch=True)
    p = ctx.new_page(); p.on("pageerror", lambda e: errs.append(str(e))); p.on("console", lambda m: errs.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    p.goto(URL); p.wait_for_selector("#login:not(.hidden)")
    out["login_shown_first"] = True
    p.screenshot(path="e2e_login.png")
    p.fill("#password", "wrong"); p.click("#login-btn"); wait_js(p, "() => document.getElementById('login-error').textContent.length > 0")
    out["wrong_pw_error"] = p.inner_text("#login-error")
    p.fill("#password", "pw123"); p.click("#login-btn"); p.wait_for_selector("#app:not(.hidden)")
    p.wait_for_selector(".msg.ai")
    out["greeting"] = "B.E.T.A." in p.inner_text(".msg.ai")
    out["usage_meter"] = p.inner_text("#usage-label")

    # normal reply with markdown
    p.fill("#input", "compare flask and fastapi"); p.click("#send-btn")
    p.wait_for_selector("#activity:not(.hidden)", timeout=5000); out["activity_shown"] = p.inner_text("#activity-text")
    p.wait_for_selector(".msg.ai table", timeout=10000)
    last = p.locator(".msg.ai").last
    out["h2"] = last.locator("h2").count() == 1
    out["raw_markup_left"] = ("##" in last.inner_text()) or ("**" in last.inner_text())
    out["table_rows"] = last.locator("tbody tr").count()
    out["zebra_visible"] = p.evaluate("(() => { const r = document.querySelectorAll('.msg.ai tbody tr'); return getComputedStyle(r[1].cells[0]).backgroundColor !== getComputedStyle(r[0].cells[0]).backgroundColor; })()")
    out["unlabeled_code_block"] = last.locator(".block pre", has_text="fastapi uvicorn").count() == 1
    out["url_is_tap_to_copy"] = last.locator(".md-url.md-copy").count() == 1
    out["inline_code_tap_to_copy"] = last.locator("code.md-copy").count() == 1
    p.screenshot(path="e2e_reply.png")
    p.locator(".md-url").first.click(); p.wait_for_selector("#toast:not(.hidden)"); out["toast_on_copy"] = p.inner_text("#toast")

    # blurred gallery
    p.fill("#input", "show me warehouse photos"); p.click("#send-btn"); p.wait_for_selector(".tile", timeout=10000)
    out["tiles_blurred"] = p.locator(".tile.blurred").count()
    out["veil_reason"] = p.inner_text(".veil-reason >> nth=0")
    p.screenshot(path="e2e_gallery.png")
    p.locator(".tile").first.click(); out["first_tap_reveals"] = p.locator(".tile.blurred").count() == 3 and p.locator("#lightbox.hidden").count() == 1
    p.locator(".tile").first.click(); p.wait_for_selector("#lightbox:not(.hidden)"); out["second_tap_opens_viewer"] = True
    p.click("#lb-close")
    wait_js(p, "() => !document.getElementById('send-btn').classList.contains('stop')")

    # attachment (phone photo gets shrunk before upload)
    big = Image.new("RGB", (3000, 2000), (30, 90, 160)); big.save(os.path.join(tempfile.gettempdir(), "phone_pic.png"))
    p.set_input_files("#file-input", os.path.join(tempfile.gettempdir(), "phone_pic.png"))
    p.wait_for_selector(".chip"); out["chip"] = p.inner_text(".chip .name")
    p.fill("#input", "what is in this picture"); p.click("#send-btn"); p.wait_for_selector(".msg.ai table >> nth=1", timeout=10000)
    out["server_got_attachment"] = agent.got[-1][1] and agent.got[-1][1][0].endswith(".jpg")

    # stop button
    p.fill("#input", "slow one please"); p.click("#send-btn"); p.wait_for_selector("#send-btn.stop"); p.click("#send-btn")
    p.wait_for_selector(".msg.notice"); out["stop_works"] = "Stopped" in p.inner_text(".msg.notice >> nth=-1")
    time.sleep(1.5)

    # memory panel
    p.click("#menu-btn"); p.click("#m-memory"); p.wait_for_selector(".mem-entry")
    out["memory_listed"] = "INJAN" in p.inner_text(".mem-entry")
    p.screenshot(path="e2e_memory.png"); p.click("#memory-close")

    # reload: history restored, still logged in
    p.reload(); p.wait_for_selector("#app:not(.hidden)"); p.wait_for_selector(".msg.ai table")
    out["history_after_reload"] = p.locator(".msg.user").count() >= 3

    # lock
    p.click("#menu-btn"); p.click("#m-logout"); p.wait_for_selector("#login:not(.hidden)"); out["lock_returns_to_login"] = True
    b.close()
print(json.dumps(out, indent=1)); print("JS errors:", errs or "none")
