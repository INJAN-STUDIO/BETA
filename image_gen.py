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

Your own pictures: pictures attached to a chat message are kept (app.py calls set_user_refs) and sent to FLUX.2 first,
ahead of any searched pictures, up to 4 in total.

Reference pictures: when a request names a character, prompt_refiner also hands back 2-3 small reference pictures and
generate_any() sends them to FLUX.2 [klein 4B] on Cloudflare (it can draw from up to 4 pictures). On any failure it falls back
to FLUX.1 schnell with the refined text prompt. Switch off with USE_REFERENCE_IMAGES=off. Needs Pillow.

Prompt refiner: before a Cloudflare picture is drawn, prompt_refiner.py works out which fictional characters the
request names, finds a written description of how they look (characters.json, the saved cache, or by having Gemini
look at a few reference pictures) and rewrites the request as a detailed paragraph. See that file for the settings.

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
# FLUX.2 models that can draw from up to 4 reference pictures. klein-4b is the default because it is cheap
# (about 120 Neurons per 1-megapixel picture with 3 references, vs about 4,100 for flux-2-dev at 20 steps).
CF_REF_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
CF_REF_LABEL = "FLUX.2 on Cloudflare (with reference pictures)"
GOOGLE_LABEL = "Gemini"
_CF_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")

_SAFETY_REASONS = {"IMAGE_SAFETY", "PROHIBITED_CONTENT", "SAFETY", "IMAGE_PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_OTHER"}


class ImageGenError(Exception):
    """Carries a message that is safe and clear enough to show the user. safety=True means the provider's content filter said no."""

    def __init__(self, user_message, safety=False):
        super().__init__(user_message)
        self.user_message = user_message
        self.safety = safety


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
# Cloudflare Workers AI - FLUX.2 with reference pictures
# ---------------------------------------------------------------------------

def _multipart(fields, files):
    """Build a multipart/form-data body by hand (FLUX.2 on Workers AI only accepts multipart)."""
    boundary = "----betaform" + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (boundary, k, v)).encode("utf-8"))
    for k, (fname, mime, data) in files.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: %s\r\n\r\n'
                   % (boundary, k, fname, mime)).encode("utf-8"))
        out.write(data)
        out.write(b"\r\n")
    out.write(("--%s--\r\n" % boundary).encode("utf-8"))
    return out.getvalue(), "multipart/form-data; boundary=" + boundary


def _flux2_size(aspect):
    """Width/height (multiples of 16, 256-1920) for about one megapixel in the shape asked for."""
    try:
        a, b = [int(x) for x in aspect.split(":")]
    except Exception:
        a, b = 1, 1
    scale = (1024 * 1024 / float(a * b)) ** 0.5
    clamp = lambda v: max(256, min(1920, int(round(v / 16.0)) * 16))
    return clamp(a * scale), clamp(b * scale)


_SAFETY_WORDS = ("nsfw", "flagged", "inappropriate", "safety", "moderation")


def _flux2_fail(code, msg):
    """Log Cloudflare's own words (the friendly message hides them) and raise."""
    print("[B.E.T.A.] Cloudflare FLUX.2 error (HTTP %s): %s" % (code, str(msg)[:300]))
    raise ImageGenError(_cf_error_message(code, msg), safety=any(w in str(msg).lower() for w in _SAFETY_WORDS))


def _flux2_request(url, token, fields, files, timeout):
    """One multipart call to a FLUX.2 model. Returns the decoded result dict or raises ImageGenError."""
    body, ctype = _multipart(fields, files)
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": ctype, "Authorization": "Bearer " + token})
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
        _flux2_fail(e.code, msg)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ImageGenError("Couldn't reach Cloudflare's image service (network problem or it took too long). Try again.")
    except ValueError:
        raise ImageGenError("Cloudflare sent back something unreadable. Try again.")
    if not data.get("success", True):
        errs = data.get("errors") or [{}]
        _flux2_fail(400, " ".join("%s %s" % (x.get("code", ""), x.get("message", "")) for x in errs))
    return data


