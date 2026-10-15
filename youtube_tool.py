"""
B.E.T.A. - find YouTube videos and prepare them to play INSIDE the chat.

Flow: Serper's video search (or a YouTube link you paste) -> check each video allows embedding (YouTube's public
oEmbed endpoint) -> fetch a small thumbnail on the server -> the chat shows a card. Nothing is loaded from YouTube
until you tap Play, and then the player comes from youtube-nocookie.com (YouTube's privacy-enhanced embed).
Videos whose owner disabled embedding are skipped, so a card you see is a card that will play.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import image_search

SERPER_VIDEOS_URL = "https://google.serper.dev/videos"
OEMBED_URL = "https://www.youtube.com/oembed"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be",
            "youtube-nocookie.com", "www.youtube-nocookie.com"}
MAX_VIDEOS = 4


def extract_video_id(text):
    """A video id from a YouTube link (watch, youtu.be, embed, shorts, live) or a bare 11-character id; else None."""
    text = (text or "").strip()
    if ID_RE.match(text):
        return text
    try:
        u = urllib.parse.urlparse(text if "//" in text else "https://" + text)
    except Exception:
        return None
    host = (u.hostname or "").lower()
    if host not in YT_HOSTS:
        return None
    cand = None
    if host == "youtu.be":
        cand = u.path.lstrip("/").split("/")[0]
    elif u.path == "/watch":
        cand = (urllib.parse.parse_qs(u.query).get("v") or [""])[0]
    else:
        m = re.match(r"^/(?:embed|shorts|live|v)/([^/?#]+)", u.path)
        cand = m.group(1) if m else None
    return cand if cand and ID_RE.match(cand) else None


def _get_json(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; BETA/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_embeddable(video_id):
    """oEmbed details ({'title', 'author_name'}) if the video exists AND allows embedding, else None."""
    if not ID_RE.match(video_id or ""):
        return None
    url = OEMBED_URL + "?format=json&url=" + urllib.parse.quote("https://www.youtube.com/watch?v=" + video_id, safe="")
    try:
        data = _get_json(url)
        return data if isinstance(data, dict) else None
    except Exception:
        return None            # 401/404 (embedding disabled / missing / private) or a network problem


def search_videos(api_key, query, num=2):
    """Serper video results, reduced to YouTube videos with a valid id. May be empty. Raises on HTTP errors."""
    num = max(1, min(MAX_VIDEOS, int(num or 1)))
    payload = json.dumps({"q": query, "num": min(10, num * 4)}).encode("utf-8")
    req = urllib.request.Request(SERPER_VIDEOS_URL, data=payload,
                                 headers={"X-API-KEY": api_key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out, seen = [], set()
    for item in data.get("videos", []):
        vid = extract_video_id(item.get("link") or "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        out.append({"video_id": vid, "title": (item.get("title") or "").strip(),
                    "channel": (item.get("channel") or item.get("source") or "").strip(),
                    "duration": (item.get("duration") or "").strip(), "fallback_thumb": item.get("imageUrl") or ""})
    return out


def _thumb(video_id, fallback_url):
    data = image_search.fetch_image_data_url("https://i.ytimg.com/vi/%s/mqdefault.jpg" % video_id)
    if not data and fallback_url:
        data = image_search.fetch_image_data_url(fallback_url)
    return data


def build_cards(candidates, want=2):
    """Keep the first `want` candidates that allow embedding, with thumbnails. Returns cards for the chat."""
    want = max(1, min(MAX_VIDEOS, int(want or 1)))
    pool = candidates[: want * 3]

    def prep(c):
        info = check_embeddable(c["video_id"])
        if not info:
            return None
        return {"video_id": c["video_id"],
                "title": c.get("title") or info.get("title") or "YouTube video",
                "channel": c.get("channel") or info.get("author_name") or "",
                "duration": c.get("duration") or "",
                "thumb": _thumb(c["video_id"], c.get("fallback_thumb")),
                "url": "https://www.youtube.com/watch?v=" + c["video_id"]}

    with ThreadPoolExecutor(max_workers=6) as ex:
        prepared = list(ex.map(prep, pool))
    return [c for c in prepared if c][:want]
