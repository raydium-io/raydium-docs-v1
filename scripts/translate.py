#!/usr/bin/env python3
"""
Batch translator for Raydium docs.

Walks the English source tree at the repo root, sends each .mdx page (and each
OpenAPI .yaml file) to the Anthropic API for translation into the eight target
locales, and writes the result to <locale>/<same path>.

USAGE
=====
  export ANTHROPIC_API_KEY=sk-ant-...
  python3 scripts/translate.py [--locales zh,ja,...] [--paths foo/bar.mdx,...]
                               [--model claude-sonnet-4-6] [--concurrency 8]
                               [--overwrite] [--dry-run]

DEFAULTS
========
  Locales:     zh, zh-Hant, ja, ko, ru, es, de, fr, pt, tr, vi, id, ar
               (skip whichever you want with --locales)
  Model:       claude-haiku-4-5   (override per --model)
  Concurrency: 8 in-flight requests (gentle on rate limits)
  Skip rule:   MDX  – if the target file already differs from the auto-generated
                       stub (i.e. someone has translated or hand-edited it),
                       skip unless --overwrite.
               YAML – if the target file exists and differs from the English
                       source, assume it has already been translated and skip
                       unless --overwrite. (Use --overwrite for the first pass
                       to refresh stale copies.)

WHAT IT TRANSLATES
==================
  MDX:
    - frontmatter title / description
    - all prose body
    - the AI-translation banner (in the target language)
    - JSX component bodies (Card / CardGroup / Info / Tip ...)
    - table cell content
    - alt text in markdown images
  OpenAPI YAML:
    - info.title, info.description
    - servers[].description
    - tags[].description (the root-level tags array)
    - every operation's summary and description
    - every parameter / response / requestBody / schema description
    - schema title (when present)

WHAT IT LEAVES ALONE
====================
  MDX:
    - frontmatter keys other than title/description (locale, mode, hidden, etc.)
    - fenced code blocks ``` ... ```
    - inline code `...`
    - markdown link URLs (the URL itself); only link text is translated
    - JSX component prop values that look like identifiers/URLs (href, icon, src, ...)
    - Solana addresses, PDAs, instruction names, account names, type names
  OpenAPI YAML:
    - structure, key names, ordering, comments, quoting style
    - operationId, $ref targets, parameter names, tag names, server URLs,
      enum values, defaults, examples, format specifiers, type names

INTERNAL LINKS
==============
  Internal links of the form "(/<path>)" are rewritten to "(/<locale>/<path>)"
  on translated pages so navigation stays inside the locale.

SAFETY
======
  - dry-run mode: prints what would be written, doesn't touch disk
  - per-file diff log: appended to scripts/translate.log
  - bails on any file whose body fails to round-trip the frontmatter
  - YAML translations are validated by re-parsing before write
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Iterable

# Make `python3 scripts/translate.py | head -30` exit cleanly instead of
# crashing with BrokenPipeError when `head` closes the pipe early.
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    # Windows or non-main thread — best-effort.
    pass

try:
    from anthropic import Anthropic
except ImportError:
    sys.stderr.write(
        "Missing dependency. Run:\n  pip install anthropic\n"
    )
    sys.exit(1)

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.scalarstring import (
        DoubleQuotedScalarString,
        LiteralScalarString,
        FoldedScalarString,
        PlainScalarString,
        SingleQuotedScalarString,
    )
    _HAS_RUAMEL = True
except ImportError:
    _HAS_RUAMEL = False


REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------- Locale config ---------------------------------------------------

LOCALES = {
    "zh": {
        "name_native": "简体中文 (Simplified Chinese)",
        "banner": "本页内容由 AI 自动翻译，所有内容以英文版本为准。",
        "cta": "查看英文版",
        "style_notes": (
            "- 使用大陆开发者文档常见的中性书面语，第二人称用「你」而非「您」。\n"
            "- 用词偏向大陆习惯：质押（不用「質押」）、开发者、流动性、文件、后端、前端、登录（不用「登入」）。\n"
            "- 标题不加句号；正文段落使用全角标点（，。；：「」），URL/代码/数字保留半角。\n"
            "- 避免「被」字滥用与英式被动结构；多用主动语态。\n"
            "- 不要把英文术语强行直译：CLMM、CPMM、AMM、PDA、CPI、ATA、LP、IDL、Anchor、Token-2022、OpenBook 全部保留英文。"
        ),
    },
    "zh-Hant": {
        "name_native": "繁體中文 (Traditional Chinese)",
        "banner": "本頁內容由 AI 自動翻譯，所有內容以英文版本為準。",
        "cta": "查看英文版",
        "style_notes": (
            "- 使用台港繁體技術文件常見用詞：質押、開發者、流動性、檔案（不是「文件」）、登入（不是「登錄」）、後端、前端、伺服器（不是「服务器」）、設定（不是「设置」）。\n"
            "- 第二人稱用「你」。語序與用語避免大陸譯腔。\n"
            "- 全形標點（，。；：「」『』），數字與代碼保留半形。\n"
            "- 標題結尾不加句號。"
        ),
    },
    "ja": {
        "name_native": "日本語 (Japanese)",
        "banner": "このページは AI による自動翻訳です。すべての内容は英語版を正とします。",
        "cta": "英語版を表示",
        "style_notes": (
            "- 文末は「です・ます」体で統一。命令形ではなく丁寧形（〜してください、〜します）。\n"
            "- カタカナ表記を多用：プール、スワップ、ミント、ティック、リクイディティ、フィー。\n"
            "- 中点「・」で並列、長音符「ー」を正しく使用（例：ユーザー、サーバー）。\n"
            "- 「〜になります」「〜となります」のような冗長な丁寧表現は避け、「〜です」「〜になる」を使用。\n"
            "- 英語の技術用語（CLMM、CPMM、PDA、CPI、ATA、LP、Token-2022、Anchor、IDL）はそのまま。"
        ),
    },
    "ko": {
        "name_native": "한국어 (Korean)",
        "banner": "이 페이지는 AI 자동 번역입니다. 모든 내용은 영문판을 기준으로 합니다.",
        "cta": "영문판 보기",
        "style_notes": (
            "- 어조는 「해요체」를 기본으로 사용합니다 (예: 합니다, 됩니다).\n"
            "- 외래어 표기법을 따릅니다: 스왑, 풀, 민트, 토큰, 슬리피지, 거래소.\n"
            "- 한자어는 자연스러운 한글 표현으로 옮기되, 기술 용어 (CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022) 는 영어로 유지합니다.\n"
            "- 띄어쓰기 규칙을 정확히 따르고, 조사 (을/를, 이/가, 은/는) 를 자연스럽게 선택합니다.\n"
            "- 영어 어순을 그대로 따르지 말고 SOV 한국어 어순으로 재구성하세요."
        ),
    },
    "ru": {
        "name_native": "русский (Russian)",
        "banner": "Эта страница переведена с помощью ИИ. За эталон принимается английская версия.",
        "cta": "Открыть английскую версию",
        "style_notes": (
            "- Используйте нейтрально-технический регистр документации для разработчиков. Местоимение «вы» пишется со строчной буквы.\n"
            "- Англицизмы DeFi-сленга оставляйте латиницей: swap, pool, slippage, mint, tick, liquidity, ликвидность можно перевести, но swap — оставить.\n"
            "- Все технические сокращения (CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022) — латиницей, не транслитерировать.\n"
            "- Избегайте кальки английского синтаксиса: переставляйте порядок слов и используйте естественные русские конструкции (творительный падеж, безличные предложения).\n"
            "- Цифры и единицы (\"$1.8B\", \"60 seconds\") сохраняйте в исходной форме, переводя только связующие слова."
        ),
    },
    "es": {
        "name_native": "español (Spanish)",
        "banner": "Esta página fue traducida automáticamente por IA. La versión en inglés es la fuente autorizada.",
        "cta": "Ver versión en inglés",
        "style_notes": (
            "- Use español neutro técnico válido tanto para España como para Latinoamérica. Trate al lector de «tú» (no «vos», no «usted»).\n"
            "- Evite localismos peninsulares («vale», «guay», «molar») y latinoamericanos muy regionales («chévere», «padre»).\n"
            "- Anglicismos técnicos aceptados: «swap», «pool», «slippage», «mint», «tick», «liquidity provider», en cursiva o entre comillas la primera vez si la frase lo permite, después en redonda.\n"
            "- Mantenga en inglés: CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022, OpenBook.\n"
            "- Use signos de apertura «¿» y «¡» cuando correspondan."
        ),
    },
    "de": {
        "name_native": "Deutsch (German)",
        "banner": "Diese Seite wurde mit KI automatisch übersetzt. Maßgeblich ist stets die englische Version.",
        "cta": "Englische Version ansehen",
        "style_notes": (
            "- Verwenden Sie die «Sie»-Form (mit großem S) im professionellen Entwickler-Doku-Register.\n"
            "- Bilden Sie deutsche Komposita statt Bindestrich-Übersetzungen: «Liquiditätspool», «Tokenpaar», «Auszahlungsadresse». Aber lassen Sie technische englische Fachbegriffe (CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022, OpenBook) unverändert.\n"
            "- Anglizismen wie «Swap», «Pool», «Mint», «Slippage», «Tick» dürfen bleiben, sind aber nicht zu kursivieren — sie zählen als Fachvokabular.\n"
            "- Vermeiden Sie wörtliche Übersetzungen englischer Phrasalverben; bauen Sie den Satz mit deutschem Verb-Endungs-Stil neu auf.\n"
            "- Korrekte deutsche Anführungszeichen „so“, nicht englische «so»."
        ),
    },
    "fr": {
        "name_native": "français (French)",
        "banner": "Cette page est traduite automatiquement par IA. La version anglaise fait foi.",
        "cta": "Voir la version anglaise",
        "style_notes": (
            "- Adressez-vous au lecteur avec «vous» (registre professionnel pour développeurs).\n"
            "- Utilisez les guillemets français «  » avec espaces insécables, et l'espace insécable avant « : ; ! ? ».\n"
            "- Anglicismes techniques tolérés : «le swap», «le pool», «le mint», «le slippage», «le tick» — sans italique.\n"
            "- Conservez en anglais : CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022, OpenBook.\n"
            "- Évitez les calques de la syntaxe anglaise (ne traduisez pas mot-à-mot les phrasal verbs ni l'ordre adjectif-nom)."
        ),
    },
    "pt": {
        "name_native": "português (Portuguese)",
        "banner": "Esta página foi traduzida automaticamente por IA. A versão em inglês é a fonte oficial.",
        "cta": "Ver versão em inglês",
        "style_notes": (
            "- Use português brasileiro neutro (audiência majoritária no Brasil), mas evite gírias regionais ou palavras puramente PT-BR que soariam estranhas em PT-PT (não use «legal», «bacana», «dar uma olhada»). Prefira termos compreendidos nos dois lados do Atlântico.\n"
            "- Trate o leitor por «você» em registro profissional.\n"
            "- Anglicismos técnicos OK: «swap», «pool», «mint», «slippage», «tick», «liquidity provider» (LP) — sem itálico.\n"
            "- Mantenha em inglês: CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022, OpenBook.\n"
            "- Não traduza «smart contract» (use o termo inglês), mas «contrato inteligente» é aceitável quando o contexto for claramente conceitual."
        ),
    },
    "tr": {
        "name_native": "Türkçe (Turkish)",
        "banner": "Bu sayfa yapay zekâ tarafından otomatik olarak çevrilmiştir. İngilizce sürüm esas alınır.",
        "cta": "İngilizce sürümü görüntüle",
        "style_notes": (
            "- Profesyonel «siz» dili kullanın; ikinci tekil «sen» yerine.\n"
            "- Ünlü uyumu ve ek seçimini titiz tutun (örn. «havuza», «havuzdan», «havuzun»). Yabancı kökenli sözcüklere ek getirirken kesme işareti kullanın: «CLMM'yi», «pool'a», «PDA'nın».\n"
            "- DeFi terimlerini İngilizce bırakın ilk geçişte: «swap», «pool», «mint», «slippage», «tick». Türkçe karşılığı yaygın olanlar (likidite, işlem ücreti) Türkçe yazılabilir.\n"
            "- Teknik kısaltmaları çevirmeyin: CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022, OpenBook.\n"
            "- İngilizce cümle yapısını taklit etmeyin; Türkçe SOV (özne-nesne-yüklem) sırasına göre yeniden kurun."
        ),
    },
    "vi": {
        "name_native": "Tiếng Việt (Vietnamese)",
        "banner": "Trang này được dịch tự động bằng AI. Phiên bản tiếng Anh là bản chính thức.",
        "cta": "Xem bản tiếng Anh",
        "style_notes": (
            "- Xưng hô với người đọc bằng «bạn» trong văn phong tài liệu kỹ thuật chuyên nghiệp.\n"
            "- Giữ nguyên tiếng Anh các thuật ngữ DeFi/Solana phổ biến: «swap», «pool», «mint», «slippage», «tick», «liquidity provider» (LP), CLMM, CPMM, AMM, PDA, CPI, ATA, IDL, Anchor, Token-2022, OpenBook. Có thể chú thích nghĩa Việt trong dấu ngoặc lần đầu xuất hiện.\n"
            "- Đảm bảo dấu thanh và dấu câu chính xác (sắc, huyền, hỏi, ngã, nặng). Khoảng cách trước dấu hai chấm/chấm phẩy theo chuẩn Việt (không có khoảng trắng trước, có khoảng trắng sau).\n"
            "- Tránh dịch sát cấu trúc tiếng Anh; sắp xếp lại câu theo trật tự chủ-vị tự nhiên trong tiếng Việt.\n"
            "- Số liệu, đơn vị và tên hàm/biến giữ nguyên định dạng gốc."
        ),
    },
    "id": {
        "name_native": "Bahasa Indonesia (Indonesian)",
        "banner": "Halaman ini diterjemahkan secara otomatis oleh AI. Versi bahasa Inggris adalah acuan resmi.",
        "cta": "Lihat versi bahasa Inggris",
        "style_notes": (
            "- Gunakan «Anda» untuk register profesional pengembang. Jangan gunakan «kamu».\n"
            "- Gunakan bahasa Indonesia baku (EYD): «aktivitas» bukan «aktifitas», «risiko» bukan «resiko», «praktik» bukan «praktek».\n"
            "- Pertahankan istilah teknis DeFi/Solana dalam bahasa Inggris: «swap», «pool», «mint», «slippage», «tick», «liquidity provider» (LP), CLMM, CPMM, AMM, PDA, CPI, ATA, IDL, Anchor, Token-2022, OpenBook. Padanan Indonesia (likuiditas, biaya transaksi) boleh dipakai bila sudah lazim.\n"
            "- Hindari kalque struktur bahasa Inggris; susun ulang kalimat dengan urutan dan konektor yang alami dalam bahasa Indonesia.\n"
            "- Awalan «di-» (penanda pasif) dipisah jika kata depan, disambung jika imbuhan: «di pool» (di lokasi), «diaktifkan» (pasif)."
        ),
    },
    "ar": {
        "name_native": "العربية (Arabic)",
        "banner": "هذه الصفحة مُترجَمة آليًا بواسطة الذكاء الاصطناعي. النسخة الإنجليزية هي المرجع المعتمد.",
        "cta": "عرض النسخة الإنجليزية",
        "style_notes": (
            "- اكتب بالعربية الفصحى الحديثة (MSA) المناسبة لتوثيق المطورين، لا بالعامية.\n"
            "- اتجاه النص العام من اليمين إلى اليسار، لكن أسماء الدوال، عناوين URL، أوامر الكود، علامات JSX/MDX، ومعرفات Solana تبقى من اليسار إلى اليمين كما هي.\n"
            "- استخدم الأرقام العربية المغربية (1, 2, 3) لتتطابق مع كتل الكود؛ تجنّب خلط الأرقام الهندية (٠ ١ ٢) داخل نفس الجملة.\n"
            "- استخدم الفاصلة العربية «،» وعلامة الاستفهام «؟»؛ تجنّب الفاصلة الإنجليزية «,».\n"
            "- احتفظ بالمصطلحات التقنية بالإنجليزية: CLMM, CPMM, AMM, PDA, CPI, ATA, LP, IDL, Anchor, Token-2022, OpenBook، swap, pool, mint, slippage. يمكن وضع ترجمة عربية بين قوسين عند أول ظهور (مثلاً: «swap (مبادلة)»).\n"
            "- اضبط التشكيل فقط حين يلزم لرفع الالتباس (همزات القطع، الشدّات على المصطلحات الجديدة)."
        ),
    },
}

# Subdirectories that hold English source content (relative to repo root).
# Anything under these is a candidate for translation if it matches a
# translatable extension (.mdx for prose, .yaml for OpenAPI specs).
SOURCE_DIRS = [
    "introduction", "protocol-overview", "getting-started", "user-flows",
    "products", "algorithms", "solana-fundamentals", "quick-start",
    "sdk-api", "integration-guides", "security",
    "api-reference", "reference", "resources", "ray",
]
ROOT_FILES = ["index.mdx", "ARCHITECTURE.mdx"]

# Extensions we know how to translate.
TRANSLATABLE_EXTS = {".mdx", ".yaml", ".yml"}

# Stub fingerprint — if the existing target body consists ONLY of our
# auto-generated AI-translation banner (no real translated content after it),
# nobody has translated the page yet and we can safely overwrite. Translated
# files have the same banner at the TOP followed by translated body, so the
# regex must match the entire body, not just its prefix.
#
# Use re.fullmatch (not re.match + re.MULTILINE) so that:
#   - the regex must consume the whole body string
#   - the trailing $ matches end-of-string, not end-of-line
STUB_BODY_RE = re.compile(
    r"<Info>\s*\n\s*\*\*[^*]+\*\*\s*\n\s*\n\s*\[[^\]]+→\][^\n]+\n</Info>\s*",
)

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


# ---------- Translation prompt ---------------------------------------------

SYSTEM_PROMPT = """You are a senior technical translator producing the {locale_name} edition of Raydium's developer documentation. Raydium is a DEX on Solana.

