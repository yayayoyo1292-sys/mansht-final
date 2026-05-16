import re
import arabic_reshaper
from bidi.algorithm import get_display

# All quotation mark variants we want to treat as quote delimiters
_OPEN_QUOTES  = set('"\u201c\u00ab')
_CLOSE_QUOTES = set('"\u201d\u00bb')
_ALL_QUOTES   = _OPEN_QUOTES | _CLOSE_QUOTES


def prepare_ar_text(text: str) -> str:
    """Reshape + apply BiDi algorithm so Arabic renders correctly in PIL."""
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

    Quoted phrases are kept on the same line — they are never broken.
    If a single quoted phrase is wider than max_width it still stays on
    one line (the design box controls the font-size reduction via fit_text).
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
