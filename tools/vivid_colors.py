#!/usr/bin/env python3
"""
vivid_colors.py - makes the colours in a theme stylesheet pop, WITHOUT changing the themes.

Every theme keeps its own hues and its own look. What changes is the quality of the colour:
  * coloured (non-grey) solid colours get richer: more chroma, and on dark themes a touch lighter so they glow
  * coloured translucent tints (glows, washes, borders, chip and bubble backgrounds) get richer AND a little more opaque,
    which is what makes a UI look faded
  * the muted text colour (--dim) gets more contrast against its background
  * greys, whites, blacks, dark backgrounds and scrims are left alone, so backgrounds and layout feel the same
Colours are adjusted in OKLCH (perceptually even), and always kept inside the sRGB gamut.

Usage:   python vivid_colors.py themes.css > themes.vivid.css          (or:  python vivid_colors.py in.css out.css)
Tuning:  the four numbers just below. 1.0 / 0.0 = no change. Run it on the ORIGINAL file each time, not on its own output.
"""
import math
import re
import sys

CHROMA_BOOST = 1.22      # solid colours: chroma x this
TINT_CHROMA_BOOST = 1.25 # translucent tints: chroma x this
TINT_ALPHA_BOOST = 1.28  # translucent tints: alpha x this (capped, see below)
DARK_LIFT = 0.025        # dark themes: lightness added to mid/light solid colours so they glow
DIM_CONTRAST = 0.06      # --dim text: lightness moved away from the background by this much
NEUTRAL_C = 0.045        # colours less coloured than this are greys/backgrounds: untouched
BG_CHROMA_BOOST = 1.08   # very dark solid colours (backgrounds): only a whisper more colour

# ---------------------------------------------------------------- colour maths
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def _gam(c):
    c = max(0.0, c)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

def rgb_to_oklch(r, g, b):
    r, g, b = _lin(r / 255), _lin(g / 255), _lin(b / 255)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B), math.atan2(B, A)

def oklch_to_rgb(L, C, h, clip=False):
    A, B = C * math.cos(h), C * math.sin(h)
    l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3
    m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3
    s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    rgb = [r, g, b]
    inside = all(-0.0005 <= v <= 1.0005 for v in rgb)
    return [round(255 * _gam(min(1.0, max(0.0, v)))) for v in rgb], inside

def fit(L, C, h):
    """Largest chroma <= C that stays inside sRGB at this lightness and hue."""
    L = min(0.995, max(0.0, L))
    rgb, inside = oklch_to_rgb(L, C, h)
    while not inside and C > 0.0005:
        C -= 0.004
        rgb, inside = oklch_to_rgb(L, max(C, 0), h)
    return rgb

# ---------------------------------------------------------------- parsing colours
HEX = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
FUNC = re.compile(r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*([0-9.]+)\s*)?\)")

def _fmt(rgb, a):
    if a >= 0.999:
        return "#%02x%02x%02x" % tuple(rgb)
    return "rgba(%d,%d,%d,%s)" % (rgb[0], rgb[1], rgb[2], ("%.2f" % a).rstrip("0").rstrip("."))

def boost(r, g, b, a, dark):
    L, C, h = rgb_to_oklch(r, g, b)
    if C < NEUTRAL_C:
        return None
    if a >= 0.999:
        if L < 0.3:
            C2, L2 = C * BG_CHROMA_BOOST, L
        else:
            C2 = C * CHROMA_BOOST
            L2 = L + DARK_LIFT if (dark and 0.35 < L < 0.85) else L
    else:
        C2, L2 = C * TINT_CHROMA_BOOST, L
        if L >= 0.45:                      # a glow / wash / chip: crisper. Dark tints (shadows, navy borders) keep their weight.
            a = min(a * TINT_ALPHA_BOOST, a + 0.14, 0.92)
    return _fmt(fit(L2, C2, h), a)

