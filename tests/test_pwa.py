"""Is B.E.T.A. a valid, installable PWA? Static checks on the manifest/icons/service worker, plus
Chromium's own installability report. (Firefox/Fennec can't be run in this sandbox, so the checks
follow the rules the Firefox install item depends on: valid manifest, https/localhost, a service
worker that installs and serves start_url, square icons of the declared sizes.)"""
import io, json, os, re, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.append(os.path.join(HERE, "stubs"))
os.environ.update({"BETA_PASSWORD": "pw", "SECRET_KEY": "k"}); os.environ.pop("SUPABASE_URL", None)
import storage; storage.STORE = storage.FileStore(tempfile.mkdtemp())
import app as appmod
from PIL import Image

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(extra)))

c = appmod.app.test_client()

# ---- the page that links the manifest ----
r = c.get("/")
check("start_url '/' loads without logging in (200, no redirect)", r.status_code == 200 and not r.headers.get("Location"), r.status_code)
page = r.get_data(as_text=True)
check("page links the manifest", '<link rel="manifest" href="/manifest.webmanifest">' in page)
check("page registers nothing from other sites (no Google/CDN requests)", not re.search(r'(googleapis|gstatic|googletagmanager|cdn\.|unpkg|jsdelivr)', page + open(os.path.join(ROOT, "static/app.js")).read()))

# ---- manifest ----
r = c.get("/manifest.webmanifest")
check("manifest served 200 as application/manifest+json", r.status_code == 200 and "manifest+json" in r.headers["Content-Type"], r.headers.get("Content-Type"))
m = json.loads(r.get_data(as_text=True))
for key in ("name", "short_name", "start_url", "scope", "display", "icons", "background_color", "theme_color", "id"):
    check("manifest has " + key, key in m and m[key], m.get(key))
check("display is standalone", m["display"] == "standalone")
check("start_url inside scope", m["start_url"].startswith(m["scope"]))
check("start_url itself returns 200", c.get(m["start_url"]).status_code == 200)

# ---- icons ----
sizes_found = set(); purposes = set()
for icon in m["icons"]:
    rr = c.get(icon["src"]); data = rr.get_data()
    check("icon %s (%s) is served" % (icon["src"], icon["purpose"]), rr.status_code == 200 and rr.headers["Content-Type"].startswith("image/png"), rr.status_code)
    im = Image.open(io.BytesIO(data)); declared = icon["sizes"]
    check("icon %s really is %s" % (icon["src"], declared), "%dx%d" % im.size == declared, im.size)
    check("icon %s is square" % icon["src"], im.size[0] == im.size[1])
    check("icon %s has a valid type" % icon["src"], icon["type"] == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n")
    sizes_found.add(declared); purposes.add(icon["purpose"])
check("has a 192x192 and a 512x512 icon", {"192x192", "512x512"} <= sizes_found, sizes_found)
check("has 'any' and 'maskable' purposes", {"any", "maskable"} <= purposes, purposes)
logo = c.get("/static/logo.jpg").get_data()
check("login logo is a real JPEG", logo[:3] == b"\xff\xd8\xff" and Image.open(io.BytesIO(logo)).size[0] >= 300)

# ---- service worker ----
r = c.get("/sw.js")
check("service worker served as JavaScript", r.status_code == 200 and "javascript" in r.headers["Content-Type"], r.headers.get("Content-Type"))
check("service worker may control '/' (Service-Worker-Allowed)", r.headers.get("Service-Worker-Allowed") == "/")
check("service worker is not cached by the browser (so updates arrive)", "max-age=0" in (r.headers.get("Cache-Control") or "") or "no-cache" in (r.headers.get("Cache-Control") or ""), r.headers.get("Cache-Control"))
sw = r.get_data(as_text=True)
check("service worker has a fetch handler", "addEventListener('fetch'" in sw)
shell = re.findall(r"'(/[^']*)'", re.search(r"var SHELL = \[(.*?)\];", sw, re.S).group(1))
bad = [u for u in shell if c.get(u).status_code != 200]
check("every file the service worker pre-caches exists (%d files)" % len(shell), not bad, bad)
check("service worker never caches API calls", "'/api/'" in sw or "indexOf('/api/') === 0" in sw)
check("pre-cache is per-file (one missing file can't break the install)", "c.add(u).catch" in sw)

# ---- security headers must not block the manifest / worker ----
csp = c.get("/").headers["Content-Security-Policy"]
check("CSP allows same-origin manifest + worker", "default-src 'self'" in csp and "manifest-src" not in csp.replace("default-src", "") and "worker-src" not in csp)

# ---- Chromium's own installability report ----
from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, appmod.app, threaded=True); port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 800}); p = ctx.new_page()
    p.goto("http://127.0.0.1:%d/" % port)
    ready = False
    for _ in range(50):
        if p.evaluate("() => navigator.serviceWorker.getRegistration().then(r => !!(r && r.active))"): ready = True; break
        time.sleep(0.2)
    check("service worker registers and activates", ready)
    p.reload(); controlled = False
    for _ in range(30):
        if p.evaluate("() => navigator.serviceWorker.controller !== null"): controlled = True; break
        time.sleep(0.2)
    check("page is controlled by the service worker after reload", controlled)
    cdp = ctx.new_cdp_session(p)
    mf = cdp.send("Page.getAppManifest")
    check("Chromium parses the manifest with no errors", not mf.get("errors"), mf.get("errors"))
    time.sleep(0.5)
    inst = cdp.send("Page.getInstallabilityErrors")
    check("Chromium reports NO installability errors", inst.get("installabilityErrors") == [], inst.get("installabilityErrors"))
    # served offline from cache while the server is 'asleep' (the Render wake-up case)
    ctx.set_offline(True)
    try:
        p.goto("http://127.0.0.1:%d/" % port, wait_until="domcontentloaded", timeout=8000)
        shell_ok = p.evaluate("() => !!document.getElementById('login') && !!document.getElementById('wake')")
    except Exception as e:
        shell_ok = False
    check("app shell opens from the cache even when the server is unreachable", shell_ok)
    ctx.set_offline(False); b.close()
print(f"\n{ok} passed, {fail} failed"); sys.exit(1 if fail else 0)
