# Raydium Documentation

Community-maintained reference and guides for [Raydium](https://raydium.io) — the AMM v4, CPMM, CLMM, Farm/Staking, and LaunchLab programs on Solana, plus the Perps integration on top of Orderly Network.

This repository is the source for the documentation site. Built on [Mintlify](https://mintlify.com); pages are MDX files with YAML frontmatter; navigation is configured in [`docs.json`](./docs.json). The information architecture, audience model, and per-chapter writing brief live in [`ARCHITECTURE.mdx`](./ARCHITECTURE.mdx).

## What's inside

- **171 pages** across 15 top-level chapters: Introduction, Protocol Overview, Getting Started, User Flows, Solana Fundamentals, Products (AMM v4 / CPMM / CLMM / Farm-Staking / Perps / Stable AMM / AMM Routing / LaunchLab — LaunchLab includes a Tips & Gotchas sub-folder), Algorithms, Quick Start, SDK & API, Integration Guides, Security, RAY token & Protocol revenues, API Reference, Reference, Resources.
- **Three audience tracks** in parallel: developers/integrators, protocol researchers/auditors, and end users. Every chapter is tagged with the audience it primarily serves.
- **Runnable code** for every instruction-level surface — TypeScript, Rust, and Python — pinned to specific SDK versions and program IDs.
- **Multi-language.** Source of truth is English at the repo root. Thirteen locales (`zh`, `zh-Hant`, `ja`, `ko`, `ru`, `es`, `de`, `fr`, `pt`, `tr`, `vi`, `id`, `ar`) are mirrored under top-level locale folders; MDX content is kept in sync by Mintlify's auto-translation. Translators are welcome to PR corrections — see [`CONTRIBUTING.md § Translations`](./CONTRIBUTING.md#translations).

## Contributing

This is an open-source documentation set. **Issues and pull requests are welcome from anyone** — corrections, new examples, missing edge cases, clarifications, fresh diagrams, or entirely new pages are all in scope.

- Found a bug, a stale code sample, a broken link, or a confusing explanation? [**Open an issue**](https://github.com/raydium-io/raydium-docs-v1/issues/new).
- Have a fix or an addition ready? [**Open a pull request**](https://github.com/raydium-io/raydium-docs-v1/compare).
- Want to discuss a larger change before writing it? Open an issue first so we can align on scope.

Before contributing, please read [`CONTRIBUTING.md`](./CONTRIBUTING.md) — it covers the writing style, the per-product page template, version-pin requirements for code samples, and the PR checklist.

New contributors: anything labeled `good first issue` is a low-risk way in.

## Run the docs locally

You'll need [Node.js](https://nodejs.org/) ≥ 18 and the Mintlify CLI:

```bash
npm i -g mint
```

Then, from the repo root (where `docs.json` lives):

```bash
mint dev
```

The site renders at `http://localhost:3000`. Edits hot-reload.

To check for broken internal links before committing:

```bash
mint broken-links
```

## Project layout

```
.
├── CONTRIBUTING.md       # Style, scope, PR guide, and translation workflow
├── AGENTS.md             # Guidance for AI coding agents working in this repo
├── README.md             # This file
├── LICENSE
├── docs.json             # Mintlify navigation + site config (multi-language schema)
├── style.css             # Homepage chrome overrides
├── favicon.svg
│
├── ARCHITECTURE.mdx      # Source of truth for IA, audience model, per-product template
├── index.mdx             # Landing page (English, default locale)
├── introduction/         # English source content lives at the repo root
├── protocol-overview/    # — the default locale has no path prefix.
├── getting-started/
├── user-flows/
├── solana-fundamentals/
├── products/             # AMM v4, CPMM, CLMM, Farm/Staking, Perps, Stable, Routing, LaunchLab
├── algorithms/
├── quick-start/
├── sdk-api/
├── integration-guides/
├── security/
├── ray/                  # RAY tokenomics, treasury, buybacks, staking, protocol revenues
├── api-reference/        # Per-service API docs — overview pages + openapi/*.yaml
├── reference/
├── resources/
│
├── zh/                   # Locale mirrors — same tree, translated content.
├── zh-Hant/              # MDX content is auto-translated by Mintlify;
├── ja/                   # corrections via PR are welcome.
├── ko/                   # Per-locale navigation (tab/group labels and page paths)
├── ru/                   # is maintained by hand in docs.json.
├── es/
├── de/
├── fr/
│
├── images/               # Diagrams and illustrations (locale-agnostic)
└── logo/                 # Site logo (locale-agnostic)
```

URLs: the default locale (English) lives at the root, e.g. `/products/cpmm/overview`. Other locales are prefixed, e.g. `/zh/products/cpmm/overview`. Visitors with a matching browser preference are served the localized tree where pages are translated and the English version where they aren't. Legacy `/en/<path>` URLs redirect to `/<path>`.

## Editorial conventions

- **One topic, one home.** Concepts are defined in exactly one chapter and linked from others. See `ARCHITECTURE.mdx § Design principles`.
- **Version-pin code samples.** Every code-heavy page declares the SDK version, program ID, Solana cluster, and last-verified date near the top.
- **Separate "how it works" from "how to use it."** Algorithms live in `algorithms/`; user flows live in `user-flows/`. Product chapters link both ways.
- **Security is a first-class chapter, not a footnote.** Auditors should not have to grep product chapters.

## License

The documentation content in this repository is released under the [MIT License](./LICENSE). Code samples are released under the same license unless otherwise noted at the page level.

The Raydium name, logo, and brand assets are property of Raydium and are not covered by this license.

## Acknowledgements

This documentation set draws from the Raydium SDK v2 source, the Anchor IDLs published with each on-chain program, the Raydium API v3 surface, the public audit reports (OtterSec, MadShield, Halborn), and conversations with integrators. Errors are the contributors' own — please flag them via issues.

## Useful links

- Live docs site: _add the deployed URL once published_
- Raydium app: <https://raydium.io>
- Raydium SDK v2: <https://github.com/raydium-io/raydium-sdk-V2>
- Raydium SDK v2 demos: <https://github.com/raydium-io/raydium-sdk-V2-demo>
- Bug bounty (Immunefi): <https://immunefi.com/bug-bounty/raydium/information/>
- Discord: <https://discord.gg/raydium>
