# `scripts/`

Tooling for the Raydium docs repo. Currently:

- [`translate.py`](./translate.py) — batch translator that turns the English source tree into locale-specific MDX, page by page, via the Anthropic API.

## `translate.py` — batch translator

Walks the English source at the repo root and writes a translated MDX file under each target locale's directory (`zh/`, `zh-Hant/`, `ja/`, `ko/`, `ru/`, `es/`, `de/`, `fr/`).

It preserves frontmatter keys, code fences, JSX components, internal-link structure, Solana program IDs and account/instruction names. It rewrites internal `/<path>` links to `/<locale>/<path>` and inserts the AI-translation banner at the top of every translated page.

### Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

### Translate everything

```bash
python3 scripts/translate.py
```

This translates every English page into all 13 locales. With the default model (`claude-haiku-5-5`) and concurrency of 8, a full run takes well under an hour; long pages are sent in several chunks, so they take proportionally longer.

By default it **skips** any target file that is no longer a stub — i.e. anything someone has hand-translated or hand-edited. Re-running is safe; only stubs get touched.

### Translate just one locale

```bash
python3 scripts/translate.py --locales ja
```

### Translate just a few pages

```bash
python3 scripts/translate.py \
  --paths products/cpmm/overview.mdx,products/clmm/overview.mdx \
  --locales zh,zh-Hant
```

### Force overwrite (replace existing translations)

```bash
python3 scripts/translate.py --overwrite
```

Useful after upstream English edits that should propagate to all locales.

### Check existing translations (no API calls)

```bash
python3 scripts/translate.py --check            # broken pages only; exits 1 if any
python3 scripts/translate.py --check --verbose  # also list pages that are out of date with English
```

"Broken" means the page will not build or is visibly cut off: frontmatter that does not parse (e.g. `« »` used as quotes), unbalanced JSX tags, a repetition loop, or missing trailing sections. "Out of date" means the English was edited after the page was translated.

Long pages are translated section by section (split on `##` headings, ~12k characters per request). Any response that stops on `max_tokens` or loses a heading, code fence or JSX tag is retried, and after three failures the target file is left untouched — so a failed run never writes a half-translated page.

### Dry run

```bash
python3 scripts/translate.py --dry-run
```

Lists every (locale, page) job and what would happen to it. No API calls, no disk writes.

### Other knobs

- `--model claude-sonnet-5-5` — pick a different model (default: `claude-haiku-5-5`).
- `--concurrency 16` — more in-flight requests.

### Log

Every run appends to `scripts/translate.log` with timestamp, locales, page count, model, and per-job status. Useful for spotting which pages errored so you can re-run them.

### What gets translated vs. preserved

**Translated:** prose, headings (when not code identifiers), markdown link visible text, JSX `title=` and `description=` props when they're user-facing strings, table cell text, alt text, frontmatter `title` and `description`.

**Not translated:** code fences, inline code, frontmatter keys (other than title/description), JSX prop names, JSX prop values that look like URLs/identifiers/icons, Solana addresses, PDA names, instruction/account/struct names, math expressions.

**Internal-link rewriting:** `[X](/foo)` becomes `[X-translated](/<locale>/foo)`. Anchor-only and external links untouched. Already-localized links untouched.

### When to re-run

- You added a new English page → run with `--paths <new-page-path>`.
- You substantially edited an existing English page → run with `--overwrite --paths <edited-page>`.
- Anthropic releases a new model and you want fresher translations → run with `--overwrite --model <new-model>`.
- Hand-translation by a community contributor → no action; the script will skip it on subsequent runs.

### Cost ballpark

A typical Raydium docs page is ~400 lines / ~12 KB. Cost scales with pages × locales and with the model you pick; see the [Claude pricing page](https://platform.claude.com/docs/en/about-claude/pricing) for current rates. Translate only the pages you changed (`--paths`) rather than the whole corpus whenever you can.
