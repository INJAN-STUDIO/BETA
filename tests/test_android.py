"""Static sanity checks for the Android wrapper. (There is no Android SDK in my sandbox, so this can't compile it -
it only catches the typos and mistakes that are detectable without a compiler.)"""
import os, re, sys, xml.etree.ElementTree as ET
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "android")
ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(extra)))

for dirpath, _, files in os.walk(ROOT):
    for f in files:
        if f.endswith(".xml"):
            p = os.path.join(dirpath, f)
            try: ET.parse(p); good = True
            except Exception as e: good = False; print(e)
            check("well-formed XML: " + os.path.relpath(p, ROOT), good)

java = open(os.path.join(ROOT, "app/src/main/java/app/beta/assistant/MainActivity.java")).read()
code = re.sub(r'"(\\.|[^"\\])*"', '""', java)                       # ignore text inside strings
code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)                       # ...block comments
code = re.sub(r"//[^\n]*", "", code)                                    # ...and line comments
for a, b in ("{}", "()", "[]"): check("balanced %s%s in MainActivity.java" % (a, b), code.count(a) == code.count(b), (code.count(a), code.count(b)))
check("package matches the manifest namespace", "package app.beta.assistant;" in java and "namespace 'app.beta.assistant'" in open(os.path.join(ROOT, "app/build.gradle")).read())
imports = re.findall(r"^import ([\w.]+);", java, re.M); body = java.split("public class")[1]
check("every import is used", all(i.split(".")[-1] in body for i in imports), [i for i in imports if i.split(".")[-1] not in body])
used = set(re.findall(r"\b(WebView|WebViewClient|WebChromeClient|WebSettings|CookieManager|ValueCallback|Intent|Uri|Color|Bundle|ViewGroup|WebResourceRequest|WebResourceError|ActivityNotFoundException)\b", body))
check("every class used is imported", all(any(i.endswith("." + u) for i in imports) for u in used), used)
manifest = open(os.path.join(ROOT, "app/src/main/AndroidManifest.xml")).read()
check("launcher activity is exported (required on Android 12+)", 'android:exported="true"' in manifest and "android.intent.category.LAUNCHER" in manifest)
check("keyboard resizes the window (adjustResize)", "adjustResize" in manifest)
check("only the INTERNET permission is requested", re.findall(r'uses-permission android:name="([^"]+)"', manifest) == ["android.permission.INTERNET"])
check("no cleartext (http) traffic", 'usesCleartextTraffic="false"' in manifest)
check("page can't read phone files (setAllowFileAccess(false))", "setAllowFileAccess(false)" in java)
check("external links leave the app", "ACTION_VIEW" in java)
check("minSdk 26 (Android 8.0+) so the Honor 8X is covered", "minSdk 26" in open(os.path.join(ROOT, "app/build.gradle")).read())
strings = open(os.path.join(ROOT, "app/src/main/res/values/strings.xml")).read()
check("URL placeholder is clearly marked for the user to change", "YOUR-SERVICE.onrender.com" in strings and "CHANGE THIS" in strings)
from PIL import Image
for folder, px in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
    p = os.path.join(ROOT, "app/src/main/res/mipmap-%s/ic_launcher.png" % folder); im = Image.open(p)
    check("launcher icon %s is %dx%d" % (folder, px, px), im.size == (px, px), im.size)
print(f"\n{ok} passed, {fail} failed"); sys.exit(1 if fail else 0)