OUTPUT FORMAT
You MUST return the translated MDX file, exactly. No prose around it, no code fences, no commentary. The output replaces the input file on disk verbatim.

PRESERVE EXACTLY (do not translate, do not reformat):
- Fenced code blocks (``` ... ```) — every byte inside the fence stays English.
- Inline code spans `like this` — stay English.
- Frontmatter keys (everything before the first `---`). Translate ONLY the values of `title` and `description`. Keep `locale`, `mode`, `hidden`, and any other key intact.
- JSX component names: <Info>, <Tip>, <Warning>, <Note>, <CardGroup>, <Card>, <Tabs>, <Tab>, <Steps>, <Step>, <Accordion>, <AccordionGroup>, <Frame>, <CodeGroup>, <Expandable>.
- JSX prop names and prop values that are URLs, identifiers, icon names, hrefs, or numeric. Examples to leave untouched: `cols={{2}}`, `icon="circle-info"`, `href="/products/cpmm/overview"`.
- Solana program IDs, mint addresses, PDAs, account names, instruction names, struct field names, type names, file paths.
- URL paths inside markdown links and JSX `href` props (the URL itself). Translate only the visible link text.
- HTML entities (e.g. `&amp;`), the literal characters `<`, `>`, `=`, `{{`, `}}`, `\\`.
- Math expressions wrapped in `$...$` or `$$...$$`.

