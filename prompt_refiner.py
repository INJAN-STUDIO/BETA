"""
B.E.T.A. - prompt refiner for image generation.

FLUX schnell (the free Cloudflare model) draws well but doesn't really know who a character is, so a bare
"Itachi" comes out as a generic anime guy in a black cloak. This module borrows Gemini's trick: let a smart
text model do the understanding first, then hand the image model a detailed description.

Steps (refine_for_image):
  1. DETECT   - ask a small text model which fictional characters the request names.
  2. LOOK UP  - for each character, find a written description of how they look:
                a. characters.json (hand-written overrides, optional) wins if it has the character;
                b. else the saved cache (Supabase via storage.py) - free and instant;
                c. else search for 2-3 reference thumbnails (Serper), have Gemini LOOK at them and write down the
                   traits they share, then save that to the cache so it only ever happens once per character.
  3. REFINE   - rewrite the request as one flowing ~80-word paragraph that spells those traits out.

  4. REFERENCES - the same 2-3 reference thumbnails (shrunk to under 512px and cached, one store key per character)
                are handed back so image_gen.py can give them to FLUX.2 [dev], which can draw from pictures.

Safety net: every step is wrapped so that ANY problem (no key, quota used up, timeout, odd reply) just means the
original prompt is used unchanged - image generation is never blocked by this module.

Settings (all optional, environment variables):
  PROMPT_REFINER = on (default) | off      switch the whole thing off
  GEMINI_MODELS                            same variable beta_agent.py uses; first entries are tried in order
  GROQ_API_KEY / GROQ_MODEL                text-only fallback when Gemini is out of quota (it can't look at pictures)
  SERPER_API_KEY                           needed for the reference-picture search (already used by B.E.T.A.)
  USE_REFERENCE_IMAGES = on (default) | off   hand reference pictures to FLUX.2 (needs Pillow to shrink them)
"""

import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

import image_search

GEMINI_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GEMINI_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

CALL_TIMEOUT = 12        # seconds for any single model call
TOTAL_BUDGET = 35        # seconds for the whole refine, then we give up and use the original prompt
MAX_REFS = 3             # reference pictures to show the vision model
MAX_CHARACTERS = 2
MAX_FLUX2_REFS = 4       # FLUX.2 [dev] takes at most 4 reference pictures per image
REF_MAX_PX = 480         # ...and each must be under 512x512
IMG_CACHE_PREFIX = "char_img2:"   # v2: older entries held tiny pictures
MIN_REF_PX = 128         # Cloudflare rejects pictures under 64px; under ~128px they are useless as a reference anyway
CACHE_KEY = "char_refs"
CACHE_LIMIT = 150
OVERRIDE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.json")


def _log(msg):
    print("[B.E.T.A. refiner] " + msg)


# ---------------------------------------------------------------------------
# Talking to the text/vision models (plain HTTPS, no extra packages)
# ---------------------------------------------------------------------------

def _usage():
    """ALPHA's daily-usage tracker, if it's loaded (it is on the server). Never required."""
    try:
        import agent_core as ac
        return ac.USAGE
    except Exception:
        return None


def _gemini_models(env):
    chain = [m.strip() for m in (env.get("GEMINI_MODELS") or "").split(",") if m.strip()]
    return chain or list(DEFAULT_GEMINI_MODELS)


