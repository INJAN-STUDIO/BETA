"""
B.E.T.A. - read-aloud with Microsoft Edge's neural voices (Brian), the same engine ALPHA uses.

The text goes through ALPHA's TTS cleaner first, so Brian never reads out web addresses, code, table pipes or
markdown symbols. Audio is made on the server and sent to the phone as one MP3, so it doesn't depend on the
phone having any text-to-speech voices installed (the browser's built-in speech was the unreliable part).

edge-tts talks to Microsoft's public speech service (the same one Edge's "read aloud" uses). It's unofficial and
free; if Microsoft changes it, `pip install -U edge-tts` usually fixes it.
"""

import asyncio
import hashlib
import os
import re
import threading
from collections import OrderedDict

from text_cleaner import clean_text_for_tts

VOICE = os.environ.get("BETA_TTS_VOICE", "en-US-BrianNeural")
MAX_CHARS = 2500
CACHE_LIMIT = 24

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+")
_slots = threading.BoundedSemaphore(2)      # a free server shouldn't run many speech jobs at once
_cache = OrderedDict()
_cache_lock = threading.Lock()


class TTSError(Exception):
    pass


def prepare_text(text):
    """What actually gets spoken: cleaned of URLs/code/tables/markdown/emoji, capped at a sentence end."""
    t = clean_text_for_tts(text or "")
    t = _EMOJI.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > MAX_CHARS:
        cut = t[:MAX_CHARS]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = cut[: end + 1] if end > MAX_CHARS * 0.5 else cut
    return t


async def _stream(text, voice):
    import edge_tts                                   # imported late so the rest of the app runs without it
    communicate = edge_tts.Communicate(text, voice)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


def synthesize(text, voice=None, timeout=45):
    """MP3 bytes for `text`. Raises TTSError with a message that is safe to show."""
    spoken = prepare_text(text)
    if not spoken:
        raise TTSError("There's nothing to read aloud in that message.")
    voice = voice or VOICE
    key = hashlib.sha1((voice + "\n" + spoken).encode("utf-8")).hexdigest()
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if not _slots.acquire(timeout=20):
        raise TTSError("The voice is busy reading something else - try again in a moment.")
    try:
        loop = asyncio.new_event_loop()
        try:
            data = loop.run_until_complete(asyncio.wait_for(_stream(spoken, voice), timeout))
        finally:
            loop.close()
    except ImportError:
        raise TTSError("The voice engine (edge-tts) isn't installed on the server.")
    except asyncio.TimeoutError:
        raise TTSError("The voice took too long to answer. Try again.")
    except Exception as e:
        raise TTSError("The voice service couldn't be reached (%s)." % type(e).__name__)
    finally:
        _slots.release()
    if not data:
        raise TTSError("The voice service sent back no audio. Try again.")
    with _cache_lock:
        _cache[key] = data
        while len(_cache) > CACHE_LIMIT:
            _cache.popitem(last=False)
    return data
