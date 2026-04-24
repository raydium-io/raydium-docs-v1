# Contributing to the Raydium documentation

Thank you for considering a contribution. This documentation is community-maintained, and pull requests are welcomed from developers, researchers, integrators, and end users alike. Even small fixes — a typo, a stale program ID, a clearer sentence — are appreciated.

This guide covers how to contribute, the conventions the docs follow, and what reviewers will look at when your PR lands.

## Ways to contribute

You don't need to be a Solana engineer to help. Useful contributions include:

- **Corrections.** Stale SDK calls, outdated program IDs, wrong fee numbers, broken links.
- **Clarifications.** A page that's correct but hard to follow — propose a rewrite.
- **Examples.** A copy-pasteable snippet for a flow that's only described in prose today.
- **New pages.** Filling in a gap that fits the architecture (talk to us first via an issue if it's a big one).
- **Diagrams.** Architecture diagrams, account-flow diagrams, math illustrations. Source files commit alongside the SVG.
- **Translations.** If you'd like to maintain a translation, open an issue first so we can scope navigation and tooling.

If you're unsure whether something fits, open an issue — early signal is cheap.

## Before you write — read these two files

Two files in the repo root define the rules of the road. Skimming them saves rework:

- [`ARCHITECTURE.mdx`](./ARCHITECTURE.mdx) — the audience model, the chapter map, the directory layout, and the per-product page template. New pages and structural changes must fit here.
- [`AGENTS.md`](./AGENTS.md) — terminology, style preferences, and content boundaries. Useful for human contributors, not just AI agents.

Pages that drift from the architecture (e.g., a deep CLMM math discussion lodged inside a user flow) will be moved during review.

## Issue and PR workflow

### Opening an issue

If you spot a problem you're not ready to fix, [open an issue](https://github.com/raydium-io/raydium-docs-v1/issues/new). Helpful issues include:

- The page URL or file path.
- A short description of what's wrong or missing.
- (For correctness issues) a source — SDK code, on-chain account snapshot, or a transaction signature on Solscan/SolanaFM.

### Submitting a PR

1. **Fork** the repo and create a feature branch off `main`. Branch names like `fix/clmm-fee-tier-table` or `add/launchlab-creator-fees` are easier to triage than `patch-1`.
2. **Make the change.** Run `mint dev` locally to preview.
3. **Self-check.** Run `mint broken-links`. The repo also expects 0 broken internal links — see "Pre-merge checklist" below.
4. **Open a PR.** Reference any related issue. Describe what changed and why. Include before/after screenshots for layout changes.

PRs are reviewed by maintainers; we aim to respond within a few days. We may push small edits onto your branch (rewording, frontmatter fixes) — let us know if you'd rather review those changes first.

## Writing style

The full style is in `AGENTS.md`. The headline rules:

- **Active voice, second person.** "Run the command" beats "the command should be run." Address the reader as "you."
- **One idea per sentence.** Two short sentences usually beat one long one with a clause inside it.
- **Sentence case for headings.** "Create a CPMM pool" — not "Create a CPMM Pool."
- **Bold for UI elements.** Click **Settings**.
- **Code formatting** for file names, commands, paths, program IDs, and code references.
- **No marketing voice.** No superlatives, no hype. The docs are reference material; trust the facts to do the work.
- **No emoji** (unless the user asks for them in their own contribution).

## Per-product page template

Every product folder follows the same shape so the four product lines stay comparable:

| File | Purpose |
|------|---------|
| `index.mdx` | Chapter landing: one-paragraph intro, when-to-use, links to sub-pages, key program ID. |
| `overview.mdx` | Conceptual model + diagram. |
| `accounts.mdx` | Every on-chain account: PDA seeds, field layout, invariants, IDL reference. |
| `math.mdx` | Pricing formulas and numerical examples. Cross-link to `algorithms/`. |
| `instructions.mdx` | Full instruction reference: args, account list, pre/post conditions, error codes. |
| `fees.mdx` | Fee tiers, fee splits (LP / protocol / fund / creator). For CLMM, also reward emissions. |
| `code-demos.mdx` | Copy-pasteable TypeScript + Rust examples for every flow. |

CLMM adds `ticks-and-positions.mdx`. LaunchLab adds `bonding-curve.mdx`. New product chapters should follow this template unless there's a strong reason not to.

## Code-sample requirements

Stale code samples are the #1 failure mode of DeFi documentation. To keep them honest:

- **Pin the version.** Every code-heavy page declares — near the top — the SDK version (`@raydium-io/raydium-sdk-v2@x.y.z`), the program ID, the Solana cluster (mainnet-beta unless explicitly otherwise), and the last-verified date.
- **Use the canonical SDK.** TypeScript examples use [`raydium-sdk-V2`](https://github.com/raydium-io/raydium-sdk-V2). Rust CPI examples use the published crate (`raydium-cp-swap` etc.). Don't introduce one-off forks unless absolutely necessary.
- **Keep examples self-contained.** A reader should be able to copy the block, fill in their wallet/RPC/mint, and run it. No "see the demo repo" without showing the relevant lines inline.
- **Use realistic addresses.** Reference real mainnet program IDs from `reference/program-addresses.mdx` rather than placeholders, except for inputs the reader provides (wallets, mints).

If your PR adds or modifies code samples, include the verification date in the page header.

## Cross-references

- **Internal links** use absolute paths starting with `/`, e.g. `/products/cpmm/instructions`. Don't link to the `.mdx` extension.
- **Program IDs** live in `reference/program-addresses.mdx`. Other pages link to it; they don't hardcode IDs.
- **Error codes** live in `reference/error-codes.mdx`. Instruction pages link to the specific anchor (e.g. `/reference/error-codes#clmm`).
- **Math definitions** live in `algorithms/`. Per-product `math.mdx` pages give the product-specific *instantiation* and link back.

## Diagrams

Architecture diagrams are SVGs checked into `/images/architecture/`. Commit the source (Mermaid `.mmd` or draw.io `.drawio`) next to the SVG so the next contributor can edit it. Inline Mermaid blocks in MDX are also acceptable for small diagrams.

## Pre-merge checklist

Before requesting review, please confirm:

- [ ] `mint dev` runs without errors locally.
- [ ] `mint broken-links` reports zero broken links.
- [ ] New pages are added to `docs.json` navigation.
- [ ] New pages have valid frontmatter (`title` and `description`).
- [ ] Code samples include the version banner described above.
- [ ] No `TODO`, `FIXME`, `XXX`, `coming soon`, or placeholder text remains.
- [ ] Internal links use absolute `/path` form, not relative paths.
- [ ] If you renamed or moved a page, set up a redirect in `docs.json` so external links keep working.
- [ ] If you **added, removed, or renamed any page** under the English root, you ran `python3 scripts/sync-locales.py` and committed the resulting `docs.json` so every locale stays in lock-step. CI runs `--check` and will fail otherwise.

## Keeping locales in sync — `scripts/sync-locales.py`

The English tree at the repo root is the source of truth. The thirteen locale trees (`zh`, `zh-Hant`, `ja`, `ko`, `ru`, `es`, `de`, `fr`, `pt`, `tr`, `vi`, `id`, `ar`) mirror its structure, but individual pages may not be translated yet. To keep `docs.json` honest, the repo ships a small idempotent script:

```bash
python3 scripts/sync-locales.py            # rewrite docs.json in place
python3 scripts/sync-locales.py --check    # CI mode: exit 1 if changes are pending
python3 scripts/sync-locales.py --diff     # preview a unified diff and exit
```

What the script does, end to end:

- Walks the English `tabs` tree and mirrors it into every locale's `tabs`. Existing translated tab/group/sub-group labels are preserved by position; brand-new English entries fall back to the English label until a translator localizes them.
- For every English page slug `<path>`: if `<locale>/<path>.mdx` exists on disk it goes into the locale's nav as `<locale>/<path>`; otherwise the page is **omitted** from the locale's nav and a redirect `/<locale>/<path>` → `/<path>` is appended to the top-level `redirects` array. Direct URL visits to a not-yet-translated locale page therefore land on the English version instead of 404'ing.
- Mintlify `openapi`-driven groups (no `pages:` array, just `{source, directory}`) are mirrored too — the `source` and `directory` get the `<locale>/` prefix automatically.
- Empty groups and tabs are dropped from the locale's nav after pruning.

Running the script never duplicates work: every redirect whose source begins with a known locale prefix is regenerated from scratch, so re-runs are stable. Manually-added redirects (anything else, including the existing `/en` → `/` rule) are kept untouched.

When to run it:

- After **adding** a page under the English root.
- After **removing** or **renaming** a page under the English root.
- After **translating** a previously-missing locale page (so the locale picks it up in nav and the redundant fallback redirect is dropped).
- After **adding a new locale** (see "Adding a new locale" below).

## What's out of scope

The architecture explicitly excludes a few things; PRs adding them will be declined or relocated:

- Trading strategy or market advice.
- Token-price predictions.
- Detailed tokenomics modeling beyond what is needed to read the code.
- Internal runbooks containing secrets or admin procedures.

## Translations

This repository is multi-language. Each locale lives under its own top-level directory and is wired into `docs.json` under `navigation.languages`.

### Current locales

| Code | Directory | URL prefix | Status |
|------|-----------|-----------|--------|
| `en` | repo root (no prefix) | `/<path>` | Source of truth. All new content lands in English first; the default locale lives at the root rather than under an `en/` directory. |
| `zh` | [`zh/`](./zh/) | `/zh/<path>` | Simplified Chinese. |
| `zh-Hant` | [`zh-Hant/`](./zh-Hant/) | `/zh-Hant/<path>` | Traditional Chinese. |
| `ja` | [`ja/`](./ja/) | `/ja/<path>` | Japanese. |
| `ko` | [`ko/`](./ko/) | `/ko/<path>` | Korean. |
| `ru` | [`ru/`](./ru/) | `/ru/<path>` | Russian. |
| `es` | [`es/`](./es/) | `/es/<path>` | Spanish. |
| `de` | [`de/`](./de/) | `/de/<path>` | German. |
| `fr` | [`fr/`](./fr/) | `/fr/<path>` | French. |
| `pt` | [`pt/`](./pt/) | `/pt/<path>` | Portuguese. |
| `tr` | [`tr/`](./tr/) | `/tr/<path>` | Turkish. |
| `vi` | [`vi/`](./vi/) | `/vi/<path>` | Vietnamese. |
| `id` | [`id/`](./id/) | `/id/<path>` | Indonesian. |
| `ar` | [`ar/`](./ar/) | `/ar/<path>` | Arabic (right-to-left). |

Each non-English locale mirrors the English tree page-for-page. Pages that haven't been translated yet are simply absent from the locale's directory — `scripts/sync-locales.py` (see above) keeps `docs.json` in sync with what's actually on disk and emits per-locale redirect rules so direct URL visits to untranslated pages fall through to the English version. Translators don't need to maintain stub files for missing pages.

Want to add another language? Open an issue first so we can scope review capacity. The mechanics are described in "Adding a new locale" below.

### Translation workflow

1. **Pick a page.** Find a page whose English source exists at the repo root but whose locale equivalent is missing under `<locale>/`. The full list is whatever `python3 scripts/sync-locales.py --diff` shows as "redirect" entries for that locale. Small, self-contained pages (glossary entries, single user flows) make good first translations.
2. **Open an issue first** if you're claiming a non-trivial page. This avoids two contributors translating the same page in parallel. Title format: `[<locale>] Translate /<path>`.
3. **Translate from the matching English file** at the repo root. The directory tree under the root and under `<locale>/` is identical — translating `products/cpmm/instructions.mdx` means creating `<locale>/products/cpmm/instructions.mdx`.
4. **Keep code blocks unchanged.** Variable names, SDK calls, JSON keys, and file paths stay in their original form. Only translate comments inside code if they are explanatory prose.
5. **Translate frontmatter.** Both `title` and `description` should be in the target language.
6. **Use locale-prefixed internal links.** Inside a translated page, write cross-references as `/<locale>/products/cpmm/math` — never as `/products/cpmm/math`. If the target page hasn't been translated yet, the redirect emitted by `scripts/sync-locales.py` will catch the URL and serve the English version instead, so the link works either way and never needs to be edited later.
7. **Match terminology.** A short glossary lives in `AGENTS.md`. For Chinese, prefer "兑换" over "交换" for swap, "流动性提供者" for LP, "联合曲线" for bonding curve. If you introduce a new term, add it to the glossary so future translators stay consistent.
8. **Translate JSX-component bodies, not the components themselves.** Keep `<Card>`, `<CardGroup>`, `<Info>`, `<Tip>` as-is, but translate their inner text and the `title` prop.
9. **Run `python3 scripts/sync-locales.py`** so the locale's nav picks up the new page (and the redundant fallback redirect is removed). Then `mint dev` to preview and `mint broken-links` to verify cross-references resolve.

### When the English source changes

When a PR updates the English source, the translations risk drifting:

- **Structural changes** (adding, removing, or renaming pages) — the contributor runs `python3 scripts/sync-locales.py` before merging. The script regenerates each locale's nav from English, drops references to localized files that don't exist, and emits per-locale fallback redirects for the missing pages. CI's `--check` mode blocks merges that forget this step.
- **Content changes** to a translated page — the translation continues to render but may be out of date. Translators add a `last-en-revision: <git-sha>` line to a page's frontmatter when they first translate it; a maintainer (or a CI check) compares that SHA against the latest commit touching the English source and flags drifting pages as `i18n-stale`.

If you don't want a stale translation in front of readers while you wait for a refresh, delete the translated `.mdx` and re-run `scripts/sync-locales.py`. The fallback redirect will route those URLs to English until the new translation lands.

### Adding a new locale

The script does most of the heavy lifting. Workflow:

1. Add the locale code to `LOCALE_CODES` in `scripts/sync-locales.py` (alphabetical order).
2. Add an entry to `docs.json` under `navigation.languages`. A minimal seed is enough; the script populates the rest:
   ```json
   { "language": "<locale>", "tabs": [] }
   ```
3. Translate the landing page first — `<locale>/index.mdx` is what readers hit when they switch locales. Add it on disk under the new directory.
4. Run `python3 scripts/sync-locales.py`. The script will mirror the English nav into the new locale, fall back to English labels (you can translate them later), and add a fallback redirect for every page you haven't translated yet.
5. Optionally start translating high-traffic pages (the Quick Start chapter, the product overviews) to seed the locale.
6. Open a PR titled `i18n: bootstrap <locale>` with the resulting `docs.json` change plus your seeded translations. Subsequent PRs fill in pages and replace English labels with translations as they land.

## Code of conduct

Be respectful. Assume good faith. Critique the work, not the contributor. Reviewers are volunteers and you are too — kindness is mutual.

If you witness or experience harassment in this repo, please flag it to the maintainers via a private channel (Discord DM or email if listed).

## Security disclosures

This repository is for documentation only — it does not host the on-chain programs. **Do not file a public issue for protocol vulnerabilities.** Submit those through the [Raydium bug bounty on Immunefi](https://immunefi.com/bug-bounty/raydium/information/) so disclosure is coordinated and rewarded properly.

If you find a *documentation* issue that could mislead users into a security-relevant mistake (a wrong instruction signer, a wrong PDA seed), it's fine to file it as a regular issue, but flag it as `security-doc` so we can prioritize.

## Recognition

Every merged PR adds the contributor to the project's contributor list. We don't currently maintain a separate `AUTHORS` file — the GitHub contributor graph is the source of truth.

Thank you for helping make these docs better.
