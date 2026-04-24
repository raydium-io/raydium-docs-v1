#!/usr/bin/env python3
"""
One-time post-translation cleanup for MDX parser-breaking patterns.

The AI translator occasionally drops MDX-specific escape sequences that the
English source carefully preserved. This script restores them.

What it fixes (in every <locale>/**/*.mdx file):

1. Currency dollar signs.
   - English source writes `\$100,000–\$500,000` (escaped).
   - Translations sometimes drop the leading `\`, leaving `$100,000–\$500,000`
     or `$100,000–$500,000`. That makes Mintlify treat the contents as KaTeX
     math mode and warn about every CJK / em-dash / comma character inside.
   - Fix: re-insert `\` before any `$` that is followed by a digit and is not
     already preceded by `\`. Skipped inside fenced code blocks and inline
     `code spans` so legitimate code samples ($var-style or shell prompts)
     are left alone.

2. `<` followed by `=` or a digit in prose.
   - English source puts these inside `code spans` (e.g. `` `<= 10,000` ``).
   - Translations sometimes lose the backticks, leaving `< 10,000` or `<= 30s`
     bare. MDX's parser then thinks a JSX tag is starting and errors with
     "Unexpected character `=` (U+003D) before name" or similar.
   - Fix: replace the bare `<` with the HTML entity `&lt;`. Same code-context
     skipping as above.

3. JSX `placeholder='...'` with an apostrophe inside the localized string.
   - The English source uses single-quoted string. French ("l'IA"), Turkish
     ("zeka'ya"), Italian etc. introduce literal apostrophes that close the
     attribute prematurely.
   - Fix: switch the outer quote style. Prefer double-quotes; if the content
     also has double-quotes, fall back to a JSX expression with template
     literal (`={`...`}`).

Idempotent: running the script twice is a no-op on the second run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES = [
    "zh", "zh-Hant", "ja", "ko", "ru", "es", "de", "fr",
    "pt", "tr", "vi", "id", "ar",
]


# ---------- Helpers --------------------------------------------------------

def _split_by_codeblocks(text: str):
    """Yield (chunk, in_code) pairs alternating between prose and fenced code."""
    chunks = []
    in_fence = False
    buf = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            chunks.append(("".join(buf), in_fence))
            buf = [line]
            in_fence = not in_fence
            continue
        buf.append(line)
    chunks.append(("".join(buf), in_fence))
    return chunks


def _apply_to_prose_only(text: str, transform):
    """Run `transform(prose_str)` only on chunks that are NOT inside ``` ... ```."""
    out = []
    parts = _split_by_codeblocks(text)
    # Each part toggles based on whether the FENCE LINE was just seen, but we
    # need to know whether we're currently INSIDE a fence. Re-walk:
    in_fence = False
    out = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
        else:
            out.append(transform(line))
    return "".join(out)


def _transform_outside_inline_code(line: str, sub_fn):
    """Apply `sub_fn` to the parts of `line` that are NOT inside backtick spans."""
    # Split on backtick-delimited spans, transforming only the non-code segments.
    parts = re.split(r"(`[^`\n]*`)", line)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # backtick-wrapped span
            out.append(part)
        else:
            out.append(sub_fn(part))
    return "".join(out)


# ---------- Fix 1: dollar-sign escapes -------------------------------------
#
# We escape every `$` that is NOT part of a real KaTeX math expression and is
# NOT already escaped. "Real math" = a same-line `$...$` pair whose content
# uses LaTeX syntax (\command, _{ or ^{ subscript/superscript braces).
#
# Block math `$$ ... $$` (which can span multiple lines) is preserved
# unchanged: any line containing `$$` is left alone, and we track an
# in_block_math state across lines.
#
# Outside those exceptions, `$` is escaped to `\$`. This catches every form
# of stray dollar sign the AI translation may produce:
#   - Leading currency:    $5,000        → \$5,000
#   - Token symbols:       $RAY          → \$RAY
#   - Trailing currency:   "5,50 $"      → "5,50 \$"  (common in fr/de/es/etc)
#   - Currency pairs:      "$1,00 ... $" → "\$1,00 ... \$"

# A `$...$` pair is treated as REAL KaTeX math iff its body contains any of:
#   - a backslash command:   \frac, \sqrt, \text, \%, \&, \#, \\, …
#   - subscript or superscript:   _{…}, ^{…}, _x, ^6
#   - LaTeX grouping braces:  {…}  (commonly used for {,} tight commas, {a+b})
# The brace match is what we missed before — KaTeX uses braces heavily for
# grouping but currency strings never do, so this is safe.
LATEX_HINT_RE = re.compile(r"\\[a-zA-Z%&#]|_\{|\^\{|_[a-zA-Z]|\^[a-zA-Z0-9]|\\\\|\{[^}]*\}")


def _find_math_pair_regions(seg: str) -> list[tuple[int, int]]:
    """Return [(start, end)] byte spans of real `$...$` math on this line."""
    regions: list[tuple[int, int]] = []
    i = 0
    while i < len(seg):
        if seg[i] != "$":
            i += 1
            continue
        # Skip $$ block math markers entirely (they may appear unbalanced
        # within a single line; the line-level wrapper handles state).
        if i + 1 < len(seg) and seg[i + 1] == "$":
            i += 2
            continue
        # Already escaped \$ — not a delimiter
        if i > 0 and seg[i - 1] == "\\":
            i += 1
            continue
        # Look for closing unescaped, non-$$  $ on the same line
        j = i + 1
        close = -1
        while j < len(seg):
            if seg[j] != "$":
                j += 1
                continue
            if j + 1 < len(seg) and seg[j + 1] == "$":
                j += 2
                continue
            if seg[j - 1] == "\\":
                j += 1
                continue
            close = j
            break
        if close == -1:
            i += 1
            continue
        content = seg[i + 1:close]
        if LATEX_HINT_RE.search(content):
            regions.append((i, close + 1))
        i = close + 1
    return regions


def _escape_dollars_in_segment(seg: str) -> tuple[str, int]:
    """Escape every unescaped, non-math, non-$$  `$` in a single line segment."""
    math = _find_math_pair_regions(seg)
    out: list[str] = []
    count = 0
    region_iter = iter(math)
    cur = next(region_iter, None)
    i = 0
    while i < len(seg):
        # Advance past any region we've exited
        while cur and i >= cur[1]:
            cur = next(region_iter, None)
        if cur and cur[0] <= i < cur[1]:
            out.append(seg[i])
            i += 1
            continue
        c = seg[i]
        if c != "$":
            out.append(c)
            i += 1
            continue
        # Already escaped?
        if i > 0 and seg[i - 1] == "\\":
            out.append(c)
            i += 1
            continue
        # $$ marker — leave intact
        if i + 1 < len(seg) and seg[i + 1] == "$":
            out.append("$$")
            i += 2
            continue
        if i > 0 and seg[i - 1] == "$":
            out.append(c)
            i += 1
            continue
        out.append("\\$")
        count += 1
        i += 1
    return "".join(out), count


def fix_dollar_escapes(text: str) -> tuple[str, int]:
    count = 0
    in_fence = False
    in_block_math = False
    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        # Track `$$` block math so we don't touch its body lines.
        # Count UNESCAPED `$$` markers on this line.
        markers = len(re.findall(r"(?<!\\)\$\$", line))
        if in_block_math:
            out_lines.append(line)
            if markers % 2 == 1:
                in_block_math = False
            continue
        if markers > 0:
            out_lines.append(line)
            if markers % 2 == 1:
                in_block_math = True
            continue
        # Process the line, but only outside inline backtick spans.
        def _seg_fix(seg: str) -> str:
            nonlocal count
            new, n = _escape_dollars_in_segment(seg)
            count += n
            return new

        out_lines.append(_transform_outside_inline_code(line, _seg_fix))
    return "".join(out_lines), count


# ---------- Recovery: un-escape `\$...\$` pairs that are actually math -----
#
# An earlier (over-aggressive) version of this script escaped some legitimate
# `$...$` KaTeX inline math because the heuristic was too narrow. The result
# `\$100{,}000 / 10^6 = 10\%\$` re-introduces a different MDX bug: the parser
# now sees the inner `{,}` and `{ ... }` as JSX expressions and acorn errors
# with "Could not parse expression with acorn".
#
# This pass reverses that mistake. For every `\$...\$` pair on the same line
# whose body matches LATEX_HINT_RE, we strip both backslashes back to `$...$`.

ESCAPED_PAIR_RE = re.compile(r"\\\$([^\n$]+?)\\\$")


def fix_unescape_math(text: str) -> tuple[str, int]:
    count = 0

    def line_fix(line: str) -> str:
        return _transform_outside_inline_code(line, _math_un_sub)

    def _math_un_sub(seg: str) -> str:
        nonlocal count

        def repl(m: re.Match) -> str:
            nonlocal count
            body = m.group(1)
            if LATEX_HINT_RE.search(body):
                count += 1
                return f"${body}$"
            return m.group(0)

        return ESCAPED_PAIR_RE.sub(repl, seg)

    return _apply_to_prose_only(text, line_fix), count


# ---------- Fix 2: bare `<` before `=` / digit in prose --------------------

# Match `<` that is NOT immediately part of a JSX tag (followed by letter,
# slash, !, ?), BUT is followed by `=`, a digit, or a space-then-`=`/digit.
# Anchored at left to avoid matching the inside of HTML entities (&lt;) or
# already-escaped sequences.
BARE_LT_RE = re.compile(r"(?<![&\\<])<(?=\s*[=0-9])")


def fix_bare_lt(text: str) -> tuple[str, int]:
    count = 0

    def line_fix(line: str) -> str:
        return _transform_outside_inline_code(line, _lt_sub)

    def _lt_sub(seg: str) -> str:
        nonlocal count
        new_seg, n = BARE_LT_RE.subn("&lt;", seg)
        count += n
        return new_seg

    return _apply_to_prose_only(text, line_fix), count


# ---------- Fix 3: placeholder='...' with stray apostrophe -----------------

# Catches a JSX-attribute single-quoted string that contains another
# unescaped single quote in its middle. We deliberately scope to known
# attributes so we don't munge unrelated single-quoted prose.
#
# The closing `'` is identified by what follows it: an attribute string ends
# only when we see `'` followed by whitespace, `/>`, `>`, or end-of-line.
# Anything else (`'leri`, `'ya`, etc) is just an apostrophe in the body. This
# lookahead is essential — a naive `[^']*'[^']*'` regex would stop at the
# first internal apostrophe and corrupt the file.
ATTR_NAMES = ("placeholder", "title", "alt", "label", "aria-label", "value")
SINGLE_QUOTE_ATTR_RE = re.compile(
    r"(?P<name>" + "|".join(ATTR_NAMES) + r")"
    r"='(?P<body>[^\n]*?'[^\n]*?)'(?=\s|/>|>|$)",
    re.MULTILINE,
)


def _rewrite_attr(match: re.Match) -> str:
    name = match.group("name")
    body = match.group("body")
    if '"' not in body:
        # Simplest: switch to double quotes.
        return f'{name}="{body}"'
    # Body has both ' and ". Use JSX expression with a template literal.
    safe = body.replace("`", "\\`").replace("$", "\\$")
    return f"{name}={{`{safe}`}}"


def fix_jsx_attr_quotes(text: str) -> tuple[str, int]:
    new_text, count = SINGLE_QUOTE_ATTR_RE.subn(_rewrite_attr, text)
    return new_text, count


# ---------- Driver ---------------------------------------------------------

def process_file(path: Path) -> dict:
    original = path.read_text(encoding="utf-8")

    # Run un-escape FIRST so freshly-recovered `$...$` math pairs can be
    # detected by fix_dollar_escapes' LATEX_HINT logic on the same pass.
    text, math_n = fix_unescape_math(original)
    text, dollar_n = fix_dollar_escapes(text)
    text, lt_n = fix_bare_lt(text)
    text, attr_n = fix_jsx_attr_quotes(text)

    if text != original:
        path.write_text(text, encoding="utf-8")
        return {"changed": True, "dollar": dollar_n, "lt": lt_n, "attr": attr_n, "math": math_n}
    return {"changed": False, "dollar": 0, "lt": 0, "attr": 0, "math": 0}


def main() -> int:
    keys = ("dollar", "lt", "attr", "math")
    total = {"files": 0, "changed_files": 0, **{k: 0 for k in keys}}
    per_locale: dict[str, dict] = {}
    for loc in LOCALES:
        base = REPO_ROOT / loc
        if not base.exists():
            continue
        loc_stats = {"files": 0, "changed_files": 0, **{k: 0 for k in keys}}
        for mdx in sorted(base.rglob("*.mdx")):
            loc_stats["files"] += 1
            total["files"] += 1
            res = process_file(mdx)
            if res["changed"]:
                loc_stats["changed_files"] += 1
                total["changed_files"] += 1
            for k in keys:
                loc_stats[k] += res[k]
                total[k] += res[k]
            if res["changed"]:
                deltas = []
                if res["math"]:   deltas.append(f'math={res["math"]}')
                if res["dollar"]: deltas.append(f'$={res["dollar"]}')
                if res["lt"]:     deltas.append(f'<={res["lt"]}')
                if res["attr"]:   deltas.append(f'attr={res["attr"]}')
                print(f"  edit  {mdx.relative_to(REPO_ROOT)}  ({', '.join(deltas)})")
        per_locale[loc] = loc_stats

    print()
    print(f"{'LOCALE':<10} {'FILES':>6} {'EDITED':>8} {'MATH':>5} {'$ FIX':>6} {'< FIX':>6} {'ATTR':>6}")
    print("-" * 60)
    for loc, s in per_locale.items():
        print(
            f"{loc:<10} {s['files']:>6} {s['changed_files']:>8} {s['math']:>5} "
            f"{s['dollar']:>6} {s['lt']:>6} {s['attr']:>6}"
        )
    print("-" * 60)
    print(
        f"{'TOTAL':<10} {total['files']:>6} {total['changed_files']:>8} {total['math']:>5} "
        f"{total['dollar']:>6} {total['lt']:>6} {total['attr']:>6}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