def recolor(value, dark):
    def hexrep(m):
        raw = m.group(1)
        if len(raw) == 3:
            raw = "".join(ch * 2 for ch in raw)
        r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        a = int(raw[6:8], 16) / 255 if len(raw) == 8 else 1.0
        return boost(r, g, b, a, dark) or m.group(0)

    def funcrep(m):
        r, g, b = (min(255, float(m.group(i))) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return boost(r, g, b, a, dark) or m.group(0)

    # never touch url(...) contents (inline SVG images etc.)
    parts = re.split(r"(url\([^)]*\))", value)
    out = []
    for p in parts:
        out.append(p if p.startswith("url(") else FUNC.sub(funcrep, HEX.sub(hexrep, p)))
    return "".join(out)

# ---------------------------------------------------------------- walking the stylesheet
def luminance_is_dark(hexcolor):
    raw = hexcolor.lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return rgb_to_oklch(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))[0] < 0.55

def theme_darkness(css):
    """{'icon-dark': True, 'light': False, ...} from each theme's --bg."""
    out = {}
    for m in re.finditer(r'data-theme="([^"]+)"\]\s*\{([^{}]*)\}', css):
        bg = re.search(r"--bg:\s*(#[0-9a-fA-F]{3,6})", m.group(2))
        if bg and m.group(1) not in out:
            out[m.group(1)] = luminance_is_dark(bg.group(1))
    return out

def _rel_lum(rgb):
    return 0.2126 * _lin(rgb[0] / 255) + 0.7152 * _lin(rgb[1] / 255) + 0.0722 * _lin(rgb[2] / 255)

def contrast(a, b):
    la, lb = sorted((_rel_lum(a), _rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

def _hex_rgb(h):
    raw = h.lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return [int(raw[i:i + 2], 16) for i in (0, 2, 4)]

def keep_contrast(old, new, panel, dark):
    """The key colours must not become harder to read against the panel than they were (or than 4.5:1)."""
    if not (HEX.fullmatch(old.strip()) and HEX.fullmatch(new.strip()) and panel):
        return new
    o, n, p = _hex_rgb(old), _hex_rgb(new.strip()), _hex_rgb(panel)
    target = min(contrast(o, p), 4.5)
    L, C, h = rgb_to_oklch(*n)
    for _ in range(40):
        if contrast(n, p) >= target:
            break
        L += 0.01 if dark else -0.01
        n = fit(L, C, h)
    return " " + _fmt(n, 1.0)

KEY_COLOURS = ("--accent", "--accent-2", "--danger", "--warn")

def recolor_declarations(body, dark, panel=None):
    def one(m):
        prop, space, value = m.group(1), m.group(2), m.group(3)
        if prop.strip() in ("color-scheme",):
            return m.group(0)
        new = recolor(value, dark)
        if prop.strip() == "--dim":
            new = adjust_dim(value, dark)
        elif prop.strip() in KEY_COLOURS:
            new = keep_contrast(value, new, panel, dark)
        return "%s:%s%s" % (prop, space, new.lstrip() if space else new)
    return re.sub(r"([\w-]+)\s*:(\s*)([^;{}]+)", one, body)

def adjust_dim(value, dark):
    m = HEX.search(value)
    if not m:
        return recolor(value, dark)
    raw = m.group(1)
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    L, C, h = rgb_to_oklch(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    L2 = L + DIM_CONTRAST if dark else L - DIM_CONTRAST
    return _fmt(fit(L2, max(C * 1.3, 0.02) if C > 0.01 else C, h), 1.0)

def theme_panels(css):
    out = {}
    for m in re.finditer(r'data-theme="([^"]+)"\]\s*\{([^{}]*)\}', css):
        p = re.search(r"--panel:\s*(#[0-9a-fA-F]{3,6})", m.group(2))
        if p and m.group(1) not in out:
            out[m.group(1)] = p.group(1)
    return out

def vivid(css):
    darkness = theme_darkness(css)
    panels = theme_panels(css)
    out, i, stack = [], 0, []
    for m in re.finditer(r"[{}]", css):
        chunk = css[i:m.start()]
        if m.group(0) == "{":
            out.append(chunk + "{")
            stack.append(chunk)
        else:
            sel = next((s for s in reversed(stack) if "@media" not in s), "")
            tm = re.search(r'data-theme="([^"]+)"', sel)
            dark = darkness.get(tm.group(1), True) if tm else True
            out.append(recolor_declarations(chunk, dark, panels.get(tm.group(1)) if tm else None) + "}")
            if stack:
                stack.pop()
        i = m.end()
    out.append(css[i:])
    return "".join(out)

if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8").read()
    result = vivid(src)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w", encoding="utf-8").write(result)
    else:
        sys.stdout.write(result)
