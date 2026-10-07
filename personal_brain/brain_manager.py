"""
Cloud replacement for ALPHA's personal_brain/brain_manager.py.

Same functions agent_core.py calls (load_db, save_db, add_fact, search_facts)
and the same fact shape ({content, tags, timestamp, importance_score}), but
the data lives in the shared key/value store instead of data.json.
"""

import difflib
import re
from datetime import datetime, timezone

import storage

KEY = "brain"


def load_db():
    data = storage.get_store().get(KEY, None)
    if not isinstance(data, dict):
        data = {"facts": []}
    facts = data.get("facts", [])
    # Same migration ALPHA does: bare strings become proper fact objects.
    data["facts"] = [
        f if isinstance(f, dict) else {"content": str(f), "tags": [], "timestamp": "", "importance_score": 1}
        for f in facts
    ]
    return data


def save_db(data):
    storage.get_store().set(KEY, data)


def add_fact(text, tags=None, importance_score=1):
    data = load_db()
    data["facts"].append({
        "content": text.strip(),
        "tags": tags or [],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "importance_score": importance_score,
    })
    save_db(data)


def _words(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def search_facts(query, limit=5):
    """Keyword overlap first, fuzzy similarity as a tiebreaker/fallback."""
    q_words = _words(query)
    scored = []
    for fact in load_db()["facts"]:
        content = fact.get("content", "")
        overlap = len(q_words & _words(content))
        fuzzy = difflib.SequenceMatcher(None, query.lower(), content.lower()).ratio()
        score = overlap * 2 + fuzzy
        if overlap > 0 or fuzzy > 0.45:
            scored.append((score, content))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]
