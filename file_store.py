"""
B.E.T.A. - files it creates for you to download.

When B.E.T.A. writes a file (a script, notes, a .docx ...) it is kept here, in memory, and the chat shows a
download card. Like generated pictures, only the most recent ones are kept and everything is forgotten when
Render restarts, so download a file soon after it appears.

Safety: only the file NAME is used (never a folder path), only plain-text-like types and .docx are allowed, there is a
size limit, and the download route always sends the file as an attachment, never as a page.
"""

import io
import os
import re
import threading
import uuid
from collections import OrderedDict

MAX_BYTES = 1_500_000
STORE_LIMIT = 20

TEXT_TYPES = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".tsv", ".html", ".css", ".xml", ".yaml", ".yml", ".sh",
    ".log", ".ini", ".toml", ".conf", ".c", ".h", ".cpp", ".java", ".kt", ".go", ".rs", ".sql", ".rst", ".tex",
}
DOCX = ".docx"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_store = OrderedDict()
_lock = threading.Lock()


class FileError(Exception):
    """Carries a message that is safe to show to the model and to Karachi."""


def safe_name(path):
    """Just a plain file name: no folders, only simple characters, at most 80 long."""
    name = str(path or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    name = name[:80].strip(" .")
    if not name:
        name = "beta-file"
    if "." not in name:
        name += ".txt"
    return name


def _build_docx(text):
    try:
        from docx import Document
    except Exception:
        raise FileError("Word files can't be made on this server (python-docx isn't installed). Make it as .md or .txt instead.")
    doc = Document()
    for raw in str(text or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            doc.add_heading(m.group(2).strip(), level=len(m.group(1)))
        elif re.match(r"^\s*[-*]\s+", line):
            doc.add_paragraph(re.sub(r"^\s*[-*]\s+", "", line), style="List Bullet")
        elif re.match(r"^\s*\d+[.)]\s+", line):
            doc.add_paragraph(re.sub(r"^\s*\d+[.)]\s+", "", line), style="List Number")
        else:
            doc.add_paragraph(line)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def create(path, content, max_bytes=None):
    """Keep a new file. Returns {'id', 'name', 'size'}. Raises FileError."""
    name = safe_name(path)
    ext = os.path.splitext(name)[1].lower()
    if ext == DOCX:
        data, mime = _build_docx(content), DOCX_MIME
    elif ext in TEXT_TYPES:
        data, mime = str(content or "").encode("utf-8"), "application/octet-stream"
    else:
        raise FileError("That file type isn't supported here (text, code and .docx files only).")
    if not data:
        raise FileError("The file would be empty.")
    limit = min(max_bytes or MAX_BYTES, MAX_BYTES)
    if len(data) > limit:
        raise FileError("That file is too big (limit %d KB)." % (limit // 1000))
    fid = uuid.uuid4().hex[:16]
    with _lock:
        _store[fid] = {"name": name, "bytes": data, "mime": mime}
        while len(_store) > STORE_LIMIT:
            _store.popitem(last=False)
    return {"id": fid, "name": name, "size": len(data)}


def get(fid):
    if not re.fullmatch(r"[0-9a-f]{16}", str(fid or "")):
        return None
    with _lock:
        return _store.get(fid)
