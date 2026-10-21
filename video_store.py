"""
B.E.T.A. - videos from your phone, for B.E.T.A. to watch.

Flow
  1. The chat page uploads the clip here (/api/video) while you are still typing. It is checked (a real video, at most
     25 MB) and kept in a private temp file for a short while.
  2. When you send your message, B.E.T.A. is told a video is attached and gets the watch_attached_video tool.
  3. That tool sends the clip to Google's Gemini (the same Gemini that watches YouTube videos for B.E.T.A.), asks your
     question about it, and returns the answer. The temp file is deleted straight away. The copy at Google is kept for
     about an hour so you can ask follow-up questions, then deleted.

Privacy and data: uploading uses your mobile data (about the size of the clip), and the video goes to Google - the same
free-tier terms as everything else you send B.E.T.A.
"""

import os
import shutil
import tempfile
import threading
import time
import uuid

MAX_BYTES = 25 * 1024 * 1024
KEEP_LOCAL_SECONDS = 1800
KEEP_REMOTE_SECONDS = 3600
EXTENSIONS = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".3gp": "video/3gpp",
              ".mkv": "video/x-matroska", ".avi": "video/x-msvideo", ".mpg": "video/mpeg", ".mpeg": "video/mpeg"}

_lock = threading.Lock()
_dir = None
_local = {}             # id -> {"path", "name", "size", "mime", "created"}
_remote = {}            # id -> {"uri", "mime", "gname", "name", "uploaded"}  (the copy at Google)
_current = []           # ids attached to the message being worked on right now
_api_key = None
_cleaner_started = False


class VideoError(Exception):
    """A problem with a video, worded so it is safe to show."""


def _workdir():
    global _dir
    if _dir is None or not os.path.isdir(_dir):
        _dir = tempfile.mkdtemp(prefix="beta_video_")
    return _dir


