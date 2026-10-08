"""Starts the real app and asks Chrome itself whether it is installable as a PWA."""
import json, os, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.append(os.path.join(HERE, "stubs"))
os.environ.update({"BETA_PASSWORD": "pw123", "SECRET_KEY": "k"}); os.environ.pop("SUPABASE_URL", None)
import storage; storage.STORE = storage.FileStore(tempfile.mkdtemp())
import app as appmod
from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, appmod.app, threaded=True); URL = f"http://127.0.0.1:{srv.server_port}"
threading.Thread(target=srv.serve_forever, daemon=True).start()
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 800}); p = ctx.new_page()
    p.goto(URL); p.wait_for_selector("#login:not(.hidden), #wake")
    time.sleep(2.5)                                                    # let the service worker register + activate
    cdp = ctx.new_cdp_session(p)
    man = cdp.send("Page.getAppManifest")
    print("manifest url:", man.get("url")); print("manifest parse errors:", man.get("errors"))
    data = json.loads(man.get("data") or "{}"); print("manifest keys:", sorted(data.keys()))
    print("icons:", [(i.get("sizes"), i.get("purpose", "any")) for i in data.get("icons", [])])
    inst = cdp.send("Page.getInstallabilityErrors")
    print("INSTALLABILITY ERRORS:", inst.get("installabilityErrors"))
    sw = p.evaluate("async () => { const r = await navigator.serviceWorker.getRegistration(); return r ? (r.active ? 'active' : 'registered-not-active') : 'none'; }")
    print("service worker:", sw)
    b.close()
