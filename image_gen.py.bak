"""
B.E.T.A. - image generation with Google's Gemini image model ("Nano Banana").

Calls Google's native REST API (generateContent with an IMAGE response). The picture is kept on the server
(last few only, in memory) and the chat gets a small JPEG preview, so a phone on mobile data isn't sent a
multi-megabyte PNG for every image. Tap the preview to open the full image or save it.

Two providers (see generate_any):
  * Google Gemini image model - best quality, but NOT on Google's free API tier (see below).
  * Cloudflare Workers AI, FLUX.1 [schnell] - the free alternative. 10,000 free "Neurons" a day, no card needed;
    by Cloudflare's published price that is roughly 170 square 1024x1024 pictures a day. Cloudflare's docs say it
    does not use your prompts or pictures to train models or to improve its services, and does not share them with
    other customers. (FLUX.1 schnell is open-source, made by Black Forest Labs.)

IMPORTANT - Google's free tier: as of October 2026 Google's pricing page lists the Gemini image models as NOT available
on the free API tier (the free allowance is 0), so with a plain free AI Studio key Google answers
"quota exceeded, limit: 0". This module turns that into a plain-language message. Options: enable billing on the
Google project, or set GEMINI_IMAGE_API_KEY to a billed key used ONLY for images (chat stays on the free key).
"""

import base64
import io
import json
import os
import re
import threading
import urllib.error
import urllib.request
import uuid
from collections import OrderedDict

import image_search

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash-image"
ASPECTS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
MAX_IMAGE_BYTES = 8_000_000
PREVIEW_MAX_PX = 768
STORE_LIMIT = 12

CF_ROOT = "https://api.cloudflare.com/client/v4/accounts"
CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
CF_LABEL = "FLUX.1 schnell on Cloudflare"
GOOGLE_LABEL = "Gemini"
_CF_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")

_SAFETY_REASONS = {"IMAGE_SAFETY", "PROHIBITED_CONTENT", "SAFETY", "IMAGE_PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_OTHER"}


class ImageGenError(Exception):
    """Carries a message that is safe and clear enough to show the user."""

    def __init__(self, user_message):
        super().__init__(user_message)
        self.user_message = user_message


def _error_message(code, body_text, model):
    low = (body_text or "").lower()
    if code == 429:
        if "limit: 0" in low or ("free" in low and "tier" in low) or "billing" in low:
            return ("Google's free API tier doesn't include image generation (its allowance for this key is 0). "
                    "Image models need billing enabled on the Google project - or put a billed key in "
                    "GEMINI_IMAGE_API_KEY just for images. Chat keeps using the free key.")
        return "The image allowance is used up for now (per-minute or daily). Try again a bit later."
    if code in (401, 403):
        return "Google rejected the API key for image generation. Check the key, and that the Generative Language API is enabled for its project."
    if code == 404:
        return "The image model '%s' wasn't found for this key. Set GEMINI_IMAGE_MODEL to an image model your key can use." % model
    if code == 400:
        if "modalit" in low or "image" in low and "support" in low:
            return "'%s' can't produce images. Set GEMINI_IMAGE_MODEL to an image-capable model." % model
        return "Google refused the request: " + (body_text or "bad request")[:200]
    return "Google's image service had a problem (error %s). Try again in a moment." % code