def _call_gemini(api_key, env, system, parts, json_mode, max_tokens, deadline):
    """Try each Gemini model in order. Returns text, or None if none of them answered."""
    if not api_key:
        return None
    usage = _usage()
    for model in _gemini_models(env):
        remaining = deadline - time.time()
        if remaining < 2:
            return None
        try:
            if usage and usage.is_exhausted(model):
                continue
        except Exception:
            pass
        cfg = {"temperature": 0.6, "maxOutputTokens": max_tokens}
        if json_mode:
            cfg["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": cfg}
        req = urllib.request.Request(
            "%s/%s:generateContent" % (GEMINI_ROOT, model), data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=min(CALL_TIMEOUT, remaining)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            _log("Gemini %s answered HTTP %s" % (model, e.code))
            continue                             # quota/overload on this model - try the next one
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            _log("Gemini %s call failed: %s" % (model, e))
            continue
        texts = []
        for cand in data.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                if part.get("text") and not part.get("thought"):
                    texts.append(part["text"])
        text = "".join(texts).strip()
        if text:
            try:
                if usage:
                    usage.record(model)
            except Exception:
                pass
            return text
    return None


def _call_groq(env, system, user_text, max_tokens, deadline):
    """Text-only fallback. Returns text or None."""
    key = (env.get("GROQ_API_KEY") or "").strip()
    remaining = deadline - time.time()
    if not key or remaining < 2:
        return None
    model = (env.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL).strip()
    body = {"model": model, "temperature": 0.6, "max_tokens": max(max_tokens, 1200),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_text}]}
    req = urllib.request.Request(GROQ_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key,
                                          "User-Agent": "beta-prompt-refiner/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=min(CALL_TIMEOUT, remaining)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception as e:
        _log("Groq call failed: %s" % e)
        return None
    text = text.strip()
    if text:
        try:
            usage = _usage()
            if usage:
                usage.record(model)
        except Exception:
            pass
    return text or None


def _llm_text(api_key, env, system, user_text, json_mode, max_tokens, deadline):
    parts = [{"text": user_text}]
    return (_call_gemini(api_key, env, system, parts, json_mode, max_tokens, deadline)
            or _call_groq(env, system, user_text, max_tokens, deadline))


def _parse_json(text):
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Step 1: which characters are named?
# ---------------------------------------------------------------------------

DETECT_SYSTEM = (
    "You help an image generator. Read the picture request and list any FICTIONAL characters it names "
    "(anime, manga, games, cartoons, comics, films). Never list real people. "
    'Reply with JSON only, like {"characters":[{"name":"Itachi Uchiha","series":"Naruto"}]}, '
    'or {"characters":[]} if none are named. At most 2 characters. '
    "Use the character's full proper name and the series they come from."
)


def detect_characters(prompt, api_key, env, deadline):
    text = _llm_text(api_key, env, DETECT_SYSTEM, "Picture request: " + prompt[:1500], True, 300, deadline)
    data = _parse_json(text) or {}
    found = []
    for c in (data.get("characters") or [])[:MAX_CHARACTERS]:
        if isinstance(c, dict) and isinstance(c.get("name"), str) and 2 <= len(c["name"].strip()) <= 60:
            series = c.get("series") if isinstance(c.get("series"), str) else ""
            found.append({"name": c["name"].strip(), "series": series.strip()[:60]})
    return found


# ---------------------------------------------------------------------------
# Step 2: how does this character look? (override file -> cache -> look at reference pictures)
# ---------------------------------------------------------------------------

def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def _get_store():
    try:
        import storage
        return storage.get_store()
    except Exception:
        return None


def _override_for(name):
    """Hand-written traits from characters.json ({"itachi uchiha": "long black hair ...", ...})."""
    try:
        with open(OVERRIDE_FILE, "r", encoding="utf-8") as f:
            table = json.load(f)
    except Exception:
        return ""
    n = _norm(name)
    for key, traits in table.items():
        k = _norm(key)
        if key.startswith("_") or not isinstance(traits, str) or len(k) < 3:
            continue
        if k in n or n in k:
            return traits.strip()
    return ""


def _cache_get(store, key):
    try:
        entry = (store.get(CACHE_KEY, None) or {}).get(key)
        return (entry or {}).get("traits", "") if isinstance(entry, dict) else ""
    except Exception:
        return ""


def _cache_put(store, key, name, traits):
    try:
        table = store.get(CACHE_KEY, None)
        table = dict(table) if isinstance(table, dict) else {}
        table[key] = {"name": name, "traits": traits, "ts": int(time.time())}
        if len(table) > CACHE_LIMIT:                       # drop the oldest entries
            for k, _ in sorted(table.items(), key=lambda kv: kv[1].get("ts", 0))[:len(table) - CACHE_LIMIT]:
                table.pop(k, None)
        store.set(CACHE_KEY, table)
    except Exception as e:
        _log("couldn't save to the cache: %s" % e)


def _tile_image(tile):
    """(mime, bytes) from a gallery tile's thumbnail, or None."""
    raw = tile.get("bytes") if isinstance(tile, dict) else None
    if not raw:
        thumb = tile.get("thumb") if isinstance(tile, dict) else None
        if isinstance(thumb, str) and thumb.startswith("data:") and ";base64," in thumb:
            try:
                raw = base64.b64decode(thumb.split(",", 1)[1])
            except Exception:
                raw = None
    if not raw:
        return None
    mime = image_search._sniff_mime(raw)
    return (mime, raw) if mime else None


def _data_url_image(data_url):
    """(mime, bytes) from a data: URL, or None."""
    if not isinstance(data_url, str) or ";base64," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
    except Exception:
        return None
    mime = image_search._sniff_mime(raw)
    return (mime, raw) if mime else None


def _fetch_references(name, series, env):
    """Reference pictures for a character, as [(mime, bytes), ...].
    Prefers the FULL-size pictures (image_search's safe downloader: public hosts only, size caps, real-image check),
    because the search thumbnails are only ~2 KB - under the 64px minimum Cloudflare accepts. If no full-size
    picture can be downloaded, falls back to the thumbnails (fine for describing, too small for FLUX.2)."""
    key = (env.get("SERPER_API_KEY") or "").strip()
    if not key:
        return []
    query = ("%s %s character official art" % (name, series)).strip()
    results = image_search.search_serper_images(key, query, MAX_REFS + 3)
    if not results:
        return []

    # 1) full-size pictures (skip ones Serper says are small), downloaded in parallel
    cands = [r for r in results if r.get("full_url")
             and min(r.get("width") or 9999, r.get("height") or 9999) >= 256][:MAX_REFS + 3]
    out = []
    if cands:
        limit = min(getattr(image_search, "FULL_MAX_BYTES", 3_000_000), 3_000_000)
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=6) as pool:
                loaded = list(pool.map(lambda it: image_search.fetch_image_data_url(it["full_url"], max_bytes=limit), cands))
            out = [i for i in (_data_url_image(u) for u in loaded) if i]
        except Exception as e:
            _log("full-size download failed: %s" % e)
            out = []
    if out:
        return out[:MAX_REFS + 2]                  # a couple of spares in case one can't be shrunk

    # 2) fallback: the small thumbnails
    tiles = image_search.build_gallery(results, want=MAX_REFS) or []
    return [i for i in (_tile_image(t) for t in tiles) if i][:MAX_REFS]