def sniff(head):
    """The real video type from a file's first bytes, or None."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/3gpp" if brand[:3] == b"3gp" else "video/mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "video/x-msvideo"
    if head[:4] in (b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3"):
        return "video/mpeg"
    return None


def save(stream, name, declared_length=None):
    """Store an uploaded clip from a readable stream. Returns {'id', 'name', 'size', 'mime'}."""
    ext = os.path.splitext(str(name or ""))[1].lower()
    if ext not in EXTENSIONS:
        raise VideoError("That doesn't look like a video file (mp4, mov, webm, 3gp, mkv, avi and mpeg work).")
    if declared_length and declared_length > MAX_BYTES + 4096:
        raise VideoError("That video is too big (limit %d MB). Trim it to a shorter clip first." % (MAX_BYTES // 1048576))
    vid = uuid.uuid4().hex[:12]
    path = os.path.join(_workdir(), vid + ext)
    size, mime = 0, None
    try:
        with open(path, "wb") as out:
            while True:
                chunk = stream.read(1 << 16)
                if not chunk:
                    break
                if mime is None:
                    mime = sniff(chunk[:16] if len(chunk) >= 16 else chunk) or None
                    if not mime:
                        raise VideoError("That file isn't a real video.")
                size += len(chunk)
                if size > MAX_BYTES:
                    raise VideoError("That video is too big (limit %d MB). Trim it to a shorter clip first." % (MAX_BYTES // 1048576))
                out.write(chunk)
        if size == 0:
            raise VideoError("The upload was empty.")
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    clean_name = "".join(c for c in str(name) if c.isalnum() or c in "._- ")[:80] or ("video" + ext)
    with _lock:
        _local[vid] = {"path": path, "name": clean_name, "size": size, "mime": mime, "created": time.time()}
        while len(_local) > 4:                                   # only a few clips are ever kept
            old = min(_local, key=lambda k: _local[k]["created"])
            _drop_local(old)
    _start_cleaner()
    return {"id": vid, "name": clean_name, "size": size, "mime": mime}


def _drop_local(vid):
    item = _local.pop(vid, None)
    if item:
        try:
            os.remove(item["path"])
        except OSError:
            pass


def known(vid):
    with _lock:
        return vid in _local or vid in _remote


def info(vid):
    with _lock:
        item = _local.get(vid)
        if item:
            return {"id": vid, "name": item["name"], "size": item["size"]}
        item = _remote.get(vid)
        return {"id": vid, "name": item["name"], "size": None} if item else None


def set_current(ids):
    with _lock:
        _current[:] = [v for v in ids if v in _local or v in _remote]


def clear_current():
    with _lock:
        _current[:] = []


def current():
    with _lock:
        return list(_current)


def note_for(ids):
    """A line telling B.E.T.A. a video is attached (added to the message it receives)."""
    parts = []
    for v in ids:
        i = info(v)
        if i:
            sz = i.get("size") or 0
            size = (" (%.1f MB)" % (sz / 1048576.0) if sz >= 1048576 else " (%d KB)" % max(1, sz // 1024)) if sz else ""
            parts.append("%s%s [video_id %s]" % (i["name"], size, v))
    if not parts:
        return ""
    return ("[Karachi attached a video: " + "; ".join(parts) + ". Use the watch_attached_video tool to look at it - "
            "pass his question about it. You cannot see it any other way.]")


# ---------------------------------------------------------------------------
# Watching (Gemini)
# ---------------------------------------------------------------------------

def _wait_active(client, f, timeout=150):
    end = time.time() + timeout
    while time.time() < end:
        state = str(getattr(getattr(f, "state", None), "name", getattr(f, "state", "")) or "")
        if "ACTIVE" in state:
            return f
        if "FAILED" in state:
            raise VideoError("Google couldn't process that video. Try a different clip or format.")
        time.sleep(2)
        f = client.files.get(name=f.name)
    raise VideoError("Google took too long to process the video. Try a shorter clip.")


def analyze(question, video_id, api_key, model):
    """Ask Gemini about a video. Returns the answer text. Raises VideoError."""
    global _api_key
    try:
        from google import genai
        from google.genai import types
    except Exception:
        raise VideoError("The Google AI library isn't available on the server.")
    _api_key = api_key
    ids = [video_id] if video_id else current()
    vid = next((v for v in reversed(ids) if known(v)), None)
    if not vid:
        return None
    client = genai.Client(api_key=api_key)
    with _lock:
        remote, local = _remote.get(vid), _local.get(vid)
    if not remote:
        if not local:
            raise VideoError("That video is no longer stored. Ask Karachi to attach it again.")
        try:
            f = client.files.upload(file=local["path"], config={"mime_type": local["mime"]})
            f = _wait_active(client, f)
        except VideoError:
            raise
        except Exception as e:
            raise VideoError("Couldn't send the video to Google (%s)." % str(e)[:120])
        remote = {"uri": f.uri, "mime": local["mime"], "gname": f.name, "name": local["name"], "uploaded": time.time()}
        with _lock:
            _remote[vid] = remote
            _drop_local(vid)                                      # the clip no longer needs to sit on this server
    prompt = ("Watch this video carefully, including what is said and what is shown. Answer this question about it: %s\n"
              "Mention timestamps (mm:ss) for the important moments. If something can't be seen or heard clearly, say so "
              "instead of guessing." % (str(question or "Describe what happens in this video.")[:1500]))
    try:
        resp = client.models.generate_content(model=model, contents=[types.Content(role="user", parts=[
            types.Part.from_uri(file_uri=remote["uri"], mime_type=remote["mime"]), types.Part.from_text(text=prompt)])])
        text = (resp.text or "").strip()
    except Exception as e:
        raise VideoError("Gemini couldn't answer about the video (%s)." % str(e)[:140])
    return text[:6000] or "Gemini returned no description for this video."


# ---------------------------------------------------------------------------
# Tidying up
# ---------------------------------------------------------------------------

def _clean_once():
    now = time.time()
    with _lock:
        for v in [v for v, i in _local.items() if now - i["created"] > KEEP_LOCAL_SECONDS]:
            _drop_local(v)
        stale = [(v, i) for v, i in _remote.items() if now - i["uploaded"] > KEEP_REMOTE_SECONDS]
        for v, _i in stale:
            _remote.pop(v, None)
    if stale and _api_key:
        try:
            from google import genai
            client = genai.Client(api_key=_api_key)
            for _v, i in stale:
                try:
                    client.files.delete(name=i["gname"])
                except Exception:
                    pass
        except Exception:
            pass


def forget_all():
    """Delete everything now (used when the conversation is cleared)."""
    with _lock:
        for v in list(_local):
            _drop_local(v)
        for i in _remote.values():
            i["uploaded"] = 0
    _clean_once()


def _start_cleaner():
    global _cleaner_started
    if _cleaner_started:
        return
    _cleaner_started = True

    def loop():
        while True:
            time.sleep(300)
            try:
                _clean_once()
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True).start()