MDX-SPECIFIC ESCAPING — these are required to keep the file parseable. Failing to preserve them breaks Mintlify's build:
- Dollar-sign escapes. Whenever the source has `\$` (backslash before `$`), preserve the backslash exactly. NEVER write a bare `$` followed by digits, letters, or another `$` in prose: `\$5,000`, `\$RAY`, `\$1.8B` must keep the backslash. If the translation introduces a trailing currency form like `5,50 $`, escape it too as `5,50 \$`. The backslash applies to every `$` that is not inside a fenced code block, an inline code span, or an actual KaTeX math expression that uses LaTeX commands like `\\frac`, `\\sqrt`, `\\text`. (When in doubt, escape.)
- Bare `<` in prose. The MDX parser treats `<` as the start of a JSX tag. If `<` is followed by `=`, a digit, or whitespace-then-digit, the parser errors. Whenever you write a comparison or "less-than" relation in prose, wrap the whole expression in backticks (`` `<= 10,000` ``) or replace `<` with `&lt;`. Example: NOT `tick_lower <= MAX_TICK`, instead `` `tick_lower <= MAX_TICK` `` or `tick_lower &lt;= MAX_TICK`.
- JSX single-quoted attributes containing apostrophes. If the translation introduces an apostrophe inside an attribute like `placeholder='...'`, the quote closes early and parsing breaks. When this happens, switch the outer quote: `placeholder="l'IA…"`. If the body contains both `'` and `"`, use a JSX expression instead: `placeholder={{`l'IA "tick"…`}}`.

