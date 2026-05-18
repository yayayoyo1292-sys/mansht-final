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


def _tokenize(text: str) -> list:
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


def _fix_orphans(lines: list) -> list:
    """
    Final pass: merge any single-token line with its neighbour.

    Rules (applied repeatedly until stable):
    • If line[0] has 1 token → merge with line[1]
    • If line[-1] has 1 token → merge with line[-2]

    We allow the merged line to exceed max_width — better to be slightly
    wide than to have a lone word on its own line.
    """
    changed = True
    while changed and len(lines) > 1:
        changed = False
        # Fix orphan first line
        if len(lines) > 1:
            first_words = [w for w in lines[0].replace(_NBSP, " ").split() if w]
            if len(first_words) == 1:
                lines = [lines[0] + " " + lines[1]] + lines[2:]
                changed = True
                continue
        # Fix orphan last line
        if len(lines) > 1:
            last_words = [w for w in lines[-1].replace(_NBSP, " ").split() if w]
            if len(last_words) == 1:
                lines = lines[:-2] + [lines[-2] + " " + lines[-1]]
                changed = True
    return lines


def _line_width(draw, tokens: list, font) -> int:
    """Pixel width of tokens joined by spaces."""
    text = " ".join(tokens)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _greedy_wrap(draw, tokens: list, font, max_width: int) -> list:
    """
    Classic greedy wrap — fill each line to max_width then break.
    Returns list of token-lists (one per line).
    """
    lines = []
    current = []
    for tok in tokens:
        candidate = current + [tok]
        if _line_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = [tok]
    if current:
        lines.append(current)
    return lines


def _balanced_wrap(draw, tokens: list, font, max_width: int, n_lines: int) -> list:
    """
    Distribute *tokens* across exactly *n_lines* as evenly as possible
    (minimise the difference in pixel width between lines).

    Algorithm: dynamic programming — find the split points that minimise
    the maximum line width while respecting max_width per line.

    This guarantees that if the text fits in n_lines, every line will be
    as close to the same width as possible — no single short word left
    alone on a line when the line could hold more tokens.
    """
    n = len(tokens)

    # Pre-compute widths of every possible span [i, j)
    width = {}
    for i in range(n):
        w = 0
        for j in range(i, n):
            tok_w = draw.textbbox((0, 0), tokens[j], font=font)[2] - \
                    draw.textbbox((0, 0), tokens[j], font=font)[0]
            space_w = draw.textbbox((0, 0), " ", font=font)[2] - \
                      draw.textbbox((0, 0), " ", font=font)[0] if j > i else 0
            w += tok_w + space_w
            width[(i, j)] = w

    INF = float("inf")

    # dp[i][k] = minimum "max-line-width" to place tokens[i:] in k lines
    # We also store the split point for reconstruction
    dp   = [[INF] * (n_lines + 1) for _ in range(n + 1)]
    split = [[0]  * (n_lines + 1) for _ in range(n + 1)]
    dp[n][0] = 0

    for i in range(n - 1, -1, -1):
        for k in range(1, n_lines + 1):
            for j in range(i, n):
                w = width[(i, j)]
                if w > max_width:
                    break   # this span is already too wide — stop extending
                cost = max(w, dp[j + 1][k - 1])
                if cost < dp[i][k]:
                    dp[i][k]   = cost
                    split[i][k] = j + 1

    # Reconstruct lines
    lines = []
    i, k = 0, n_lines
    while k > 0 and i < n:
        j = split[i][k]
        lines.append(tokens[i:j])
        i, k = j, k - 1

    # If DP couldn't fill all n_lines (edge case), fall back to greedy
    if not lines:
        lines = _greedy_wrap(draw, tokens, font, max_width)

    return lines


def wrap_text(draw, text: str, font, max_width: int) -> list:
    """
    Wrap *text* into lines that fit within *max_width* pixels.

    Strategy
    ────────
    1. Tokenise (quoted phrases & NBSP-protected names = single tokens).
    2. Greedy-wrap to find the minimum number of lines needed (n_lines).
    3. Re-wrap using the balanced algorithm so that all n_lines carry
       roughly equal pixel weight — no orphan first/last lines.

    This means a 12-word headline that needs 3 lines gets ~4 words per
    line, not "1 word / 5 words / 6 words".
    """
    tokens = _tokenize(text)
    if not tokens:
        return []

    # Step 1 — find minimum line count via greedy
    greedy_lines = _greedy_wrap(draw, tokens, font, max_width)
    n_lines = len(greedy_lines)

    if n_lines <= 1:
        return [" ".join(tokens)]

    # Step 2 — balanced redistribution
    balanced = _balanced_wrap(draw, tokens, font, max_width, n_lines)

    # Convert token-lists → strings
    result = [" ".join(toks) for toks in balanced if toks]
    result = result if result else [" ".join(tokens)]

    # Final pass: fix any remaining single-word lines
    return _fix_orphans(result)


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
