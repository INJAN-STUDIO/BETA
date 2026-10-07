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
        if "hello" in text: time.sleep(1.1)
        if on_tool_result: on_tool_result("Searching the web - 'flask vs fastapi'")
        time.sleep(1.2 if "slow" in text else 0.5)
        if "photos" in text and on_images:
            on_images({"query": "warehouse photos", "blurred": True, "reason": "may show bomb damage", "images": [
                {"id": i, "thumb": photo(i), "full_url": "https://x.example/%d.jpg" % i, "title": "Photo %d" % i, "source": "Example News", "page_url": "https://x.example/p%d" % i, "width": 800, "height": 600} for i in range(4)]})
            reply = "I blurred them because they may show bomb damage."
        elif "hello" in text:
            reply = "Hi Karachi! " + " ".join(["I can search the web, find photos, watch YouTube videos, read what you attach and remember things for you."] * 4)
        elif "long" in text:
            reply = "\n\n".join(["**Step %d:** B.E.T.A. keeps writing so you can scroll up while it types. " % (i + 1) * 3 for i in range(14)])
        else:
            reply = REPLY
        self.messages.append({"role": "assistant", "content": reply}); return reply
agent = FakeAgent(); appmod.AGENT = agent
from personal_brain import brain_manager
brain_manager.add_fact("Karachi builds INJAN Technologies")

from personal_brain import brain_manager
brain_manager.add_fact("Karachi builds INJAN Technologies")
from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, appmod.app, threaded=True); port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{port}"