TRANSLATE:
- Prose paragraphs.
- Headings (## Some heading), unless the heading is a code identifier.
- Markdown link visible text — `[visible text](url)`.
- JSX `title=` and `description=` prop values when they are user-facing strings (NOT when they look like identifiers).
- Body of <Info>, <Tip>, <Note>, <Warning>, <Card> and similar components.
- Table cell content (markdown tables `| ... | ... |`).
- Alt text in markdown images `![alt](src)`.
- Frontmatter `title` and `description` values.

INTERNAL LINK REWRITING:
- Markdown links and JSX hrefs that begin with a single slash (e.g. `/products/cpmm/overview`) are internal documentation links. Rewrite them by inserting `/{locale_code}` after the leading slash, so `/products/cpmm/overview` becomes `/{locale_code}/products/cpmm/overview`.
- DO NOT rewrite external links (those starting with `http://`, `https://`, `mailto:`, or anything containing `://`).
- DO NOT rewrite anchor-only links (`#section`).
- DO NOT rewrite paths that already start with `/{locale_code}/` or any other locale code (`/zh/`, `/ja/`, `/de/`, etc.).
- DO NOT rewrite paths inside fenced code blocks or inline code.

AI-TRANSLATION BANNER:
The very first thing in the document body — immediately after the closing `---` of frontmatter, before any heading or content — must be exactly this <Info> block:

<Info>
  **{banner}**

  [{cta} →](/ENGLISH_LINK_FROM_USER_MESSAGE)
</Info>

Replace `ENGLISH_LINK_FROM_USER_MESSAGE` literally with the path given on the `english_link:` line of the user message — it starts with a slash and does not include `.mdx`. Do NOT include backticks around it; it should be a normal URL inside the markdown link.

If the source file already starts with an existing <Info> banner, REPLACE it with the one above. If the source file does not, INSERT this <Info> block as the first body element.

LOCALIZATION (NOT JUST TRANSLATION) FOR {locale_name}:
- This is a localization, not a literal translation. Re-express each idea the way a native technical writer in {locale_name} would write it from scratch. If a sentence reads as a calque of English, rewrite it.
- Sentence structure: rebuild sentences using the rhythm, clause order, and connector words natural to {locale_name}. Don't preserve English subject-verb-object order when the target language prefers something else (e.g. SOV in Korean / Japanese, verb-initial constructions in Arabic, topic-comment in Chinese).
- Register: Raydium's docs are direct, second person, active voice, no marketing fluff. Adapt this register to whatever the equivalent professional-but-friendly register is in {locale_name} — that means polite-plain form (です・ます) for Japanese, 해요체 for Korean, "vous" + clear technical tone for French, neutral 你 for Chinese, "Sie" for German, neutral "tú" for Spanish, MSA for Arabic, "ban" / friendly-formal "Anda" for Indonesian, "bạn" for Vietnamese, "siz/siz" professional register for Turkish, "você" professional for Portuguese.
- Idioms & metaphors: replace English-rooted metaphors that won't land in the target language with native equivalents. If no equivalent exists, drop the metaphor and state the underlying meaning plainly.
- Punctuation & typography: use the target language's conventions — full-width punctuation 「」 ， 。 in CJK, French spaces before « : ; ! ? », guillemets « » where appropriate, Arabic comma ، and question mark ؟, Vietnamese spacing rules, etc.
- Numbers and units stay in their original form (e.g. "$1.8B", "0.25 bps", "60 seconds"). Localize how they're embedded into a sentence, but don't convert currencies or change unit symbols.
- For technical terms that are universally English in the Solana / DeFi space (CLMM, CPMM, AMM, slippage, swap, pool, mint, LP, NFT, PDA, CPI, ATA, Token-2022, OpenBook, Anchor, IDL), keep them in English unless the locale strongly prefers a localized term — in which case use the local term parenthetically the first time, then carry on with the English term.
- Arabic specifically: write right-to-left prose. Keep all code, URLs, and JSX/MDX tag names left-to-right (browsers handle the bidi). Use Arabic numerals' Latin form ("3", "10") to match the surrounding code samples; Arabic-Indic digits are fine inside pure prose paragraphs but stay consistent within a sentence.

LOCALE-SPECIFIC STYLE NOTES FOR {locale_name}:
{style_notes}

Now translate the file below. Return the translated MDX file with no preamble or postamble.
"""


# ---------- YAML translation prompt ----------------------------------------

YAML_SYSTEM_PROMPT = """You are a senior technical translator producing the {locale_name} edition of Raydium's OpenAPI documentation. Raydium is a DEX on Solana.

You will be given a JSON array of English strings extracted from an OpenAPI spec. These are user-facing fields: API titles, endpoint summaries, parameter descriptions, schema descriptions, etc. Mintlify renders them on the public docs site, so they must read naturally to {locale_name}-speaking developers.

OUTPUT FORMAT
You MUST return a single JSON array of strings, exactly the same length as the input, in the same order. No prose around it, no code fences, no commentary, no key. Just the raw JSON array. The array must parse with json.loads().

PRESERVE EXACTLY (do not translate, do not reformat):
- Inline backtick code spans `like this` — keep the English identifier inside the backticks.
- Solana program IDs, mint addresses, PDAs, account names, instruction names, struct field names, type names, file paths.
- Numbers, units, version strings, enum tokens (e.g. "0.25 bps", "$1.8B", "v3", "true", "false").
- Keep code-style fragments such as $ref values, JSON keys mentioned inside backticks, and HTTP verbs (GET, POST, etc.) untouched.
- HTML / markdown special characters and entities.
- The capitalization of acronyms: CLMM, CPMM, AMM, LP, NFT, PDA, CPI, ATA, SOL, USDC, RAY, IDO, TVL, DEX.
- Newline characters: if an input string contains literal `\\n` (newline) sequences, preserve them at the same positions in the output.

TRANSLATE:
- Prose sentences and noun phrases.
- Field-purpose phrases like "Token mint address", "Whether the request was successful".
- Cache hints like "Cached 60 seconds." — translate to natural {locale_name}.

LOCALIZATION (NOT JUST TRANSLATION) FOR {locale_name}:
- Re-express each string the way a native technical writer in {locale_name} would phrase it on a public API reference page. Avoid word-for-word calques.
- Match the developer-doc register of {locale_name}: terse, factual, professional-but-friendly. Mirror the brevity of the English source — if the English is one sentence, the output is one sentence.
- Use the target language's natural sentence structure and connector words; don't preserve English clause order if the target language prefers another.
- Use the target language's punctuation conventions: full-width punctuation in CJK, Arabic comma ، and question mark ؟ for Arabic, French non-breaking spaces before « : ; ! ? », etc.
- For technical terms that are universally English in the Solana / DeFi space (CLMM, CPMM, AMM, slippage, swap, pool, mint, LP, NFT, PDA, CPI, ATA, Token-2022, OpenBook, Anchor, IDL), keep them in English.
- Arabic: write the prose RTL, but keep identifiers, URLs, and field names left-to-right.

LOCALE-SPECIFIC STYLE NOTES FOR {locale_name}:
{style_notes}

Now translate the array below. Return only the JSON array.
"""


# Keys whose scalar string values we translate. (Other scalars stay as-is.)
YAML_TRANSLATABLE_KEYS = {"title", "summary", "description"}

# If any ancestor key on the path equals one of these, we treat the subtree as
# data / examples and do NOT translate even when we encounter a translatable
# key inside it. This protects example payloads, enum tables, default values.
YAML_DATA_CONTEXT_KEYS = {"example", "examples", "enum", "default", "x-codeSamples"}


def _yaml_loader() -> "YAML":
    y = YAML(typ="rt")  # round-trip: preserves order, comments, quoting style
    y.preserve_quotes = True
    y.width = 4096      # don't auto-wrap long scalars
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _is_translatable_yaml_value(val) -> bool:
    """Cheap filter: skip empty / numeric-only / single-token scalar."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if not s:
        return False
    # Skip pure URL or mailto.
    if re.match(r"^[a-z][a-z0-9+.-]*://\S+$", s, re.IGNORECASE):
        return False
    if s.startswith("mailto:"):
        return False
    # Skip bare identifiers (no whitespace, no punctuation suggesting prose).
    # If it contains a space OR a sentence-ending punctuation OR a CJK char,
    # it's probably prose.
    if " " in s or any(c in s for c in ".,;:!?，。；：！？") \
       or any("一" <= c <= "鿿" for c in s):
        return True
    # Single bare word — leave it alone.
    return False


def _collect_yaml_strings(node, path: tuple, out: list) -> None:
    """Walk the parsed YAML tree, collect (location, value) for translatable scalars.

    `out` is a list of dicts: {"key_path": tuple, "value": str}.
    `key_path` is the path of mapping keys leading to this scalar (for replay).
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k in YAML_DATA_CONTEXT_KEYS:
                continue
            new_path = path + (k,)
            if k in YAML_TRANSLATABLE_KEYS and _is_translatable_yaml_value(v):
                out.append({"path": new_path, "value": str(v)})
            else:
                _collect_yaml_strings(v, new_path, out)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _collect_yaml_strings(item, path + (i,), out)
    # scalars at non-translatable keys: ignore


def _replace_yaml_strings(node, path: tuple, replacements: dict) -> None:
    """Walk the tree again and substitute translated strings in place."""
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k in YAML_DATA_CONTEXT_KEYS:
                continue
            new_path = path + (k,)
            if k in YAML_TRANSLATABLE_KEYS and new_path in replacements:
                # Preserve the original scalar style (double-quoted, literal, etc.)
                node[k] = _wrap_like(v, replacements[new_path])
            else:
                _replace_yaml_strings(v, new_path, replacements)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _replace_yaml_strings(item, path + (i,), replacements)


def _wrap_like(original, new_text: str):
    """Return new_text wrapped in the same ruamel scalar style as `original`."""
    if not _HAS_RUAMEL:
        return new_text
    if isinstance(original, LiteralScalarString):
        return LiteralScalarString(new_text)
    if isinstance(original, FoldedScalarString):
        return FoldedScalarString(new_text)
    if isinstance(original, SingleQuotedScalarString):
        return SingleQuotedScalarString(new_text)
    if isinstance(original, DoubleQuotedScalarString):
        return DoubleQuotedScalarString(new_text)
    if isinstance(original, PlainScalarString):
        return PlainScalarString(new_text)
    # Plain Python str: default to double-quoted to match the existing convention
    # in the Raydium OpenAPI files.
    return DoubleQuotedScalarString(new_text)


def _batched(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _translate_string_batch(
    client: "Anthropic",
    strings: list[str],
    locale: str,
    model: str,
) -> list[str]:
    """Send one batch of English strings to Claude, get translations back."""
    cfg = LOCALES[locale]
    system = YAML_SYSTEM_PROMPT.format(
        locale_name=cfg["name_native"],
        style_notes=cfg.get("style_notes", "(no locale-specific notes)"),
    )
    user_msg = json.dumps(strings, ensure_ascii=False)

    last_err = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=16000,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = "".join(
                b.text for b in resp.content if b.type == "text"
            ).strip()
            # Tolerate accidental ```json fences.
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
                text = re.sub(r"\n?```\s*$", "", text)
            translated = json.loads(text)
            if (
                not isinstance(translated, list)
                or len(translated) != len(strings)
                or not all(isinstance(x, str) for x in translated)
            ):
                raise ValueError(
                    f"bad response shape: expected list[{len(strings)}] of str, "
                    f"got {type(translated).__name__} of len "
                    f"{len(translated) if hasattr(translated, '__len__') else '?'}"
                )
            return translated
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"translation batch failed after 3 attempts: {last_err}")


def translate_yaml_text(
    client: "Anthropic",
    src_text: str,
    locale: str,
    model: str,
    batch_size: int = 40,
) -> str:
    """Translate user-visible strings inside an OpenAPI YAML and return new text."""
    if not _HAS_RUAMEL:
        raise RuntimeError(
            "ruamel.yaml is required for OpenAPI YAML translation. "
            "Install with:  pip install ruamel.yaml"
        )

    yaml = _yaml_loader()
    from io import StringIO
    data = yaml.load(src_text)

    items: list[dict] = []
    _collect_yaml_strings(data, (), items)

    if not items:
        return src_text  # nothing user-visible to translate

    # Translate in batches and accumulate replacements keyed by path tuple.
    replacements: dict[tuple, str] = {}
    sources = [it["value"] for it in items]
    paths = [it["path"] for it in items]

    out_pos = 0
    for batch in _batched(sources, batch_size):
        translated = _translate_string_batch(client, batch, locale, model)
        for i, t in enumerate(translated):
            replacements[paths[out_pos + i]] = t
        out_pos += len(batch)

    _replace_yaml_strings(data, (), replacements)

    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


# ---------- File walking ----------------------------------------------------

def english_pages() -> list[Path]:
    """All English source files we know how to translate (relative paths)."""
    out: list[Path] = []
    for sub in SOURCE_DIRS:
        base = REPO_ROOT / sub
        if not base.exists():
            continue
        for ext in TRANSLATABLE_EXTS:
            for p in base.rglob(f"*{ext}"):
                out.append(p.relative_to(REPO_ROOT))
    for f in ROOT_FILES:
        if (REPO_ROOT / f).exists():
            out.append(Path(f))
    out = sorted(set(out))
    return out


def is_stub(target: Path) -> bool:
    """Return True if target MDX file is still our auto-generated stub."""
    if not target.exists():
        return True
    try:
        text = target.read_text()
    except Exception:
        return False
    m = FRONTMATTER_RE.match(text)
    if not m:
        return False
    body = text[m.end():].strip()
    return bool(STUB_BODY_RE.fullmatch(body))


def is_yaml_stub(target: Path, source: Path) -> bool:
    """Return True if target YAML file looks untranslated.

    A target is considered a stub if:
      - it doesn't exist; or
      - it is byte-identical to the English source (a raw copy); or
      - its user-visible scalars (title/summary/description) still match the
        English source verbatim (i.e. nothing was translated).
    """
    if not target.exists():
        return True
    try:
        src_text = source.read_text()
        tgt_text = target.read_text()
    except Exception:
        return False
    if src_text == tgt_text:
        return True
    if not _HAS_RUAMEL:
        # Without ruamel we can't introspect — fall back to byte-equality only.
        return False
    try:
        yaml = _yaml_loader()
        src_doc = yaml.load(src_text)
        tgt_doc = yaml.load(tgt_text)
    except Exception:
        return False
    src_items: list[dict] = []
    tgt_items: list[dict] = []
    _collect_yaml_strings(src_doc, (), src_items)
    _collect_yaml_strings(tgt_doc, (), tgt_items)
    src_by_path = {it["path"]: it["value"] for it in src_items}
    tgt_by_path = {it["path"]: it["value"] for it in tgt_items}
    if not src_by_path:
        return False
    same = sum(
        1 for p, v in src_by_path.items()
        if tgt_by_path.get(p) == v
    )
    # If ≥80% of the user-visible strings are still identical to English,
    # treat the file as not-yet-translated.
    return (same / len(src_by_path)) >= 0.8


# ---------- Per-page translation -------------------------------------------

def _translate_mdx(
    client: Anthropic,
    en_rel: Path,
    target: Path,
    locale: str,
    model: str,
) -> tuple[Path, str]:
    """Translate one MDX page. Returns (target, status)."""
    src_text = (REPO_ROOT / en_rel).read_text()
    cfg = LOCALES[locale]
    english_link = str(en_rel.with_suffix("")).replace("\\", "/")

    system = SYSTEM_PROMPT.format(
        locale_name=cfg["name_native"],
        locale_code=locale,
        banner=cfg["banner"],
        cta=cfg["cta"],
        style_notes=cfg.get("style_notes", "(no locale-specific notes)"),
    )
    user_msg = (
        f"english_link: /{english_link}\n"
        f"locale_code: {locale}\n"
        f"--- BEGIN SOURCE ---\n"
        f"{src_text}\n"
        f"--- END SOURCE ---\n"
    )

    translated = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=16000,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            translated = "".join(
                b.text for b in resp.content if b.type == "text"
            ).rstrip() + "\n"
            break
        except Exception as e:
            if attempt == 2:
                return target, f"error: {e}"
            time.sleep(2 ** attempt)

    if not translated or not translated.startswith("---"):
        return target, "error: no frontmatter in output"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(translated)
    return target, "wrote"


def _translate_yaml(
    client: Anthropic,
    en_rel: Path,
    target: Path,
    locale: str,
    model: str,
) -> tuple[Path, str]:
    """Translate one OpenAPI YAML. Returns (target, status)."""
    if not _HAS_RUAMEL:
        return target, "error: ruamel.yaml not installed (pip install ruamel.yaml)"
    src_text = (REPO_ROOT / en_rel).read_text()
    try:
        translated = translate_yaml_text(client, src_text, locale, model)
    except Exception as e:
        return target, f"error: {e}"

    # Sanity check: re-parse the output to make sure we didn't break the spec.
    try:
        _yaml_loader().load(translated)
    except Exception as e:
        return target, f"error: translated yaml does not parse: {e}"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(translated)
    return target, "wrote"


def translate_one(
    client: Anthropic,
    en_rel: Path,
    locale: str,
    model: str,
    overwrite: bool,
    dry_run: bool,
) -> tuple[Path, str]:
    """Translate one English file into one locale. Returns (target, status)."""
    target = REPO_ROOT / locale / en_rel
    src = REPO_ROOT / en_rel
    ext = en_rel.suffix.lower()

    # Stub / overwrite gating.
    if ext == ".mdx":
        if not overwrite and not is_stub(target):
            return target, "skip-existing"
    elif ext in (".yaml", ".yml"):
        if not overwrite and not is_yaml_stub(target, src):
            return target, "skip-existing"
    else:
        return target, f"error: unsupported extension {ext}"

    if dry_run:
        return target, "dry-run"

    if ext == ".mdx":
        return _translate_mdx(client, en_rel, target, locale, model)
    else:
        return _translate_yaml(client, en_rel, target, locale, model)


# ---------- CLI -------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--locales",
        default=",".join(LOCALES.keys()),
        help="Comma-separated list of locale codes to translate into.",
    )
    ap.add_argument(
        "--paths",
        default="",
        help=(
            "Comma-separated list of source paths (relative to repo root) "
            "to translate. Default: all English source mdx files."
        ),
    )
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--overwrite", action="store_true",
                    help="Overwrite even if target is no longer a stub.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    locales = [l.strip() for l in args.locales.split(",") if l.strip()]
    for l in locales:
        if l not in LOCALES:
            sys.exit(f"unknown locale: {l}. valid: {','.join(LOCALES)}")

    if args.paths:
        rels = [Path(p.strip()) for p in args.paths.split(",") if p.strip()]
    else:
        rels = english_pages()

    if not args.dry_run:
        if "ANTHROPIC_API_KEY" not in os.environ:
            sys.exit("ANTHROPIC_API_KEY is not set.")

    client = Anthropic() if not args.dry_run else None
    jobs = [(rel, loc) for rel in rels for loc in locales]

    print(f"Translating {len(rels)} pages × {len(locales)} locales = {len(jobs)} jobs.")
    print(f"Model: {args.model}  Concurrency: {args.concurrency}  "
          f"Dry-run: {args.dry_run}  Overwrite: {args.overwrite}")
    print()

    counts = {"wrote": 0, "skip-existing": 0, "dry-run": 0, "error": 0}
    log_path = REPO_ROOT / "scripts" / "translate.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as logf:
        logf.write(f"\n=== run @ {time.strftime('%Y-%m-%d %H:%M:%S')} "
                   f"locales={locales} pages={len(rels)} model={args.model} ===\n")

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.concurrency
        ) as pool:
            futures = {
                pool.submit(
                    translate_one,
                    client, rel, loc, args.model, args.overwrite, args.dry_run,
                ): (rel, loc)
                for rel, loc in jobs
            }
            for fut in concurrent.futures.as_completed(futures):
                rel, loc = futures[fut]
                target, status = fut.result()
                key = (
                    "error" if status.startswith("error")
                    else status
                )
                counts[key] = counts.get(key, 0) + 1
                short = f"{loc}/{rel}".ljust(60)
                line = f"[{status:12s}] {short}"
                print(line)
                logf.write(line + "\n")

    print()
    print("Summary:")
    for k, v in counts.items():
        print(f"  {k:14s} {v}")
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
