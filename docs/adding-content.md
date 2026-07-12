# Adding a project or article (and getting it into search)

Step-by-step guide for adding content to the site. The short version: **one
bundle folder with an `en.html` inside + a rebuild = the page exists in every
language tree, appears on its index, gets its tag pages, and is searchable.**
Search inclusion is automatic — there is no separate registration step — but
*how* you write the file decides how well it ranks, so the details below
matter.

Related docs: [`taxonomies.md`](taxonomies.md) (allowed tags, single source of
truth), [`i18n-design.md`](i18n-design.md) (the multi-language design this
guide follows), and [`portfolio-build-plan.md`](portfolio-build-plan.md)
(overall plan).

---

## Step 1 — Choose the type and create the bundle

| Type | Folder | It is… | Body structure |
|---|---|---|---|
| Project | `content/projects/` | a thing you built | context → your role → constraints/tradeoffs → approach → result → media → links |
| Article | `content/articles/` | writing | a clean reading column, sections as needed |

Every page is a **bundle**: one folder named by its slug, holding the page's
languages and assets side by side:

```
content/projects/<slug>/
├── en.html            ← required: English source, fallback for other languages
├── es.html            ← optional: Spanish translation (present = it exists)
├── de.html            ← optional: German translation
└── images/            ← assets, free-form subfolders
    ├── graph.en.jpg   ← translated figure (language suffix, by convention)
    ├── graph.es.jpg
    └── gripper.jpg    ← language-neutral asset
```

- **The folder name is the slug** — there is no `slug` frontmatter field
  (writing one fails the build). Conventions: lowercase, hyphen-separated,
  short, stable — it becomes the permanent URL `/projects/<slug>/` (and
  `/es/projects/<slug>/`, …). Don't rename it after deploying or you break
  inbound links.
- A flat `content/<type>/<slug>.html` file is a build error — bundles only.
- **HTML only, never Markdown.** Content files are hand-written HTML
  fragments; the build has no Markdown parser, on purpose.
- (Fixed pages under `content/pages/` are also bundles, but they can't hold
  assets — put shared images in `static/images/`.)

## Step 2 — Write the frontmatter

`en.html` starts with a frontmatter block between two `---` lines, then the
HTML body. All five fields are required — the build **fails** if one is
missing:

```
---
title: Vision-Based Sorting Conveyor
description: A conveyor demo that classifies parts by color and shape with OpenCV and diverts them with a PLC-driven gate.
date: 2026-01-15
discipline: automation
tech: opencv, python, raspberry-pi, plc
---
```

Field by field:

| Field | Rules |
|---|---|
| `title` | The page's `<h1>`, the link text in search results and cards, and the `<title>` tag. |
| `description` | One sentence. Shown on cards, used as the meta description, **and shown verbatim as the excerpt under every search result** — write it for a human deciding whether to click. |
| `date` | `YYYY-MM-DD`, nothing else (anything else fails the build). Controls ordering: indexes, tag pages, and the no-query view on `/search/` all list newest first. |
| `discipline` | **Exactly one**, from the `discipline` list in `docs/taxonomies.md`. Unknown values fail the build. |
| `tech` | Comma-separated, zero or more, all from the `tech` list in `docs/taxonomies.md`. The key must be present even if empty (`tech:`). Unknown values fail the build. |

Frontmatter is flat `key: value` lines only — no lists, no nesting, no quotes
needed.

`date`, `discipline`, and `tech` live **only in `en.html`** — they are shared
metadata and must never drift between translations, so a translation file
that redefines them fails the build (see Step 5).

## Step 3 — If you need a new tag, add it to the taxonomy FIRST

The build validates every `discipline` and `tech` value against
`docs/taxonomies.md` and **fails on anything it doesn't know**. This is
deliberate — it stops the tag vocabulary from fragmenting (`robot` vs
`robotics`, `raspberrypi` vs `raspberry-pi`).

To introduce a tag:

1. Open `docs/taxonomies.md`.
2. Add a `- tagname` bullet under the right heading (`## discipline` or
   `## tech`).
