#!/usr/bin/env python3
"""Sync localized navigation in docs.json from the English source.

What it does
============

Reads ``docs.json`` at the repo root, finds the English language entry
(``language: en``), and mirrors its nav structure into every other
language entry declared there.

For each non-English locale ``L``:

1. The script walks the English ``tabs`` tree and the existing locale
   ``tabs`` tree in parallel. Any translated tab/group/sub-group label
   already in the locale tree is preserved at the same position; new
   English entries fall back to the English label (translator's TODO).

2. For every English page slug ``<path>``:

   - If ``<L>/<path>.mdx`` (or ``.md``) exists on disk, the locale's
     nav references ``<L>/<path>``.
   - Otherwise the page is omitted from the locale's nav AND a redirect
     ``"/<L>/<path>" -> "/<path>"`` is appended to the top-level
     ``redirects`` array, so direct URL visits to the missing localized
     page land on the English version instead of 404'ing.

3. Empty groups and tabs (after pruning missing pages) are dropped from
   the locale's nav.

The script is idempotent. On every run it strips any existing redirect
whose source starts with ``/<locale>/`` (or equals ``/<locale>``) for
any locale listed in ``LOCALE_CODES`` and rebuilds them deterministically;
unrelated manual redirects (including the existing ``/en`` -> ``/`` rule
for the legacy English path prefix) are preserved untouched.

Usage
-----

    python3 scripts/sync-locales.py            # rewrite docs.json in place
    python3 scripts/sync-locales.py --check    # exit non-zero if changes pending (CI)
    python3 scripts/sync-locales.py --diff     # print a unified diff and exit

Run this after adding, removing, or renaming any English ``.mdx`` page,
or after translating a previously-missing locale page.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"

# Non-English locales that the sync script is responsible for. If you add a
# new translation locale, add its code here AND make sure docs.json contains
# a corresponding entry under navigation.languages.
LOCALE_CODES = [
    "ar", "de", "es", "fr", "id", "ja", "ko",
    "pt", "ru", "tr", "vi", "zh", "zh-Hant",
]


def load_docs_json() -> dict[str, Any]:
    with DOCS_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def page_file_exists(slug: str) -> bool:
    """A page slug is a repo-relative path without extension."""
    for ext in (".mdx", ".md"):
        if (REPO_ROOT / f"{slug}{ext}").exists():
            return True
    return False


# ---------- Content-based signatures for label preservation ----------------
#
# Earlier versions of this script paired locale tabs/groups with English ones
# by *position* (locale_tabs[i] aligns with en_tabs[i]). That works only when
# the two arrays stay the same length. When a brand-new locale is first synced
# with few/no translated pages on disk, mdx-only groups (and tabs that contain
# only mdx-only groups) get pruned, while OpenAPI-only groups always survive.
# The locale's saved tabs become a *truncated* version of English's, and on
# the next sync the position-based pairing misaligns: locale label "Api
# Reference" ends up "preserved" onto English's "Home" or "Overview" tab.
#
# The fix below pairs by content signature. A signature is a stable, locale-
# agnostic identifier derived from the first page slug or first openapi source
# inside the entry. When a locale tab/group with a matching signature exists,
# we reuse its label (the translator's work). Otherwise we fall back to the
# English label.

def _strip_locale_prefix(s: str, locale: str | None = None) -> str:
    """Remove the leading "/<locale>/" or "<locale>/" from a path-like string.

    If ``locale`` is given, only that prefix is stripped; otherwise any of the
    known LOCALE_CODES is tried. Always returns a path that starts at the
    repo-root level (no leading slash).
    """
    s = s.lstrip("/")
    candidates = [locale] if locale else LOCALE_CODES
    for code in candidates:
        if not code:
            continue
        pfx = f"{code}/"
        if s.startswith(pfx):
            return s[len(pfx):]
    return s


def _group_signature(group: dict, locale: str | None = None) -> str | None:
    """Return a locale-agnostic signature for a group, or None if it's empty.

    The signature is built from the first concrete page slug (for `pages`-type
    groups) or the openapi `source` filename (for `openapi`-type groups), with
    any locale prefix stripped. This makes English and locale entries compare
    equal as long as they describe the same content.
    """
    if "openapi" in group:
        src = (group.get("openapi") or {}).get("source", "")
        if not src:
            return None
        return f"openapi:{_strip_locale_prefix(src, locale)}"
    pages = group.get("pages") or []
    for p in pages:
        if isinstance(p, str):
            return f"page:{_strip_locale_prefix(p, locale)}"
        if isinstance(p, dict):
            inner = _group_signature(p, locale)
            if inner:
                return f"nested:{inner}"
    return None


def _tab_signature(tab: dict, locale: str | None = None) -> tuple:
    """Tuple of every group signature inside the tab (preserves order)."""
    sigs = tuple(
        s for s in (
            _group_signature(g, locale) for g in tab.get("groups", [])
        ) if s is not None
    )
    return sigs


def _index_by_signature(items, sig_fn, locale):
    """Build {signature: item} mapping; later duplicates overwrite earlier ones."""
    out = {}
    for it in items or []:
        sig = sig_fn(it, locale)
        if sig:
            out[sig] = it
    return out


def localize_openapi(en_openapi: dict, locale: str) -> dict:
    """Re-prefix a Mintlify ``openapi`` block (``source`` and ``directory``) for the locale.

    Mintlify treats the ``openapi`` block on a group as the spec to render that
    group's API docs from. We need a per-locale copy so the URL tree under the
    locale gets its own pages, even though the spec content itself is the same.
    """
    out = dict(en_openapi)
    src = en_openapi.get("source", "")
    if src.startswith("/"):
        # Replace leading "/" with "/<locale>/" only if not already locale-prefixed.
        if not any(src.startswith(f"/{code}/") for code in LOCALE_CODES):
            out["source"] = f"/{locale}{src}"
    elif src and not any(src.startswith(f"{code}/") for code in LOCALE_CODES):
        out["source"] = f"{locale}/{src}"

    directory = en_openapi.get("directory", "")
    if directory and not any(directory.startswith(f"{code}/") for code in LOCALE_CODES):
        out["directory"] = f"{locale}/{directory}"

    return out


def localize_group_entry(en_entry: dict, existing: dict | None, locale: str, redirects: list) -> dict | None:
    """Localize one ``{group: ..., pages: [...]}`` or ``{group: ..., openapi: {...}}`` node.

    Returns the localized node, or None if the node would be empty after pruning.
    """
    new_label = (
        existing.get("group")
        if isinstance(existing, dict) and existing.get("group")
        else en_entry.get("group")
    )

    # Case 1: openapi-driven group (no `pages`)
    if "openapi" in en_entry:
        return {"group": new_label, "openapi": localize_openapi(en_entry["openapi"], locale)}

    # Case 2: regular group with a `pages` list
    inner_locale_pages = existing.get("pages", []) if isinstance(existing, dict) else []
    inner_pages = localize_pages(
        en_entry.get("pages", []),
        inner_locale_pages,
        locale,
        redirects,
    )
    if not inner_pages:
        return None
    return {"group": new_label, "pages": inner_pages}


def localize_pages(en_pages, locale_pages, locale, redirects):
    """Translate an English ``pages`` list into the locale's ``pages`` list.

    String entries (page slugs) are mirrored from English with the locale
    prefix added; entries whose locale file doesn't exist on disk are dropped
    and a fallback redirect is emitted instead.

    Dict entries (nested groups) are paired with the locale's existing nested
    group by *content signature* — see _group_signature — so a locale's
    translated label survives even after the locale's pages list has been
    truncated and re-padded by previous syncs.
    """
    # Index any nested groups in the locale list by signature for O(1) lookup.
    locale_nested_by_sig = _index_by_signature(
        [p for p in (locale_pages or []) if isinstance(p, dict)],
        _group_signature,
        locale,
    )

    out: list = []
    for en_entry in en_pages:
        if isinstance(en_entry, str):
            localized_slug = f"{locale}/{en_entry}"
            if page_file_exists(localized_slug):
                out.append(localized_slug)
            else:
                redirects.append(
                    {
                        "source": f"/{localized_slug}",
                        "destination": f"/{en_entry}",
                        "permanent": False,
                    }
                )
        else:
            existing = locale_nested_by_sig.get(_group_signature(en_entry, None))
            localized = localize_group_entry(en_entry, existing, locale, redirects)
            if localized is not None:
                out.append(localized)
    return out


def localize_groups(en_groups, locale_groups, locale, redirects):
    """Pair each English group with its locale counterpart by content signature."""
    locale_by_sig = _index_by_signature(locale_groups, _group_signature, locale)
    out: list = []
    for en_g in en_groups:
        existing = locale_by_sig.get(_group_signature(en_g, None))
        localized = localize_group_entry(en_g, existing, locale, redirects)
        if localized is not None:
            out.append(localized)
    return out


def localize_tabs(en_tabs, locale_tabs, locale, redirects):
    """Pair each English tab with its locale counterpart by content signature.

    A tab's signature is the tuple of its groups' signatures. This survives
    locale truncation: if last sync dropped a tab because its mdx group(s)
    had no translated files, the next sync still finds the right locale tab
    via signature lookup once those files exist.
    """
    locale_by_sig = _index_by_signature(locale_tabs, _tab_signature, locale)
    out: list = []
    for en_t in en_tabs:
        existing = locale_by_sig.get(_tab_signature(en_t, None))
        new_label = (
            existing.get("tab")
            if isinstance(existing, dict) and existing.get("tab")
            else en_t.get("tab")
        )
        new_groups = localize_groups(
            en_t.get("groups", []),
            existing.get("groups", []) if isinstance(existing, dict) else [],
            locale,
            redirects,
        )
        if new_groups:
            out.append({"tab": new_label, "groups": new_groups})
    return out


def strip_locale_redirects(existing: list[dict]) -> list[dict]:
    """Drop redirects whose source begins with /<known-locale>/ or equals /<known-locale>."""
    kept = []
    for r in existing:
        src = r.get("source", "")
        if any(src == f"/{code}" or src.startswith(f"/{code}/") for code in LOCALE_CODES):
            continue
        kept.append(r)
    return kept


def sync(doc: dict[str, Any]) -> None:
    """Rewrite each non-English locale's tabs in place and rebuild the redirects array."""
    languages = doc["navigation"]["languages"]
    try:
        en = next(l for l in languages if l.get("language") == "en")
    except StopIteration:
        raise SystemExit("error: docs.json has no language entry with language=en")
    en_tabs = en.get("tabs", [])

    generated_redirects: list = []
    seen_locales: set = set()
    for lang in languages:
        code = lang.get("language")
        if code == "en":
            continue
        if code not in LOCALE_CODES:
            print(
                f"warning: language {code!r} is in docs.json but not in LOCALE_CODES; "
                "skipping. Add it to scripts/sync-locales.py LOCALE_CODES if it's real.",
                file=sys.stderr,
            )
            continue
        seen_locales.add(code)
        lang["tabs"] = localize_tabs(en_tabs, lang.get("tabs", []), code, generated_redirects)

    missing_locales = [c for c in LOCALE_CODES if c not in seen_locales]
    if missing_locales:
        print(
            f"warning: LOCALE_CODES contains locales not in docs.json: {missing_locales}",
            file=sys.stderr,
        )

    # Sort redirects deterministically so re-runs produce stable diffs.
    generated_redirects.sort(key=lambda r: (r["source"], r["destination"]))

    kept = strip_locale_redirects(doc.get("redirects", []))
    doc["redirects"] = kept + generated_redirects


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sync localized navigation in docs.json from the English source.",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if changes are pending; do not write",
    )
    ap.add_argument(
        "--diff",
        action="store_true",
        help="print a unified diff of pending changes and exit",
    )
    args = ap.parse_args()

    doc = load_docs_json()
    before = json.dumps(doc, indent=2, ensure_ascii=False)
    sync(doc)
    after = json.dumps(doc, indent=2, ensure_ascii=False)

    if args.diff:
        if before == after:
            print("docs.json is in sync.")
            return 0
        import difflib

        for line in difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="docs.json (current)",
            tofile="docs.json (synced)",
            lineterm="",
        ):
            print(line)
        return 1

    if args.check:
        if before == after:
            print("docs.json is in sync.")
            return 0
        print(
            "docs.json is OUT OF SYNC. Re-run `python3 scripts/sync-locales.py` to fix.",
            file=sys.stderr,
        )
        return 1

    if before == after:
        print("docs.json already in sync; nothing to write.")
        return 0
    DOCS_JSON.write_text(after + "\n", encoding="utf-8")
    print(f"wrote {DOCS_JSON.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
