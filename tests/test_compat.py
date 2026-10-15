"""(1) The loading spinner really spins. (2) B.E.T.A. still works when the browser lacks features Chrome has - what
you get on Firefox/Fennec (no speech recognition, no vibrate...) or privacy builds that strip even more.
Firefox itself can't be run in my sandbox, so this removes those features from Chromium instead."""
import json, os, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.append(os.path.join(HERE, "stubs"))
os.environ.update({"BETA_PASSWORD": "pw", "SECRET_KEY": "k"}); os.environ.pop("SUPABASE_URL", None)
import storage; storage.STORE = storage.FileStore(tempfile.mkdtemp())
import app as appmod
from flask import request
appmod.LOGIN_FAIL_DELAY = 0
DELAY = {"s": 0.0, "page": 0.0}
@appmod.app.before_request
def _slow_health():
    if request.path == "/api/health" and DELAY["s"]: time.sleep(DELAY["s"])
    if request.path == "/" and DELAY["page"]: time.sleep(DELAY["page"])
from PIL import Image

class FakeAgent:
    def __init__(self): self.messages = [{"role": "system", "content": "s"}]; self._lock = threading.Lock(); self.allowed_image_urls = set(); self.got = []
    def usage_snapshot(self): return {"provider": "gemini", "active": "gemini-3.8-flash", "resets_in": 3600, "models": [{"model": "gemini-3.8-flash", "used": 1, "limit": 20, "remaining": 19, "exhausted": False}]}
    def send(self, text, image_paths=None, on_tool_result=None, on_images=None):
        self.got.append((text, [os.path.basename(p) for p in (image_paths or [])])); self.messages.append({"role": "user", "content": text})
        if on_tool_result: on_tool_result("Working…")
        time.sleep(0.3); reply = "Hello **Karachi**, here is `some code` and https://example.com/docs"; self.messages.append({"role": "assistant", "content": reply}); return reply
agent = FakeAgent(); appmod.AGENT = agent

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(extra)))

