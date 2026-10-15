"""
ALPHA - image search.

What this module does
  1. Asks Serper's image endpoint for photos matching a query.
  2. Decides whether the results should be BLURRED until the user clicks them
     (news-event / violence / disaster searches), and writes a short plain-
     language reason that the GUI shows on every blurred image.
  3. Downloads the thumbnails itself (in Python) and hands the GUI ready-made
     data URLs. Fetching in Python means sites that block hotlinking still
     work, and every file is checked before the GUI ever sees it.

Safety rules baked in
  - Only http/https URLs, and only hosts that resolve to PUBLIC addresses
    (no localhost, LAN, link-local) - checked again on every redirect.
  - Only real raster images are accepted (JPEG/PNG/GIF/WEBP, verified from the
    file's first bytes, not just the Content-Type header). SVG is refused
    because it can carry scripts.
  - Hard size limits and timeouts on every download.
"""

import base64
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SERPER_IMAGES_URL = "https://google.serper.dev/images"

MAX_IMAGES = 8
DEFAULT_IMAGES = 6
THUMB_MAX_BYTES = 800_000
FULL_MAX_BYTES = 8_000_000
FETCH_TIMEOUT = 8

# Tests flip this on so a local test server (127.0.0.1) can be used.
ALLOW_PRIVATE_HOSTS = False

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Sensitivity: should these results be blurred, and why?
# ---------------------------------------------------------------------------

# (pattern, short phrase used in the reason). First match wins, so the most
# specific topics come first. Deliberately a little over-eager: a wrongly
# blurred image costs one click, a wrongly shown one can't be un-seen.
_SENSITIVE_TOPICS = [
    (r"\b(bomb\w*|explosion\w*|blast|detonat\w*|airstrike\w*|shelling|missile strike)\b",
     "damage, injuries or victims from an explosion or attack"),
    (r"\b(terror\w*|massacre\w*|shooting|shooter|gunman|stabbing|hostage\w*|genocide|execution\w*|beheading)\b",
     "violence, injuries or victims"),
    (r"\b(killed|killing|dead|death|deaths|bodies|corpse\w*|casualt\w*|victims?)\b",
     "death or injuries"),
    (r"\b(gore|gory|torture\w*|mutilat\w*|injur\w*|wound\w*)\b",
     "graphic injuries"),
    (r"\b(crash|wreckage|disaster|aftermath|collapse[sd]?|earthquake|tsunami)\b",
     "destruction, damage or victims of a disaster"),
    (r"\b(suicide|self[- ]harm)\b", "distressing content about self-harm"),
    (r"\b(abuse|assault|rape)\b", "distressing content"),
]

_GENERIC_REASON = "may contain disturbing content"


def _clean_reason(text):
    """One short plain line - no markdown, no newlines, capped length."""
    text = re.sub(r"[*_`#>]+", "", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(blurred|warning|sensitive)\s*[:\-–—]\s*", "", text, flags=re.I)
    text = text.rstrip(".")
    if len(text) > 120:
        text = text[:117].rstrip() + "..."
    return text


def decide_blur(query, model_sensitive=False, model_warning=""):
    """
    Returns (blur: bool, reason: str).

    Blur if the model flagged the search as sensitive OR the query itself
    trips a keyword check - the model can add caution but can't talk the
    check out of it. The reason prefers the model's own wording (it knows
    the context) and falls back to a topic-based one.
    """
    topic = None
    for pattern, phrase in _SENSITIVE_TOPICS:
        if re.search(pattern, query or "", flags=re.I):
            topic = phrase
            break

    blur = bool(model_sensitive) or topic is not None
    if not blur:
        return False, ""

    warning = _clean_reason(model_warning)
    if warning:
        reason = warning
    elif topic:
        reason = "may show " + topic
    else:
        reason = _GENERIC_REASON
    return True, reason


# ---------------------------------------------------------------------------
# Safe fetching
# ---------------------------------------------------------------------------

def is_public_url(url):
    """True only for http(s) URLs whose host resolves to public addresses."""
    try:
        parts = urllib.parse.urlparse(url)
    except Exception:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if ALLOW_PRIVATE_HOSTS:
        return True
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except Exception:
        return False  # can't resolve -> can't vouch for it
    if not infos:
        return False
    for info in infos:
        try:
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
        except ValueError:
            return False
    return True


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    """A public URL must not be able to bounce us to a private one."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_public_url(newurl):
            raise urllib.error.URLError("redirect to a non-public address blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _sniff_mime(data):
    """Real image type from the file's first bytes, or None."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def fetch_image_data_url(url, max_bytes=THUMB_MAX_BYTES, timeout=FETCH_TIMEOUT):
    """Download one image and return it as a data: URL, or None if anything
    about it is wrong (unreachable, too big, not really an image...)."""
    if not url or not is_public_url(url):
        return None
    try:
        opener = urllib.request.build_opener(_SafeRedirects)
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "image/*"})
        with opener.open(req, timeout=timeout) as resp:
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                return None
            data = resp.read(max_bytes + 1)
    except Exception:
        return None
    if not data or len(data) > max_bytes:
        return None
    mime = _sniff_mime(data)
    if not mime:
        return None
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


# ---------------------------------------------------------------------------
# Serper + gallery
# ---------------------------------------------------------------------------

def search_serper_images(api_key, query, num=DEFAULT_IMAGES):
    """Normalised list of image results (may be empty). Raises on HTTP errors."""
    num = max(1, min(MAX_IMAGES, int(num or DEFAULT_IMAGES)))
    payload = json.dumps({"q": query, "num": min(20, num * 3)}).encode("utf-8")  # extras: some will fail to download
    req = urllib.request.Request(SERPER_IMAGES_URL, data=payload, headers={
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results, seen = [], set()
    for item in data.get("images", []):
        full = item.get("imageUrl") or ""
        thumb = item.get("thumbnailUrl") or ""
        if not (full or thumb) or full in seen:
            continue
        seen.add(full)
        results.append({
            "title": (item.get("title") or "").strip(),
            "full_url": full,
            "thumb_url": thumb or full,
            "source": (item.get("source") or item.get("domain") or "").strip(),
            "page_url": item.get("link") or "",
            "width": item.get("imageWidth"),
            "height": item.get("imageHeight"),
        })
    return results


def build_gallery(results, want=DEFAULT_IMAGES):
    """
    Download thumbnails (in parallel) for the first results that actually
    load, up to `want`. Returns tiles ready for the GUI.
    """
    want = max(1, min(MAX_IMAGES, int(want or DEFAULT_IMAGES)))
    candidates = results[: want * 3]

    def load(item):
        data_url = fetch_image_data_url(item["thumb_url"])
        if not data_url and item["thumb_url"] != item["full_url"]:
            data_url = fetch_image_data_url(item["full_url"], max_bytes=THUMB_MAX_BYTES * 2)
        return data_url

    with ThreadPoolExecutor(max_workers=6) as pool:
        loaded = list(pool.map(load, candidates))

    tiles = []
    for item, data_url in zip(candidates, loaded):
        if not data_url:
            continue
        tiles.append({
            "id": len(tiles),
            "thumb": data_url,
            "full_url": item["full_url"],
            "title": item["title"],
            "source": item["source"],
            "page_url": item["page_url"],
            "width": item["width"],
            "height": item["height"],
        })
        if len(tiles) >= want:
            break
    return tiles