def generate_cloudflare_flux2(account_id, token, prompt, refs, aspect="1:1", steps=20, model=None, timeout=120):
    """FLUX.2 (klein 4B by default) with up to 4 reference pictures ([(mime, bytes), ...], each under 512x512).
    Same return shape as generate(). Raises ImageGenError with a message safe to show.

    'steps' is only sent to flux-2-dev: the klein models have a fixed number of steps and may reject the field.
    If Cloudflare answers "Invalid input", it is retried once with only the prompt and pictures (no size/steps) and
    the log says which version worked - that tells us which field the model didn't like."""
    prompt = (prompt or "").strip()[:1900]
    if not prompt:
        raise ImageGenError("There was no description of the picture to make.")
    if not refs:
        raise ImageGenError("No reference pictures to draw from.")
    if not _CF_ACCOUNT_RE.match(account_id or ""):
        raise ImageGenError("CLOUDFLARE_ACCOUNT_ID doesn't look right (it's the long code on your Cloudflare dashboard).")
    aspect = aspect if aspect in ASPECTS else "1:1"
    model = (model or CF_REF_MODEL).strip()
    w, h = _flux2_size(aspect)
    full = {"prompt": prompt, "width": w, "height": h}
    if "flux-2-dev" in model:
        full["steps"] = max(1, min(50, int(steps)))
    minimal = {"prompt": prompt}
    files = {}
    for i, (mime, data) in enumerate(refs[:4]):
        files["input_image_%d" % i] = ("ref%d.jpg" % i, mime or "image/jpeg", data)
    url = "%s/%s/ai/run/%s" % (CF_ROOT, account_id, model)

    try:
        data = _flux2_request(url, token, full, files, timeout)
    except ImageGenError as e:
        text = e.user_message.lower()
        if "invalid input" not in text and "8001" not in text:
            raise
        print("[B.E.T.A.] %s said 'Invalid input' with fields=%s, image sizes=%s bytes. Retrying with prompt + pictures only."
              % (model, sorted(full), [len(r[1]) for r in refs[:4]]))
        data = _flux2_request(url, token, minimal, files, timeout)
        print("[B.E.T.A.] The retry WORKED, so the size/steps fields were the problem (picture comes out at the default shape).")

    b64 = (data.get("result") or {}).get("image")
    if not b64:
        raise ImageGenError("Cloudflare's FLUX.2 model didn't return a picture. Try again.")
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise ImageGenError("Cloudflare sent back a damaged picture. Try again.")
    mime = image_search._sniff_mime(raw)
    if not mime or not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ImageGenError("Cloudflare's FLUX.2 model didn't return a usable picture. Try again.")
    return [{"mime": mime, "bytes": raw}]


# ---------------------------------------------------------------------------
# Pictures the user attached to the current chat message (used as references)
# ---------------------------------------------------------------------------
# app.py calls set_user_refs() before a reply is worked on and clear_user_refs() afterwards. Only one reply is ever
# being worked on at a time, so a single shared slot is enough. Pictures are shrunk to under 512px (FLUX.2's limit).

USER_REF_MAX = 4
USER_REF_MIN_PX = 64          # Cloudflare rejects anything smaller
USER_REF_MAX_PX = 480
_user_refs = []
_user_refs_lock = threading.Lock()


def _shrink_reference(raw):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        try:
            im.draft("RGB", (USER_REF_MAX_PX * 2, USER_REF_MAX_PX * 2))
        except Exception:
            pass
        im.thumbnail((USER_REF_MAX_PX, USER_REF_MAX_PX))
        im = im.convert("RGB")
        if min(im.size) < USER_REF_MIN_PX:
            return None
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def set_user_refs(paths):
    """Remember the pictures (file paths) attached to this message. Non-pictures and unreadable files are skipped."""
    refs = []
    for path in paths or []:
        if not str(path).lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            continue
        try:
            with open(path, "rb") as f:
                raw = f.read(MAX_IMAGE_BYTES + 1)
        except Exception:
            continue
        small = _shrink_reference(raw) if 0 < len(raw) <= MAX_IMAGE_BYTES else None
        if small:
            refs.append(("image/jpeg", small))
        if len(refs) >= USER_REF_MAX:
            break
    with _user_refs_lock:
        _user_refs[:] = refs
    return len(refs)


def clear_user_refs():
    with _user_refs_lock:
        _user_refs[:] = []


