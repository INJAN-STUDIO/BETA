"""What B.E.T.A. says out loud is not the same as what it writes.

A written reply has code blocks, tables, links, headings, bullet marks, emojis and footnotes. A person talking would not
read any of that out. `speakable(text)` turns a written reply into what a person would actually SAY:

  * code blocks and tables are not read - one short sentence says they are on screen instead
  * links are not spelled out (a link's visible words are kept; a bare address becomes "the link")
  * markdown marks, emojis, footnote numbers, "Sources:" lists and HTML tags are dropped
  * headings and bullet points become short sentences, so the voice pauses where a person would
  * long file paths / commands in `backticks` are skipped; short names such as app.py are kept

The same rules are in static/app.js (speakable) so the phone's own voice, used as a last resort, behaves the same.
Keep the two in step: tests compare them on the same samples.
"""
import re

CODE_SAID = "I've put the code on screen."
TABLE_SAID = "I've put a table on screen."

_CODE_MARK = "\u0001CODE\u0001"
_TABLE_MARK = "\u0001TABLE\u0001"

_EMOJI = re.compile("[←-⇿⌀-⏿─-➿⬀-⯿️‍\U0001f000-\U0001fbff]")
_END_PUNCT = re.compile(r"[.!?:;,…]['\"”’)\]]*$")


def _tidy_inline_code(m):
    code = m.group(1).strip()
    symbols = len(re.findall(r"[/\\{}\[\]()<>=;|$]", code))
    if len(code) > 28 or symbols >= 3:
        return " "                      # a long path or command: nobody reads that aloud
    return " " + code + " "


def speakable(text):
    t = str(text or "").replace("\r\n", "\n").replace("\r", "\n")

    # code blocks (also one that was never closed) and tables are replaced by a marker, said once at the end
    t = re.sub(r"(```|~~~)[\s\S]*?(\1|$)", "\n" + _CODE_MARK + "\n", t)
    t = re.sub(r"(?:^[ \t]*\|.*\|[ \t]*\n?)+", "\n" + _TABLE_MARK + "\n", t, flags=re.M)

    # a trailing "Sources:" / "References:" list is for the eyes
    t = re.sub(r"^[ \t]*(?:\*\*|__)?(?:sources?|references?|further reading)(?:\*\*|__)?[ \t]*:?[ \t]*(?:\*\*|__)?[ \t]*$[\s\S]*", "", t,
               flags=re.M | re.I)

    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)                       # images
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)                     # [words](link) -> words
    t = re.sub(r"<[^>\n]{1,200}>", " ", t)                             # html tags
    t = re.sub(r"\bhttps?://\S+", " the link ", t)                     # a bare address is never read out
    t = re.sub(r"\bwww\.\S+", " the link ", t)
    t = re.sub(r"\[\^?\d{1,3}\]", "", t)                               # footnote marks like [1]
    t = re.sub(r"`([^`\n]+)`", _tidy_inline_code, t)                   # inline code
    t = t.replace("`", "")

    t = re.sub(r"^[ \t]*([-*_][ \t]*){3,}$", "", t, flags=re.M)        # horizontal rules
    t = re.sub(r"^[ \t]*#{1,6}[ \t]+(.+?)[ \t#]*$", r"\1.", t, flags=re.M)   # headings become short sentences
    t = re.sub(r"^[ \t]*>+[ \t]?", "", t, flags=re.M)                  # quotes
    t = re.sub(r"^[ \t]*(?:[-*•+]|\d{1,3}[.)])[ \t]+", "", t, flags=re.M)   # bullet / number marks

    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)                          # bold
    t = re.sub(r"~~(.+?)~~", r"\1", t)
    t = re.sub(r"\*([^*\n]+)\*", r"\1", t)                             # italic
    t = re.sub(r"(^|[\s(])_+([^_\n]+?)_+(?=$|[\s).,!?:;])", r"\1\2", t, flags=re.M)

    # symbols that a voice would read badly
    t = t.replace("→", " to ").replace("->", " to ").replace("=>", " to ")
    t = _EMOJI.sub(" ", t)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r"(\d)\s*%", r"\1 percent", t)
    t = re.sub(r"(\d)\s*[x×]\s*(\d)", r"\1 by \2", t)
    t = t.replace("&", " and ")
    t = re.sub(r"~\s*(?=\d)", "about ", t)

    # line by line: every line is a sentence of its own, so the voice pauses at the end of it
    out, said_code, said_table = [], False, False
    for line in t.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _CODE_MARK in line or _TABLE_MARK in line:
            if _CODE_MARK in line:
                said_code = True
            if _TABLE_MARK in line:
                said_table = True
            line = line.replace(_CODE_MARK, " ").replace(_TABLE_MARK, " ").strip()
            if not line:
                continue
        line = re.sub(r"[\[\]|^#*_~]+", " ", line)
        line = re.sub(r"\(\s*\)", " ", line)
        line = re.sub(r"\s+", " ", line).strip(" -,")
        if not line:
            continue
        if not _END_PUNCT.search(line):
            line += "."
        out.append(line)
    if said_code:
        out.append(CODE_SAID)
    if said_table:
        out.append(TABLE_SAID)
    s = " ".join(out)
    s = re.sub(r"\s+([.,!?;:])", r"\1", s)
    s = re.sub(r"([.!?])(\s*\.)+", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
