# Documentation project instructions

## About this project

- This is the Raydium documentation set, built on [Mintlify](https://mintlify.com).
- Pages are MDX files with YAML frontmatter; navigation lives in `docs.json`.
- The information architecture, audience model, and chapter map are defined in `ARCHITECTURE.mdx` — consult that before authoring any new page.
- The English tree at the repo root is the source of truth. Thirteen locales (`zh`, `zh-Hant`, `ja`, `ko`, `ru`, `es`, `de`, `fr`, `pt`, `tr`, `vi`, `id`, `ar`) mirror it; locale pages that don't exist on disk are auto-redirected to English by rules generated in `docs.json` — see "Multi-language hygiene" below.
- Run `mint dev` to preview locally, `mint broken-links` to check links.

## Terminology

- Prefer **CPMM** (constant-product market maker) for the new default pool, not "v5" or "raydium-cp-swap" outside of code references.
- **AMM v4** is the original constant-product + OpenBook pool — always written with the version suffix.
- **CLMM** is the concentrated-liquidity program; positions are NFTs, not LP tokens.
- **Stable AMM** is the StableSwap-style pool program. **It is still a current product** — the docs cover it as a live integration target. Don't add deprecation banners.
- **Farm v6** is the current farm generation; v3/v5 are wind-down only.
- **LaunchLab** is the bonding-curve launch program; the user-facing brand is "LaunchLab", not "launchpad".
- **Perps** are powered by Orderly Network (white-label backend); refer to "Raydium Perps" for the product surface and "Orderly" for the underlying venue.
- Use **liquidity provider** or **LP** for stakers in pools/farms; **trader** for swap users.

## Style preferences

- Use active voice and second person ("you").
- Keep sentences concise — one idea per sentence.
- Use sentence case for headings.
- Bold for UI elements: Click **Settings**.
- Code formatting for file names, commands, paths, program IDs, and code references.
- Every code block that targets the SDK or a program ID should pin a version (SDK version, program ID, Solana cluster, last-verified date) per the convention in `ARCHITECTURE.mdx`. The current canonical pin is `@raydium-io/raydium-sdk-v2@0.2.42-alpha`; if you bump it, run a global search to keep every code-demo page in lock-step.

## Cross-reference conventions

- **Program IDs and shared PDAs** live only in `reference/program-addresses.mdx`. Other pages link to it; don't hardcode addresses elsewhere. Source-code links there are limited to publicly-available repos (`raydium-amm`, `raydium-cp-swap`, `raydium-clmm`, `raydium-idl`); the rest of the program family is closed-source — write "source not publicly available" rather than inventing a URL.
- **Error codes** live only in `reference/error-codes.mdx`. Instruction pages link to its anchors.
- **Math definitions** live in `algorithms/`. Per-product `math.mdx` pages give the product-specific instantiation and link back.
- **API endpoints** live in `api-reference/openapi/*.yaml`. Don't restate request/response shapes in narrative pages; link to the endpoint.

## Multi-language hygiene

If you add, remove, or rename any English page — or translate a previously-missing locale page — run:

```bash
python3 scripts/sync-locales.py
```

The script mirrors the English nav into every locale, prunes references to locale files that don't exist, and emits per-locale fallback redirects so direct URL visits to untranslated pages land on English instead of 404'ing. Re-runs are idempotent; CI runs `--check` to block merges that forget this step. See `CONTRIBUTING.md` § "Keeping locales in sync" for the full workflow.

## Content boundaries

The following are explicitly out of scope (see `ARCHITECTURE.mdx` § "What is explicitly out of scope"):

- Trading strategy or market advice.
- Token-price predictions.
- Detailed tokenomics modeling beyond what is needed to read the code.
- Internal runbooks containing secrets or admin procedures.