def get_user_refs():
    with _user_refs_lock:
        return list(_user_refs)


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
    """Try the providers in order. Returns (images, label, usage_key). Raises ImageGenError listing what went wrong.

    For Cloudflare (FLUX schnell, which doesn't really know characters) the prompt first goes through
    prompt_refiner: detect named characters -> look up how they look -> rewrite as a detailed description.
    Pictures the user attached to the message (and searched pictures of named characters) go to FLUX.2, which can
    draw from them. If the refiner or FLUX.2 has any trouble we carry on with plain text, so a picture still comes out.
    """
    problems = []
    order = provider_order(env, chat_key)
    use_refs = (env.get("USE_REFERENCE_IMAGES") or "on").strip().lower() not in ("off", "0", "false", "no")
    user_refs = get_user_refs() if use_refs else []
    refined = {"prompt": prompt, "characters": [], "refined": False, "refs": [], "ref_prompt": prompt}
    if "cloudflare" in order:
        try:
            import prompt_refiner
            refined = prompt_refiner.refine_for_image(prompt, aspect, env, chat_key, user_refs=user_refs)
        except Exception as e:
            print("[B.E.T.A.] prompt refiner unavailable, using the original prompt: %s" % e)
        if user_refs and not refined.get("refs"):          # refiner failed: the user's pictures must not be lost
            refined["refs"] = list(user_refs)[:USER_REF_MAX]
            refined["ref_prompt"] = (refined["prompt"] + " Use the attached reference picture(s) as the visual reference - "
                                     "stay faithful to what they show except where the request asks for a change.")[:1900]
    for name in order:
        try:
            if name == "cloudflare":
                # 1) reference pictures (yours and/or a named character's) -> FLUX.2, which can draw from pictures.
                #    If it fails for any reason (quota, error), quietly carry on with schnell below.
                if refined.get("refs") and use_refs:
                    try:
                        steps2 = int(env.get("CF_REF_STEPS") or 20)           # only used by flux-2-dev
                    except ValueError:
                        steps2 = 20
                    ref_model = (env.get("CF_REF_MODEL") or CF_REF_MODEL).strip()
                    try:
                        imgs = generate_cloudflare_flux2(env["CLOUDFLARE_ACCOUNT_ID"].strip(), env["CLOUDFLARE_API_TOKEN"].strip(),
                                                         refined["ref_prompt"], refined["refs"], aspect=aspect, steps=steps2,
                                                         model=ref_model)
                        return imgs, CF_REF_LABEL, "cloudflare-" + ref_model.split("/")[-1]
                    except ImageGenError as e:
                        print("[B.E.T.A.] FLUX.2 with reference pictures failed: %s" % e.user_message)
                        # The safety filter reviews the reference pictures too, and pictures from the web can trip it. If it
                        # said no to the set, try each reference on its own and keep the first one it accepts.
                        refs_all = refined["refs"]
                        if e.safety and len(refs_all) > 1:
                            print("[B.E.T.A.] trying the reference pictures one at a time")
                            single_prompt = (refined["prompt"] + " Use the attached reference picture as the visual reference - "
                                             "stay faithful to what it shows except where the request asks for a change.")[:1900]
                            for idx, one in enumerate(refs_all[:4]):
                                try:
                                    imgs = generate_cloudflare_flux2(env["CLOUDFLARE_ACCOUNT_ID"].strip(), env["CLOUDFLARE_API_TOKEN"].strip(),
                                                                     single_prompt, [one], aspect=aspect, steps=steps2, model=ref_model)
                                    print("[B.E.T.A.] FLUX.2 accepted reference picture #%d on its own" % idx)
                                    return imgs, CF_REF_LABEL + " (one reference)", "cloudflare-" + ref_model.split("/")[-1]
                                except ImageGenError as e2:
                                    if not e2.safety:
                                        break
                        print("[B.E.T.A.] using schnell instead")
                # 2) text-only FLUX schnell. Characters get a few more steps (more detail) - costs more of the daily free allowance
                try:
                    steps = int(env.get("CF_IMAGE_STEPS") or (6 if refined["characters"] else 4))
                except ValueError:
                    steps = 4
                imgs = generate_cloudflare(env["CLOUDFLARE_ACCOUNT_ID"].strip(), env["CLOUDFLARE_API_TOKEN"].strip(),
                                           refined["prompt"], aspect=aspect, steps=steps)
                label = CF_LABEL + (" (your reference picture couldn't be used this time)" if user_refs else "")
                return imgs, label, "cloudflare-flux-1-schnell"
            model = env.get("GEMINI_IMAGE_MODEL") or DEFAULT_MODEL
            key = env.get("GEMINI_IMAGE_API_KEY") or chat_key
            imgs = generate(key, prompt, model=model, aspect=aspect)    # Gemini understands characters itself
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