from playwright.sync_api import sync_playwright
out = {}; errs = []
def wait_js(page, fn, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate(fn): return True
        time.sleep(0.1)
    raise TimeoutError(fn)
IDLE = "() => !document.getElementById('send-btn').classList.contains('stop')"
def ailen(p): return p.evaluate("() => { const m = [...document.querySelectorAll('.msg.ai:not(.thinking)')].pop(); return m ? m.innerText.length : 0; }")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 360, "height": 780}, device_scale_factor=2, is_mobile=True, has_touch=True)
    p = ctx.new_page(); p.on("pageerror", lambda e: errs.append(str(e))); p.on("console", lambda m: errs.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    p.goto(URL); p.wait_for_selector("#login:not(.hidden)")
    out["login_children_animated"] = p.evaluate("() => [...document.querySelectorAll('#login .screen-card > *')].every(e => getComputedStyle(e).animationName !== 'none')")
    p.fill("#password", "wrong"); p.keyboard.press("Enter")
    wait_js(p, "() => document.getElementById('login-error').textContent.length > 0")
    out["wrong_pw"] = p.inner_text("#login-error"); out["shake"] = p.evaluate("() => document.querySelector('#login .screen-card').classList.contains('shake')")
    p.fill("#password", "pw123"); p.keyboard.press("Enter")                      # Enter works on the login form
    p.wait_for_selector("#app:not(.hidden)"); p.wait_for_selector(".msg.ai")
    out["app_chrome_animated"] = p.evaluate("() => ['.header', '.composer', '.msg'].every(s => getComputedStyle(document.querySelector(s)).animationName !== 'none')")
    out["usage_meter"] = p.inner_text("#usage-label")
    time.sleep(0.6)

    # ---- Enter sends; Shift+Enter is a new line ----
    p.click("#input"); p.keyboard.type("line one"); p.keyboard.down("Shift"); p.keyboard.press("Enter"); p.keyboard.up("Shift"); p.keyboard.type("line two")
    out["shift_enter_newline"] = p.input_value("#input") == "line one\nline two" and p.locator(".msg.user").count() == 0
    p.fill("#input", ""); p.keyboard.type("hello there"); p.keyboard.press("Enter")
    wait_js(p, "() => document.querySelectorAll('.msg.user').length === 1")
    out["enter_sends"] = True; out["input_cleared"] = p.input_value("#input") == ""
    out["thinking_bubble"] = p.locator(".msg.thinking").count() == 1
    out["blob_thinking"] = p.evaluate("() => document.querySelector('.brand .blob').classList.contains('thinking')")
    p.screenshot(path="e2e_thinking.png")

    # ---- the reply streams in word by word ----
    wait_js(p, "() => document.querySelectorAll('.msg.ai:not(.thinking) .md').length >= 2", 15)       # greeting + this reply
    out["thinking_removed"] = p.locator(".msg.thinking").count() == 0
    time.sleep(0.4); l1 = ailen(p); p.screenshot(path="e2e_streaming.png"); time.sleep(0.7); l2 = ailen(p); time.sleep(4); l3 = ailen(p)
    out["stream_lengths"] = [l1, l2, l3]; out["streams_progressively"] = l1 < l2 < l3 and l1 < l3 * 0.8
    wait_js(p, IDLE)

    # ---- phone keyboards: the Enter/send key arrives as a beforeinput "insertLineBreak" ----
    p.fill("#input", "hello again")
    p.evaluate("() => document.getElementById('input').dispatchEvent(new InputEvent('beforeinput', { inputType: 'insertLineBreak', cancelable: true, bubbles: true }))")
    wait_js(p, "() => document.querySelectorAll('.msg.user').length === 2"); out["soft_keyboard_enter_sends"] = True
    wait_js(p, "() => document.querySelectorAll('.msg.ai:not(.thinking) .md').length >= 3", 15); time.sleep(0.4)

    # ---- tap a typing reply to show it all at once ----
    before = ailen(p); p.locator(".msg.ai:not(.thinking)").last.click(position={"x": 20, "y": 10}); time.sleep(0.15); after = ailen(p)
    out["tap_to_skip"] = after > before and after >= l3 - 5
    wait_js(p, IDLE)

    # ---- sending while a reply is typing finishes that reply first ----
    p.fill("#input", "hello once more"); p.keyboard.press("Enter")
    wait_js(p, "() => document.querySelectorAll('.msg.ai:not(.thinking) .md').length >= 4", 15); time.sleep(0.4)
    mid = ailen(p)
    p.fill("#input", "compare flask and fastapi"); p.keyboard.press("Enter"); time.sleep(0.25)
    finished = p.evaluate("() => { const m = [...document.querySelectorAll('.msg.ai:not(.thinking)')]; return m[m.length - 1].innerText.length; }")
    out["send_finishes_previous_reply"] = mid < l3 - 20 and finished >= l3 - 5
    p.wait_for_selector(".msg.ai table", timeout=15000)
    out["h2"] = p.locator(".msg.ai").last.locator("h2").count() == 1
    last = p.locator(".msg.ai").last; wait_js(p, IDLE, 15)
    prev_len = -1
    for _ in range(40):                                  # wait until the reply has finished typing
        cur = last.inner_text()
        if len(cur) == prev_len: break
        prev_len = len(cur); time.sleep(0.4)
    out["no_raw_markup"] = not (("##" in last.inner_text()) or ("**" in last.inner_text()))
    if not out["no_raw_markup"]: print("RAW MARKUP SAMPLE >>>", repr(last.inner_text()[:400]))
    out["zebra_visible"] = p.evaluate("() => { const r = document.querySelectorAll('.msg.ai tbody tr'); return getComputedStyle(r[1].cells[0]).backgroundColor !== getComputedStyle(r[0].cells[0]).backgroundColor; }")
    out["code_and_links_copyable"] = last.locator(".block pre", has_text="fastapi uvicorn").count() == 1 and last.locator(".md-url.md-copy").count() == 1 and last.locator("code.md-copy").count() == 1
    p.locator(".md-url").first.click(); p.wait_for_selector("#toast:not(.hidden)"); out["toast"] = p.inner_text("#toast")

    # ---- blurred gallery ----
    p.fill("#input", "show me warehouse photos"); p.keyboard.press("Enter"); p.wait_for_selector(".tile", timeout=15000)
    out["tiles_blurred"] = p.locator(".tile.blurred").count(); out["veil_reason"] = p.inner_text(".veil-reason >> nth=0")
    out["tiles_staggered"] = p.evaluate("() => [...document.querySelectorAll('.tile')].map(t => getComputedStyle(t).animationDelay).join(',')")
    p.screenshot(path="e2e_gallery.png")
    p.locator(".tile").first.click(); out["first_tap_reveals"] = p.locator(".tile.blurred").count() == 3 and p.locator("#lightbox.hidden").count() == 1
    p.locator(".tile").first.click(); p.wait_for_selector("#lightbox:not(.hidden)"); out["second_tap_opens_viewer"] = True; p.click("#lb-close")
    wait_js(p, IDLE, 15)

    # ---- attachment (a phone photo gets shrunk first) ----
    big = Image.new("RGB", (3000, 2000), (30, 90, 160)); big.save(os.path.join(tempfile.gettempdir(), "phone_pic.png"))
    p.set_input_files("#file-input", os.path.join(tempfile.gettempdir(), "phone_pic.png")); p.wait_for_selector(".chip")
    p.fill("#input", "what is in this picture"); p.keyboard.press("Enter"); wait_js(p, "() => document.querySelectorAll('.msg.user').length >= 6", 15)
    wait_js_py = time.time() + 5
    while time.time() < wait_js_py and not (agent.got and agent.got[-1][0] == "what is in this picture"): time.sleep(0.1)
    out["server_got_attachment"] = bool(agent.got[-1][1]) and agent.got[-1][1][0].endswith(".jpg"); wait_js(p, IDLE, 15)

    # ---- scrolling up while a long reply types is respected ----
    p.fill("#input", "give me a long answer"); p.keyboard.press("Enter")
    wait_js(p, "() => { const c = document.getElementById('chat'); return c.scrollHeight - c.clientHeight > 0 && document.querySelectorAll('.msg.ai:not(.thinking) .md').length >= 7; }", 20)
    wait_js(p, "() => document.getElementById('chat').scrollHeight > document.getElementById('chat').clientHeight + 900", 20)
    p.mouse.move(180, 400); p.mouse.wheel(0, -400); time.sleep(0.3)
    d1 = p.evaluate("() => { const c = document.getElementById('chat'); return c.scrollHeight - c.scrollTop - c.clientHeight; }"); time.sleep(1.5)
    d2 = p.evaluate("() => { const c = document.getElementById('chat'); return c.scrollHeight - c.scrollTop - c.clientHeight; }")
    out["scroll_up_respected_while_typing"] = d1 > 100 and d2 >= d1; out["latest_button"] = p.locator("#jump:not(.hidden)").count() == 1
    p.click("#jump"); time.sleep(0.2)
    out["latest_returns_to_bottom"] = p.evaluate("() => { const c = document.getElementById('chat'); return c.scrollHeight - c.scrollTop - c.clientHeight < 5; }")
    wait_js(p, IDLE, 25)

    # ---- stop button ----
    p.fill("#input", "hello stop me"); p.keyboard.press("Enter"); p.wait_for_selector("#send-btn.stop"); p.click("#send-btn")
    p.wait_for_selector(".msg.notice"); out["stop_works"] = "Stopped" in p.inner_text(".msg.notice >> nth=-1"); time.sleep(1.5)

    # ---- menu + memory panel ----
    p.click("#menu-btn"); time.sleep(0.15); out["sheet_animated"] = p.evaluate("() => getComputedStyle(document.querySelector('#menu .sheet')).animationName !== 'none'")
    p.screenshot(path="e2e_menu.png"); p.click("#m-memory"); p.wait_for_selector(".mem-entry"); out["memory_listed"] = "INJAN" in p.inner_text(".mem-entry"); p.click("#memory-close")

    # ---- reload keeps history; lock returns to login ----
    p.reload(); p.wait_for_selector("#app:not(.hidden)"); p.wait_for_selector(".msg.ai table")
    out["history_after_reload"] = p.locator(".msg.user").count() >= 5
    p.click("#menu-btn"); p.click("#m-logout"); p.wait_for_selector("#login:not(.hidden)"); out["lock_returns_to_login"] = True
    ctx.close()

    rctx = b.new_context(viewport={"width": 360, "height": 780}, reduced_motion="reduce"); rp = rctx.new_page(); rp.goto(URL); rp.wait_for_selector("#login:not(.hidden)")
    out["reduced_motion_duration"] = rp.evaluate("() => getComputedStyle(document.querySelector('#login .screen-card > *')).animationDuration")
    b.close()
print(json.dumps(out, indent=1)); print("JS errors:", errs or "none")
bad = [k for k, v in out.items() if v is False]
print("FAILED:", bad or "none"); sys.exit(1 if bad else 0)