def _post_json(url, key, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate(api_key, prompt, model=None, aspect="1:1", timeout=90):
    """Returns [{'mime': ..., 'bytes': ...}, ...] (usually one image). Raises ImageGenError."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageGenError("There was no description of the picture to make.")
    if len(prompt) > 4000:
        prompt = prompt[:4000]
    model = (model or DEFAULT_MODEL).strip()
    aspect = aspect if aspect in ASPECTS else "1:1"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect}},
    }
    try:
        data = _post_json("%s/%s:generateContent" % (API_ROOT, model), api_key, body, timeout)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
            msg = (json.loads(raw).get("error") or {}).get("message", raw)
        except Exception:
            msg = ""
        raise ImageGenError(_error_message(e.code, msg, model))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ImageGenError("Couldn't reach Google's image service (network problem or it took too long). Try again.")
    except ValueError:
        raise ImageGenError("Google's image service sent back something unreadable. Try again.")

    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise ImageGenError("Google's safety filter blocked that prompt (%s). Try describing it differently." % block)

    images, texts, finish = [], [], None
    for cand in data.get("candidates") or []:
        finish = finish or cand.get("finishReason")
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                try:
                    raw = base64.b64decode(inline["data"])
                except Exception:
                    continue
                mime = image_search._sniff_mime(raw)            # trust the bytes, not the label
                if mime and 0 < len(raw) <= MAX_IMAGE_BYTES:
                    images.append({"mime": mime, "bytes": raw})
            elif part.get("text"):
                texts.append(part["text"])
    if images:
        return images
    if finish in _SAFETY_REASONS:
        raise ImageGenError("Google's safety filter declined to make that picture (%s). Try describing it differently." % finish)
    note = (" It said: " + texts[0].strip()[:220]) if texts else ""
    raise ImageGenError("The image model didn't return a picture." + note)


# ---------------------------------------------------------------------------
# Cloudflare Workers AI - FLUX.1 [schnell] (the free, privacy-respecting alternative)
# ---------------------------------------------------------------------------

def _cf_error_message(code, body_text):
    low = (body_text or "").lower()
    if code == 429 or "4006" in low or "neuron" in low or ("daily" in low and ("limit" in low or "allocation" in low)):
        return ("Cloudflare's free daily allowance (10,000 Neurons) is used up. It resets at 00:00 UTC "
                "(1 am in Nigeria), so image generation is available again after that.")
    if code in (401, 403) or "authentication" in low or "unauthorized" in low:
        return ("Cloudflare rejected the API token. It needs the 'Workers AI' permission, and "
                "CLOUDFLARE_ACCOUNT_ID must be the same account the token was made in.")
    if code == 404:
        return "Cloudflare couldn't find the image model. Check CLOUDFLARE_ACCOUNT_ID."
    if "nsfw" in low or "flagged" in low or "inappropriate" in low or "safety" in low:
        return "Cloudflare's safety filter declined that picture. Try describing it differently."
    if code == 400:
        return "Cloudflare refused the request: " + (body_text or "bad request")[:200]
    return "Cloudflare's image service had a problem (error %s). Try again in a moment." % code


def _crop_to_aspect(raw, aspect):
    """FLUX schnell makes square pictures; centre-crop to the shape asked for (needs Pillow, else left square)."""
    if aspect == "1:1" or aspect not in ASPECTS:
        return raw, image_search._sniff_mime(raw) or "image/jpeg"
    try:
        from PIL import Image
        a, b = [int(x) for x in aspect.split(":")]
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = im.size
        if w * b > h * a:                       # too wide: trim the sides
            nw = int(h * a / b); x0 = (w - nw) // 2; im = im.crop((x0, 0, x0 + nw, h))
        else:                                   # too tall: trim top and bottom
            nh = int(w * b / a); y0 = (h - nh) // 2; im = im.crop((0, y0, w, y0 + nh))
        out = io.BytesIO(); im.save(out, "JPEG", quality=92, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return raw, image_search._sniff_mime(raw) or "image/jpeg"


def generate_cloudflare(account_id, token, prompt, aspect="1:1", steps=4, timeout=90):
    """Same return shape as generate(). Raises ImageGenError with a message safe to show."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageGenError("There was no description of the picture to make.")
    if not _CF_ACCOUNT_RE.match(account_id or ""):
        raise ImageGenError("CLOUDFLARE_ACCOUNT_ID doesn't look right (it's the long code on your Cloudflare dashboard).")
    aspect = aspect if aspect in ASPECTS else "1:1"
    if aspect != "1:1":
        prompt = prompt[:1900] + " (Composition framed for a %s picture, main subject centred.)" % aspect
    prompt = prompt[:2000]                       # the model's limit is 2048 characters
    url = "%s/%s/ai/run/%s" % (CF_ROOT, account_id, CF_MODEL)
    body = {"prompt": prompt, "steps": max(1, min(8, int(steps)))}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            raw_err = e.read().decode("utf-8", "replace")
            errs = (json.loads(raw_err).get("errors") or [{}])
            msg = " ".join("%s %s" % (x.get("code", ""), x.get("message", "")) for x in errs).strip() or raw_err
        except Exception:
            msg = ""
        raise ImageGenError(_cf_error_message(e.code, msg))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ImageGenError("Couldn't reach Cloudflare's image service (network problem or it took too long). Try again.")
    except ValueError:
        raise ImageGenError("Cloudflare sent back something unreadable. Try again.")
    if not data.get("success", True):
        errs = data.get("errors") or [{}]
        raise ImageGenError(_cf_error_message(400, " ".join("%s %s" % (x.get("code", ""), x.get("message", "")) for x in errs)))
    b64 = (data.get("result") or {}).get("image")
    if not b64:
        raise ImageGenError("Cloudflare's image model didn't return a picture. Try again.")
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise ImageGenError("Cloudflare sent back a damaged picture. Try again.")
    if not image_search._sniff_mime(raw) or not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ImageGenError("Cloudflare's image model didn't return a usable picture. Try again.")
    raw, mime = _crop_to_aspect(raw, aspect)
    return [{"mime": mime, "bytes": raw}]


# ---------------------------------------------------------------------------
# Choosing a provider
# ---------------------------------------------------------------------------

def provider_order(env, chat_key):
    """
    IMAGE_PROVIDER = auto (default) | google | cloudflare
      auto: a billed Google key (GEMINI_IMAGE_API_KEY) -> Google first (best quality), Cloudflare as the backup.
            otherwise, Cloudflare if it's set up (free + privacy-respecting; Google's free key can't make images).
            otherwise Google with the chat key (works only if that key's project has billing).
    """
    pref = (env.get("IMAGE_PROVIDER") or "auto").strip().lower()
    cf_ok = bool(env.get("CLOUDFLARE_ACCOUNT_ID") and env.get("CLOUDFLARE_API_TOKEN"))
    g_key = env.get("GEMINI_IMAGE_API_KEY") or ""
    if pref == "google":
        return ["google"]
    if pref == "cloudflare":
        return ["cloudflare"] if cf_ok else ["google"]
    if g_key:
        return ["google", "cloudflare"] if cf_ok else ["google"]
    return ["cloudflare"] if cf_ok else ["google"]


def generate_any(prompt, aspect, env, chat_key):
    """Try the providers in order. Returns (images, label, usage_key). Raises ImageGenError listing what went wrong."""
    problems = []
    for name in provider_order(env, chat_key):
        try:
            if name == "cloudflare":
                imgs = generate_cloudflare(env["CLOUDFLARE_ACCOUNT_ID"].strip(), env["CLOUDFLARE_API_TOKEN"].strip(), prompt, aspect=aspect)
                return imgs, CF_LABEL, "cloudflare-flux-1-schnell"
            model = env.get("GEMINI_IMAGE_MODEL") or DEFAULT_MODEL
            key = env.get("GEMINI_IMAGE_API_KEY") or chat_key
            imgs = generate(key, prompt, model=model, aspect=aspect)
            return imgs, GOOGLE_LABEL, model
        except ImageGenError as e:
            problems.append(("Google" if name == "google" else "Cloudflare") + ": " + e.user_message)
    raise ImageGenError(" | ".join(problems))


# ---- preview + short-term storage of what was generated ----

def make_preview(raw, max_px=PREVIEW_MAX_PX):
    """(data_url, (width, height)) for the chat bubble. A JPEG about 100-200 KB instead of a multi-MB PNG."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        size = im.size
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), size
    except Exception:
        mime = image_search._sniff_mime(raw) or "image/png"
        return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii")), (None, None)


_store = OrderedDict()
_store_lock = threading.Lock()


def store_image(raw, mime, prompt):
    gid = uuid.uuid4().hex[:16]
    with _store_lock:
        _store[gid] = {"bytes": raw, "mime": mime, "prompt": prompt}
        while len(_store) > STORE_LIMIT:
            _store.popitem(last=False)
    return gid


def get_image(gid):
    with _store_lock:
        return _store.get(gid)
