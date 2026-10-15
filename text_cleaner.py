import re

# A markdown table's separator row, e.g. |---|:-:|---:|
_TABLE_SEPARATOR = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$')

TABLE_SPOKEN_PLACEHOLDER = "I've put a table on screen."


def replace_tables_for_tts(text, placeholder=TABLE_SPOKEN_PLACEHOLDER):
    """
    Swaps each markdown table for a short spoken phrase. Otherwise Edge-TTS
    reads the pipes and dashes aloud, and reading every cell of a table out
    loud is useless anyway - the table is right there on screen.
    """
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        is_table_start = (
            "|" in lines[i]
            and i + 1 < len(lines)
            and "|" in lines[i + 1]
            and _TABLE_SEPARATOR.match(lines[i + 1])
        )
        if is_table_start:
            j = i + 2
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                j += 1
            out.append(placeholder)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def clean_text_for_tts(text):
    """
    Cleans text:
    - Replaces markdown tables with a short spoken phrase.
    - Removes code blocks.
    - Converts '*' to a comma for a natural pause (instead of reading it).
    - Removes other annoying symbols.
    - Handles specific replacements.
    """
    # 0. Tables first - before any symbol stripping destroys the pipe/dash
    # structure we use to recognise them.
    text = replace_tables_for_tts(text)

    # 1. Remove code blocks
    text = re.sub(r'`[^`]*`', '', text)

    # 1b. Markdown links [text](url) -> just "text" - otherwise TTS reads the
    # raw URL aloud character by character, which is about as bad as TTS gets.
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)

    # 1c. Any bare URL left over (not in link syntax) - drop it rather than
    # read it aloud; a citation or pasted link shouldn't get spoken verbatim.
    text = re.sub(r'https?://\S+', '', text)

    # 1d. Emphasis markers (**bold**, *italic*, ***both***) -> just the words.
    # Without this the '*' rule below turns every marker into a comma pause.
    text = re.sub(r'(\*{1,3})(?=\S)(.+?)(?<=\S)\1', r'\2', text)

    # 2. Convert '*' to a comma (pause) - what's left is bullet markers
    text = text.replace('*', ', ')

    # 3. Remove or replace other symbols
    # Hashtags, at, colons, semicolons can just go away or be replaced by a pause
    text = re.sub(r'[#@:;]', '', text)

    # 4. Handle specific replacements
    replacements = {
        r'--': ', ',
        r'\.\.\.': ', ',
        r'/': ' ',
        r'\\': ' ',
        r'=': ' equals ',
        r'\+': ' plus ',
        r'&': ' and '
    }

    for symbol, replacement in replacements.items():
        text = re.sub(symbol, replacement, text)

    # 5. Final cleanup of extra whitespace
    return re.sub(r'\s+', ' ', text).strip()
