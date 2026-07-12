# Internationalization (i18n) Design

Design for multi-language support. Status: **specified, not yet built**.
Initial languages: **English** (default), **Español**, **Deutsch**. The design
must scale to more later (e.g. Chinese) without restructuring.

> ⚠️ `CLAUDE.md` currently says "do not build i18n now". When implementation
> starts, update `CLAUDE.md` and `docs/portfolio-build-plan.md` to match this
> document.

---

## Core principles

1. **Languages are data, not code.** `build.py` holds a single language
   registry; every feature (output trees, switcher, hreflang, sitemap, search,
   RSS) iterates over it. No `if lang == "es"` scattered around.
2. **Existence of a file defines availability.** A page exists in a language
   if and only if its `<lang>.html` file exists. No configuration flags.
3. **Pluggable per-language tokenizer** in the search engine, from day one.
4. **Fully static, no JS required.** Each language is a real set of URLs;
   the switcher is plain links. No client-side language swapping, no
   `localStorage`, no content hidden in the DOM.

## Rejected alternatives (and why)

- **All languages in one HTML, toggled by JS** — kills SEO (no per-language
  URLs, no hreflang, mixed-language documents), no shareable language links,
  every visitor downloads every language, JS becomes load-bearing.
- **Translated slugs** (`/es/articulos/controlador-brazo/`) — weak SEO gain,
  but breaks the automatic same-name mapping between translations, adds a
  slug-mapping layer and silent-breakage risk. Slugs are identical in all
  languages.

## Language registry

Small data table (in `build.py` or a JSON file), one entry per language:

```python
LANGUAGES = {
    "en": {"name": "English", "default": True},
    "es": {"name": "Español"},
    "de": {"name": "Deutsch"},
}
```

Per language it also carries: the chrome-string translations (nav labels,
footer, "Read more", the fallback banner text, …) and search config (stopword
list / tokenizer). **Adding a language** = one registry entry + one strings
table + translated content files. Nothing else changes.

## URL scheme

Default language (English) lives at the root; every other language under a
prefix. Slugs are identical across languages.

```
/projects/robot-arm/          ← English
/es/projects/robot-arm/       ← Spanish
/de/projects/robot-arm/       ← German
```

## Source layout: page bundles

Every page (project, article, standalone page) is a **folder**, named by its
slug, containing one HTML file per language plus all of its assets:

```
content/projects/robot-arm/
├── en.html                 ← required: default language, fallback source
├── es.html                 ← present = Spanish translation exists
├── de.html                 ← absent  = no German translation
├── images/
│   ├── graph.en.jpg        ← translated figure, English labels
│   ├── graph.es.jpg        ← translated figure, Spanish labels
│   └── gripper.jpg         ← language-neutral asset
└── files/
    └── wiring-diagram.pdf
```

Rules:

- Files named `<lang>.html` (where `<lang>` is in the registry) are the page's
  translations. `en.html` is **mandatory**; others optional.
- Everything else in the folder, recursively, is an **asset**.
- Asset subfolders (`images/`, `files/`, `models/`, …) are free-form.
- **Translated figures use a language suffix** on the same base name:
  `graph.en.jpg` / `graph.es.jpg`. This is an authoring convention (keeps the
  pair adjacent and obviously related) — the build treats them as ordinary
  assets. Language-neutral assets take plain names (`gripper.jpg`).

## Asset handling (build output)

The build copies a bundle's assets **into every language's output folder**:

```
dist/projects/robot-arm/images/       ← all assets
dist/es/projects/robot-arm/images/    ← all assets (copy)
```

So every language's HTML references assets with the same simple relative path
(`images/graph.es.jpg`) and it is always present. Cost: duplicated bytes in
`dist/` only (source and repo hold one copy). Accepted at current scale.

*Future optimization if the deploy artifact gets heavy (large `.glb`/video):
copy assets once to the default-language folder and rewrite asset paths in
translated pages — a contained `build.py` change; content files unaffected.*

## Untranslated content: fallback pages with banner

Every page is generated in **every** language, always. When `<lang>.html` is
missing for a page:

- The **chrome** (header, nav, footer, template strings) renders in the
  visitor's language.
- The **body** is taken from the original language (`en.html`, or the page's
  only existing translation).
- A **banner** at the top of the content states that this article/project is
  not available in the current language (banner text comes from the chrome
  strings; body keeps its original `lang` attribute for accessibility).

Consequence: the language switcher never dead-ends — the same URL exists in
every language.

## SEO rules for fallback pages

To avoid duplicate-content penalties and dishonest annotations:

- **`hreflang` alternates list only genuine translations.** Fallback URLs are
  never declared as alternates.
- Every alternate set includes **`x-default` → the English page**.
- **Fallback pages carry `<link rel="canonical">` pointing to the
  original-language page** (and optionally `noindex`).
- **`sitemap.xml` lists only genuine translations**, each with its hreflang
  set. Fallback pages are excluded.

## Language switcher (the "button")

A small header component — plain links (or a native disclosure), no JS
required — offering EN | ES | DE. Each link points to **the same page** in the
target language (which always exists; see fallback pages). `build.py` injects
the correct URLs per page. Rendered from the language registry, so new
languages appear automatically.

## Index pages, per language

Each language gets its own project index, article index, and tag pages.
Listing policy: **fallback listing** — untranslated items appear in every
language's index with a small **language badge** (e.g. "ES") linking to the
fallback page. Genuine translations appear without a badge.

## Search

- **One search index per language** (`search-index.en.json`, `…es.json`, …),
  containing only that language's genuine translations. The search page/
  dropdown queries only the current language's index.
- Tokenization is **per-language**: shared splitting logic, per-language
  stopword lists (from the registry).
- **Chinese (future):** no word boundaries — use **character bigram indexing**
  (index adjacent character pairs). Works with BM25, needs no dictionary or
  dependency. The pluggable-tokenizer requirement exists for this.

## RSS

One feed per language, containing only that language's genuine translations.

## Chrome strings

All template strings (nav, footer, buttons, banner text, index headings, date
formatting) come from the per-language strings table — never hardcoded in
templates. Templates reference string keys; the build substitutes per
language.

## Implementation notes

- This makes the bundle folder the **universal content format** — projects,
  articles, and standalone pages all work the same way, keeping `build.py`
  small.
- Quality gates extend naturally: unknown `<lang>` filename → build failure;
  broken asset reference → build failure (link checker runs per generated
  page).
- **Timing recommendation:** build i18n *after* the 4–6 real launch projects
  are written. Translating placeholder content is wasted work, and the
  migration of existing content files into bundle folders is mechanical.

## Decision log

| Decision | Choice |
|---|---|
| Architecture | Parallel static trees per language (no JS swapping) |
| Source format | Bundle folder per page, `<lang>.html` files |
| Default language | English (`en.html` mandatory, root URLs) |
| Slugs | Identical across languages (no translated slugs) |
| Assets | Co-located in bundle; copied to every language's output |
| Translated figures | Suffix convention: `name.<lang>.ext` |
| Missing translation | Generate page anyway: localized chrome + original body + banner |
| hreflang | Genuine translations only + `x-default` → English |
| Fallback pages SEO | `canonical` → original; excluded from sitemap |
| Index listings | Fallback listing with language badge |
| Search | One index per language; pluggable tokenizer; bigrams for zh |
| RSS | One feed per language |