3. Follow the conventions: lowercase, hyphen-separated, **singular**, no
   synonyms of an existing tag, no version numbers (`ros2` is grandfathered;
   don't add `python3`).
4. Now use it in your frontmatter.

Full details — naming rules, how the taxonomy file is parsed, renaming and
removing tags, adding a discipline — in [`adding-tags.md`](adding-tags.md).

Tag pages (`/tags/<tag>/`, `/discipline/<d>/`) and the chip lists in the
search UI are generated automatically, per language, for every tag *actually
in use* — a tag that's in the taxonomy but on no content simply doesn't
appear anywhere.

## Step 4 — Write the body

Everything after the second `---` is the page body: a **bare HTML fragment**.

- No `<html>`, `<head>`, `<body>`, header, nav, or footer — the build wraps
  your fragment in the type template (`templates/project.html` or
  `article.html`) and then in `templates/base.html`. Title, date, discipline
  link, and tech chips are rendered from the frontmatter; don't repeat them.
- Start headings at `<h2>` (the template already renders the `<h1>` from
  `title`).
- Use semantic HTML: `<section>`, `<p>`, `<figure>`, `<ul>`, `<code>`…
- Escape literal `<`, `>`, `&` in text as `&lt;`, `&gt;`, `&amp;`.
- **Bundle assets:** everything in the bundle besides the `<lang>.html`
  files is copied next to the generated page (in every language tree), so
  reference them relatively: `<img src="images/gripper.jpg">`. Relative
  links work unchanged from `/projects/<slug>/` and `/es/projects/<slug>/`
  alike.
- Internal links must resolve: every root-relative `href`/`src` (e.g.
  `/projects/other-thing/`, `/static/images/photo.webp`) is checked against
  the generated output, and **a broken one fails the build**. (Relative links
  are not checked — one more reason to keep them simple.) Reference static
  assets by their plain name — cache-bust hashing is applied to CSS/JS
  automatically.

A minimal project skeleton:

```html
<section>
  <h2>Context</h2>
  <p>…</p>

  <h2>My role</h2>
  <p>…</p>

  <h2>Constraints &amp; tradeoffs</h2>
  <p>…</p>

  <h2>Approach</h2>
  <p>…</p>

  <h2>Result</h2>
  <p>…</p>
</section>
```

## Step 5 — Translations (optional, add them whenever)

Nothing else is required for the page to exist in every language: without a
translation, `/es/…` and `/de/…` serve a **fallback page** — the English body
with a banner saying the content isn't available in that language yet.
Fallback pages are excluded from that language's search index, the sitemap,
and `hreflang` alternates, so adding a translation later upgrades all of that
automatically.

To translate, add `<lang>.html` next to `en.html`, where `<lang>` is a code
from the language registry in `build.py` (currently `es`, `de` — a filename
that isn't in the registry fails the build). Rules:

- Frontmatter carries **only `title` and `description`**, translated.
  Repeating `date`, `discipline`, or `tech` fails the build — shared
  metadata lives in `en.html` alone.
- The body is a full translation of the English body, same structure.
- **Root-relative internal links must point into the same language's tree**
  (`/es/contact.html`, `/es/projects/other-thing/`) — bodies are emitted
  as-is, links are not rewritten. Relative asset links need no change.
- **Figures with burned-in text** follow the language-suffix convention:
  `graph.en.jpg` / `graph.es.jpg`, side by side in the bundle; each body
  references its own. The build treats them as ordinary assets.

## Step 6 — Understand what search does with your bundle (nothing to do, but worth knowing)

On every build, `build.py` writes **one index per language** —
`dist/search-index.<lang>.json` — each containing only that language's
*genuine* translations (fallbacks are excluded, so Spanish search never
returns English text). The client (`static/js/search.js`) fetches the
current language's index and ranks matches with BM25.

How the indexer reads your file — and how to write with that in mind:

- **Weighting: title ×3, tags ×2, body ×1.** A word in your `title` counts
  triple; `discipline`/`tech` tags count double. Put the words people would
  actually search for in the title.
- **The `description` is the search-result excerpt**, shown under the title
  in every result. It is *also* indexed as part of the body text.
- **Tokenization** (identical in `build.py` and `search.js`, keep them in
  sync if you ever touch one): lowercase → strip accents (`López` matches
  `lopez`) → split on anything non-alphanumeric → drop stop-words (each
  language's list lives in the registry in `build.py`) → crude
  singularization (a trailing `s` is dropped from words longer than 3
  letters, so `motors` matches `motor`).
- **HTML tags and comments are stripped** before indexing — markup, class
  names, and `<!-- comments -->` are not searchable. Alt text inside
  attributes is not indexed either; important words belong in visible text.
- **Known quirks** of the deliberately simple stemmer: `robotics` stems to
  `robotic`, not `robot`, so a query for "robot" only finds pages that
  contain the word "robot" literally somewhere. Spanish `-es` plurals
  (`sensores`) don't reduce to their singular. If a term matters, make sure
  the form people will type appears in your text.

## Step 7 — Build and verify locally

From the repo root (**`python3`, not `python` — plain `python` is not on
this machine's PATH**):

```
python3 build.py
```

A successful build ends with `OK: <n> pages, all internal links resolve`.
If it fails instead, the message names the file and the problem — see the
table in Step 9.

Then serve the output (search needs HTTP — the index fetch fails from
`file://`):

```
python3 -m http.server 8000 -d dist
```

Checklist at `http://localhost:8000`:

1. Your page renders at `/projects/<slug>/` (or `/articles/<slug>/`) with
   title, date, discipline, and tech chips.
2. It appears on `/projects/` (or `/articles/`), newest first, with its tech
   chips on the card.
3. Its tag pages list it.
4. **Header search box:** type a distinctive word from your title — the page
   should appear in the dropdown.
5. **`/search/`:** it shows in the no-query list, and toggling its tags
   filters it in/out correctly (AND and OR modes).
6. **Other languages:** `/es/projects/<slug>/` shows either your Spanish
   translation (no banner) or the English body with the fallback banner.
   If you added `es.html`, search on `/es/search/` finds its Spanish title.

## Step 8 — Deploy

```
git add content/ docs/
git commit -m "Add <title>"
git push
```

The GitHub Action rebuilds and publishes `dist/` to
johanalejandrolopezarias.com. Never commit `dist/` — it's gitignored and
regenerated on every deploy.

## Step 9 — If the build fails

| Message | Cause / fix |
|---|---|
| `flat content files are gone — move it to …/en.html` | You created `content/<type>/<slug>.html`; make a folder and put the file inside as `en.html`. |
| `bundle has no en.html (English is mandatory)` | Every bundle needs an `en.html`, even if translations exist. |
| `'….html' is not a language in the registry` | The translation filename must be a registry code (`es`, `de`) — check for typos, or add the language to `LANGUAGES` in `build.py` first. |
| `drop the 'slug' field — the bundle folder name is the slug` | Remove `slug:` from the frontmatter; rename the folder if you wanted a different URL. |
| `… belong(s) only in en.html` | A translation file redefines `date`, `discipline`, or `tech` — delete those lines; translations carry only `title` and `description`. |
| `missing frontmatter (expected two '---' lines)` | The file doesn't start with a `---` block, or the closing `---` is missing. |
| `missing frontmatter field(s): …` | Add the named fields. `tech` may be empty but the key must exist. |
| `date must be YYYY-MM-DD` | Fix the date format (e.g. `2026-07-11`). |
| `unknown discipline '…'` / `unknown tech tag(s): …` | Typo, or the tag isn't in `docs/taxonomies.md` yet — add it there first (Step 3). |
| `fixed-page bundles can't hold assets` | Bundles under `content/pages/` are chrome, not content — move the asset to `static/images/`. |
| `broken internal link(s): …` | Each listed `page: target` pair is a link to something that doesn't exist in `dist/`. Fix the path or add the missing asset — and remember translated bodies link into their own tree (`/es/…`). |

The build either succeeds completely or fails loudly — there is no state
where a page half-exists or is published but missing from search.
