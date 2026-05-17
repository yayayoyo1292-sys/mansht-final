import re
import arabic_reshaper
from bidi.algorithm import get_display

# All quotation mark variants we want to treat as quote delimiters
_OPEN_QUOTES  = set('"\u201c\u00ab')
_CLOSE_QUOTES = set('"\u201d\u00bb')
_ALL_QUOTES   = _OPEN_QUOTES | _CLOSE_QUOTES

# ── Protected names ───────────────────────────────────────────────────────────
# These multi-word Arabic names must NEVER be broken across lines.
# Sorted longest-first so overlapping phrases match correctly.
PROTECTED_NAMES: list = sorted([
    # UAE leadership
    "محمد بن زايد آل نهيان",
    "خالد بن محمد بن زايد",
    "حمدان بن محمد بن زايد",
    "أحمد بن محمد بن راشد",
    "منصور بن محمد بن راشد",
    "ذياب بن محمد بن زايد",
    "محمد بن راشد",
    "منصور بن زايد",
    "حمدان بن محمد",
    "سيف بن زايد",
    "عبدالله بن زايد",
    "طحنون بن زايد",
    "هزاع بن زايد",
    "حمدان بن زايد",
    "سلطان القاسمي",
    "عمر بن زايد",
    "حميد بن راشد",
    "سعود بن صقر",
    "راشد بن سعود",
    "حمد الشرقي",
    "سلطان بن زايد",
    "نهيان بن زايد",
    "محمد بن زايد",
    "رئيس الدولة",
    "ولي عهد",
    # Arab League / regional figures
    "أبو الغيط",
    "أبوالغيط",
    # Common two-word titles that must stay together
    "بن مكتوم",
    "بن راشد",
    "بن زايد",
    "بن محمد",
    "آل نهيان",
    "آل مكتوم",
], key=lambda s: -len(s))

# Non-breaking space — glues words of a protected name into one token
_NBSP = "\u00a0"


def _protect_names(text: str) -> str:
    """
    Replace ordinary spaces inside protected names with non-breaking spaces
    so the entire name stays on a single line during wrapping.

        "هزاع بن زايد يقول"  →  "هزاع\u00a0بن\u00a0زايد يقول"
        "أبو الغيط يدين"     →  "أبو\u00a0الغيط يدين"
    """
    for name in PROTECTED_NAMES:
        protected = name.replace(" ", _NBSP)
        text = text.replace(name, protected)
    return text


def prepare_ar_text(text: str) -> str:
    """Reshape + apply BiDi algorithm so Arabic renders correctly in PIL."""
    text = _protect_names(text)
    reshaped = arabic_reshaper.reshape(text)
    return str(get_display(reshaped))


def _tokenize(text: str) -> list[str]:
    """
    Split text into tokens where a quoted phrase counts as ONE token.

    "World Health Org" everyone must follow  →  ['"World Health Org"', 'everyone', 'must', 'follow']
    """
    tokens: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch in ' \t':
            i += 1
            continue

        if ch in _OPEN_QUOTES:
            # Scan ahead for the matching close quote
            j = i + 1
            while j < n and text[j] not in _CLOSE_QUOTES:
                j += 1
            if j < n:                           # found closing quote
                tokens.append(text[i: j + 1])
                i = j + 1
            else:                               # no closing quote — treat as plain word
                k = i + 1
                while k < n and text[k] != ' ':
                    k += 1
                tokens.append(text[i:k])
                i = k
        else:
            # Plain word — read until space or quote
            j = i
            while j < n and text[j] not in ' \t' and text[j] not in _ALL_QUOTES:
                j += 1
            tokens.append(text[i:j])
            i = j

    return [t for t in tokens if t]


def wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """
    Wrap *text* into lines that fit within *max_width* pixels.

    Rules:
    • Quoted phrases stay on one line (never broken).
    • Protected names (joined with NBSP) stay on one line.
    • Orphan prevention: if the first line has only ONE token, it is merged
      with the second line so a name like "أبو الغيط" never splits as
      "أبو" alone on line 1.
    """
    tokens = _tokenize(text)
    lines: list[str] = []
    current = ""

    for token in tokens:
        candidate = (current + " " + token).strip() if current else token
        bbox  = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = token          # start fresh line with this token

    if current:
        lines.append(current)

    # ── Orphan prevention ────────────────────────────────────────────────────
    # If the first line is a single short token (≤ 6 chars) AND there's a
    # second line, merge them. This keeps "أبو الغيط" together even when the
    # wrapping algorithm would otherwise leave "أبو" alone on line 1.
    if len(lines) >= 2:
        first_tokens = _tokenize(lines[0])
        if len(first_tokens) == 1 and len(lines[0].replace(_NBSP, "")) <= 8:
            merged = lines[0] + " " + lines[1]
            lines = [merged] + lines[2:]

    return lines


def fit_text(
    draw,
    text: str,
    font_path: str,
    max_width: int,
    max_height: int,
    max_font_size: int = 60,
    min_font_size: int = 26,
) -> tuple:
    """
    Find the largest font size where *text* fits inside the given box.

    Returns (font, lines, line_height) or (None, None, None) if nothing fits.

    Changes vs original:
    • line_height increased from size+15 → size+22  (more breathing room)
    • Uses quote-aware wrap_text
    """
    from PIL import ImageFont

    for size in range(max_font_size, min_font_size - 1, -2):
        font        = ImageFont.truetype(font_path, size)
        lines       = wrap_text(draw, text, font, max_width)
        line_height = size + 22          # ← increased spacing (was +15)

        total_height  = len(lines) * line_height
        longest_line  = max(
            (draw.textbbox((0, 0), ln, font=font)[2] - draw.textbbox((0, 0), ln, font=font)[0])
            for ln in lines
        ) if lines else 0

        if total_height <= max_height and longest_line <= max_width:
            return font, lines, line_height

    return None, None, None