from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, appmod.app, threaded=True); URL = "http://127.0.0.1:%d" % srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    b = pw.chromium.launch()

    # ---------- 1. the spinner on the wake screen ----------
    DELAY["s"] = 7.0                                                     # pretend Render is still waking up
    ctx = b.new_context(viewport={"width": 360, "height": 780}); p = ctx.new_page()
    p.goto(URL, wait_until="domcontentloaded"); p.wait_for_selector("#wake .spinner", timeout=5000); time.sleep(1.0)
    names = p.evaluate("() => getComputedStyle(document.querySelector('#wake .spinner')).animationName")
    t1 = p.evaluate("() => getComputedStyle(document.querySelector('#wake .spinner')).transform"); time.sleep(0.31)
    t2 = p.evaluate("() => getComputedStyle(document.querySelector('#wake .spinner')).transform"); time.sleep(0.17)
    t3 = p.evaluate("() => getComputedStyle(document.querySelector('#wake .spinner')).transform")
    check("spinner has the 'spin' animation", "spin" in names, names)
    check("spinner is actually rotating (its angle changes over time)", len({t1, t2, t3}) >= 2, (t1, t2, t3))
    sample = lambda sel: p.evaluate("(s) => getComputedStyle(document.querySelector(s)).transform", sel)
    lg = {sample("#wake .logo-wrap")}; time.sleep(0.9); lg.add(sample("#wake .logo-wrap")); time.sleep(0.9); lg.add(sample("#wake .logo-wrap"))
    check("logo gently floats on the wake screen (its position changes over time)", len(lg) >= 2, lg)
    time.sleep(1.4)
    check("after a few seconds the wake screen explains the free server is waking", "Waking" in p.inner_text("#wake-text"), p.inner_text("#wake-text"))
    DELAY["s"] = 0.0; ctx.close()

    # ---------- 1b. updates: asleep server, and a phone stuck on an old copy ----------
    ctx = b.new_context(viewport={"width": 360, "height": 780}); p = ctx.new_page(); seen = []
    p.on("request", lambda r: seen.append(r.url.replace(URL, "")))
    p.goto(URL); p.wait_for_selector("#login:not(.hidden)", timeout=8000)
    for _ in range(40):
        if p.evaluate("() => navigator.serviceWorker.getRegistration().then(r => !!(r && r.active))"): break
        time.sleep(0.2)
    p.reload(); p.wait_for_selector("#login:not(.hidden)", timeout=8000)
    check("service worker is registered with the release number in its address", p.evaluate("() => navigator.serviceWorker.getRegistration().then(r => r.active.scriptURL)").endswith("/sw.js?v=" + appmod.APP_VERSION))
    DELAY["page"] = 9.0                                                   # the server is asleep: the page request hangs
    t0 = time.time(); p.goto(URL, wait_until="domcontentloaded", timeout=15000); took = time.time() - t0
    check("asleep server: the app still opens from the saved copy within ~3 seconds (took %.1fs)" % took, took < 5.5 and p.locator("#wake").count() == 1, took)
    DELAY["page"] = 0.0; time.sleep(1.0)
    p.goto(URL); p.wait_for_selector("#login:not(.hidden)", timeout=15000)
    check("version label is filled in from the server", appmod.APP_VERSION in p.evaluate("() => document.getElementById('m-version').textContent"))
    # pretend the phone is showing an OLD release while the server has moved on
    seen.clear(); appmod.APP_VERSION = "9999.NEW"
    p.goto(URL); p.wait_for_url(URL + "/", timeout=15000)
    for _ in range(40):
        if "/reset" in seen and "/static/reset.js" in seen: break
        p.wait_for_timeout(150)
    check("a stale copy is detected and sent through /reset exactly once", seen.count("/reset") == 1 and "/static/reset.js" in seen, seen)
    p.wait_for_selector("#login:not(.hidden)", timeout=15000)
    check("...and the app comes back up afterwards (no refresh loop)", seen.count("/reset") == 1)
    appmod.APP_VERSION = appmod.APP_VERSION  # (left bumped on purpose; this context ends here)
    ctx.close()

    # ---------- 2. a browser with Firefox-style gaps ----------
    STRIP = """
    (() => {
      try { delete window.SpeechRecognition; delete window.webkitSpeechRecognition; } catch (e) {}
      for (const [o, k] of [[window, 'visualViewport'], [navigator, 'vibrate'], [navigator, 'clipboard'], [window, 'createImageBitmap'], [window, 'speechSynthesis']]) {
        try { Object.defineProperty(o, k, { value: undefined, configurable: true }); } catch (e) {}
      }
    })();
    """
    ctx = b.new_context(viewport={"width": 360, "height": 780}, is_mobile=True, has_touch=True,
                        user_agent="Mozilla/5.0 (Android 8.1.0; Mobile; rv:130.0) Gecko/130.0 Firefox/130.0")
    ctx.add_init_script(STRIP); p = ctx.new_page()
    p.on("pageerror", lambda e: errs.append(str(e))); p.on("console", lambda m: errs.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    p.goto(URL); p.wait_for_selector("#login:not(.hidden)", timeout=8000)
    check("features really are missing in this test browser", p.evaluate("() => !window.visualViewport && !navigator.clipboard && !window.createImageBitmap && !window.speechSynthesis && !('SpeechRecognition' in window)"))
    p.fill("#password", "pw"); p.keyboard.press("Enter"); p.wait_for_selector("#app:not(.hidden)", timeout=8000); p.wait_for_selector(".msg.ai")
    check("voice-input button is hidden (no speech recognition)", p.locator("#mic-btn.hidden").count() == 1)
    app_h = p.evaluate("() => document.querySelector('.app').getBoundingClientRect().height")
    check("layout still fits the screen without VisualViewport", abs(app_h - 780) < 2, app_h)
    p.click("#input"); p.keyboard.type("hello"); p.keyboard.press("Enter")
    for _ in range(60):
        if p.evaluate("() => document.querySelectorAll('.msg.ai:not(.thinking) .md').length >= 2 && !document.getElementById('send-btn').classList.contains('stop')"): break
        time.sleep(0.2)
    time.sleep(2.5)
    reply = p.locator(".msg.ai").last
    check("a reply arrives and renders markdown", reply.locator("strong").count() == 1 and "Hello Karachi" in reply.inner_text(), reply.inner_text()[:80])
    p.locator("code.md-copy").last.click(); p.wait_for_selector("#toast:not(.hidden)", timeout=3000)
    check("tap-to-copy still answers with a toast (clipboard fallback)", p.inner_text("#toast") in ("Copied", "Couldn't copy"), p.inner_text("#toast"))
    Image.new("RGB", (2400, 1600), (30, 90, 160)).save(os.path.join(tempfile.gettempdir(), "compat_pic.png"))
    p.set_input_files("#file-input", os.path.join(tempfile.gettempdir(), "compat_pic.png")); p.wait_for_selector(".chip", timeout=8000)
    check("photo attaches and is shrunk without createImageBitmap", p.inner_text(".chip .name").endswith(".jpg"), p.inner_text(".chip .name"))
    p.click("#menu-btn"); time.sleep(0.4); p.click("#m-install"); p.wait_for_selector("#install:not(.hidden)")
    body = p.inner_text("#install-body")
    check("install sheet names Fennec/Firefox and tells the user what to tap", "Fennec / Firefox" in body and "Tap Install" in body, body[:120])
    check("install sheet lists exactly what this browser lacks", "Not available in this browser" in body and "voice input" in body and "keyboard fitting" in body, body)
    p.click("#install-close"); time.sleep(0.2)
    for t in ("icon-dark", "icon-light", "dark", "light"):
        p.evaluate("(t) => { localStorage.setItem('beta_theme', t); document.documentElement.setAttribute('data-theme', t); }", t)
    check("no JavaScript errors in the stripped-down browser", not errs, errs)
    ctx.close(); b.close()
print(f"\n{ok} passed, {fail} failed"); sys.exit(1 if fail else 0)