DESCRIBE_SYSTEM = ("You describe how a fictional character looks so an artist who has never seen them can draw "
                   "them accurately. Be concrete and brief.")


def _describe_from_references(name, series, refs, api_key, env, deadline):
    who = "%s from %s" % (name, series) if series else name
    parts = [{"text": (
        "These are reference pictures of %s. In about 60 words of plain text, list the traits of their appearance "
        "that are the same across the pictures: hair (colour, length, style), face (eye colour, marks, lines), "
        "skin tone, build and apparent age, outfit and accessories with their colours. Ignore the background, "
        "art style, watermarks and any text. If the pictures do not clearly show this character, reply with "
        "exactly: NONE" % who)}]
    for mime, raw in refs:
        parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(raw).decode("ascii")}})
    text = _call_gemini(api_key, env, DESCRIBE_SYSTEM, parts, False, 400, deadline)   # Groq can't see pictures
    text = (text or "").strip()
    if not text or text.upper().startswith("NONE") or len(text) < 25:
        return ""
    return re.sub(r"\s+", " ", text)[:600]


def _shrink_for_flux2(raw):
    """JPEG bytes at most REF_MAX_PX on the long side (FLUX.2 wants references under 512x512). None without Pillow."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        try:
            im.draft("RGB", (REF_MAX_PX * 2, REF_MAX_PX * 2))   # JPEG: decode at reduced size, saves memory on Render
        except Exception:
            pass
        im.thumbnail((REF_MAX_PX, REF_MAX_PX))
        im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _img_size(raw):
    try:
        from PIL import Image
        return Image.open(io.BytesIO(raw)).size
    except Exception:
        return (0, 0)


def _prepared_refs(char, env, store, memo=None):
    """[(mime, bytes), ...] reference pictures for a character, already shrunk. Cached per character in the store
    so the web search only happens the first time. Returns [] if nothing usable (no Serper key, no Pillow...)."""
    name, series = char["name"], char.get("series", "")
    key = _norm(name) + "|" + _norm(series)
    if memo is not None and key in memo:
        return memo[key]
    out = []
    ck = IMG_CACHE_PREFIX + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    if store is not None:
        try:
            entry = store.get(ck, None)
            if isinstance(entry, dict):
                for b64 in entry.get("imgs") or []:
                    raw = base64.b64decode(b64)
                    mime = image_search._sniff_mime(raw)
                    if mime:
                        out.append((mime, raw))
        except Exception:
            out = []
    if not out:
        try:
            for _mime, raw in _fetch_references(name, series, env):
                small = _shrink_for_flux2(raw)
                if small:
                    out.append(("image/jpeg", small))
                if len(out) >= MAX_REFS:
                    break
        except Exception as e:
            _log("reference pictures unavailable for %s: %s" % (name, e))
            out = []
        if out and store is not None:
            try:
                store.set(ck, {"name": name, "ts": int(time.time()),
                               "imgs": [base64.b64encode(r).decode("ascii") for _m, r in out]})
            except Exception as e:
                _log("couldn't cache reference pictures: %s" % e)
    if memo is not None:
        memo[key] = out
    return out


def traits_for(char, api_key, env, store, deadline, memo=None):
    name, series = char["name"], char.get("series", "")
    over = _override_for(name)
    if over:
        return over
    key = _norm(name) + "|" + _norm(series)
    if store is not None:
        cached = _cache_get(store, key)
        if cached:
            return cached
    try:
        refs = _prepared_refs(char, env, store, memo)
    except Exception as e:
        _log("reference search failed for %s: %s" % (name, e))
        refs = []
    if not refs:
        return ""
    traits = _describe_from_references(name, series, refs, api_key, env, deadline)
    if traits and store is not None:
        _cache_put(store, key, name, traits)
    return traits


# ---------------------------------------------------------------------------
# Step 3: write the detailed prompt
# ---------------------------------------------------------------------------

REFINE_SYSTEM = (
    "You write prompts for an image model (FLUX schnell). Turn the user's picture request into ONE flowing "
    "paragraph of 70-100 words, written as a natural description rather than a keyword list.\n"
    "Rules:\n"
    "- Keep everything the user asked for (subject, setting, style, colours, mood). Do not add story or extra characters.\n"
    "- For each character that has a trait list, describe exactly those traits (hair, face marks, outfit, colours). "
    "The trait lists are ground truth - do not contradict them. Keep the character's name in the paragraph too.\n"
    "- Add composition (shot type, camera angle), lighting and atmosphere.\n"
    "- If it is an anime, cartoon or game character and the user asked for no other style, use a polished anime "
    "illustration style with clean line art and cel shading.\n"
    "- Do not name artists, do not ask for text, words or captions inside the picture, and do not use negative "
    "phrases such as 'no blur'.\n"
    "- Reply with the paragraph only."
)


def write_prompt(prompt, aspect, traits_by_name, api_key, env, deadline):
    lines = ["Picture request: " + prompt[:1500], "Picture shape: " + (aspect or "1:1")]
    if traits_by_name:
        lines.append("\nCharacter trait lists:")
        lines += ["- %s: %s" % (n, t) for n, t in traits_by_name]
    text = _llm_text(api_key, env, REFINE_SYSTEM, "\n".join(lines), False, 600, deadline)
    text = re.sub(r"\s+", " ", (text or "").strip().strip('"'))
    if len(text) < 40:
        return ""
    return text[:1500]


# ---------------------------------------------------------------------------
# The one function image_gen.py calls
# ---------------------------------------------------------------------------

def refine_for_image(prompt, aspect, env, chat_key):
    """Returns {'prompt': str, 'characters': [names], 'refined': bool, 'refs': [(mime, bytes)], 'ref_prompt': str}.
    'prompt' is for text-only models (FLUX schnell); 'refs' + 'ref_prompt' are for FLUX.2 [dev], which can draw from
    pictures. Never raises; on any trouble the original prompt comes back unchanged and refs is empty."""
    result = {"prompt": prompt, "characters": [], "refined": False, "refs": [], "ref_prompt": prompt}
    if (env.get("PROMPT_REFINER") or "on").strip().lower() in ("off", "0", "false", "no"):
        return result
    original = (prompt or "").strip()
    if not original or not (chat_key or env.get("GROQ_API_KEY")):
        return result
    deadline = time.time() + TOTAL_BUDGET
    store = _get_store()
    memo = {}

    chars, traits_by_name = [], []
    try:
        chars = detect_characters(original, chat_key, env, deadline)
    except Exception as e:
        _log("detect step failed: %s" % e)
    for c in chars:
        try:
            t = traits_for(c, chat_key, env, store, deadline, memo)
        except Exception as e:
            _log("look-up failed for %s: %s" % (c.get("name"), e))
            t = ""
        if t:
            traits_by_name.append((c["name"], t))
    try:
        better = write_prompt(original, aspect, traits_by_name, chat_key, env, deadline)
    except Exception as e:
        _log("rewrite step failed: %s" % e)
        better = ""
    if better:
        result.update(prompt=better, refined=True)
    result["characters"] = [c["name"] for c in chars]

    # reference pictures for FLUX.2 [dev] (at most 4 in total, split between the characters)
    base = result["prompt"]
    if chars and (env.get("USE_REFERENCE_IMAGES") or "on").strip().lower() not in ("off", "0", "false", "no"):
        per = max(1, min(3, MAX_FLUX2_REFS // len(chars)))
        refs, notes = [], []
        for c in chars:
            try:
                allrefs = _prepared_refs(c, env, store, memo)
                got = [r for r in allrefs if min(_img_size(r[1])) >= MIN_REF_PX][:per]
                if allrefs and not got:
                    _log("reference pictures for %s are too small for FLUX.2 (sizes %s, need at least %dpx) - "
                         "using the text-only model" % (c.get("name"), [_img_size(r[1]) for r in allrefs], MIN_REF_PX))
            except Exception as e:
                _log("reference pictures failed for %s: %s" % (c.get("name"), e))
                got = []
            if got:
                first, last = len(refs), len(refs) + len(got) - 1
                where = "image %d" % first if first == last else "images %d to %d" % (first, last)
                notes.append("%s show%s %s" % (where.capitalize(), "s" if first == last else "", c["name"]))
                refs += got
        if refs:
            result["refs"] = refs[:MAX_FLUX2_REFS]
            result["ref_prompt"] = (base + " Reference pictures: " + "; ".join(notes) +
                                    " - keep each character's face, hair, outfit and colours exactly as in those pictures.")[:1900]
    if not result["refs"]:
        result["ref_prompt"] = base
    _log("characters=%s traits_found=%d refined=%s refs=%d" % (result["characters"], len(traits_by_name),
                                                                result["refined"], len(result["refs"])))
    return result
