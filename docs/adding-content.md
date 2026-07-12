# Adding a project or article (and getting it into search)

Step-by-step guide for adding content to the site. The short version: **one
HTML file in the right folder + a rebuild = the page exists, appears on its
index, gets its tag pages, and is searchable.** Search inclusion is automatic —
there is no separate registration step — but *how* you write the file decides
how well it ranks, so the details below matter.

Related docs: [`taxonomies.md`](taxonomies.md) (allowed tags, single source of
truth) and [`portfolio-build-plan.md`](portfolio-build-plan.md) (overall plan).

---

## Step 1 — Choose the type and create the file

| Type | Folder | It is… | Body structure |
|---|---|---|---|
| Project | `content/projects/` | a thing you built | context → your role → constraints/tradeoffs → approach → result → media → links |
| Article | `content/articles/` | writing | a clean reading column, sections as needed |

Create one file: `content/<projects|articles>/<slug>.html`.

- The file name should match the `slug` you'll put in the frontmatter
  (not enforced, but keeps the repo greppable).
- Slug conventions: lowercase, hyphen-separated, short, stable — it becomes
  the permanent URL `/projects/<slug>/` or `/articles/<slug>/`. Don't rename
  it after deploying or you break inbound links.
- **HTML only, never Markdown.** Content files are hand-written HTML
  fragments; the build has no Markdown parser, on purpose.

## Step 2 — Write the frontmatter

The file starts with a frontmatter block between two `---` lines, then the
HTML body. All six fields are required — the build **fails** if one is
missing:

```
---
title: Vision-Based Sorting Conveyor
description: A conveyor demo that classifies parts by color and shape with OpenCV and diverts them with a PLC-driven gate.
slug: vision-sorting-conveyor
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
| `slug` | Lowercase-hyphenated; becomes the URL. Must be unique within its folder (duplicate slugs fail the build). |
| `date` | `YYYY-MM-DD`, nothing else (anything else fails the build). Controls ordering: indexes, tag pages, and the no-query view on `/search/` all list newest first. |
| `discipline` | **Exactly one**, from the `discipline` list in `docs/taxonomies.md`. Unknown values fail the build. |
| `tech` | Comma-separated, zero or more, all from the `tech` list in `docs/taxonomies.md`. The key must be present even if empty (`tech:`). Unknown values fail the build. |

Frontmatter is flat `key: value` lines only — no lists, no nesting, no quotes
needed.

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
search UI are generated automatically for every tag *actually in use* — a tag
that's in the taxonomy but on no content simply doesn't appear anywhere.

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
- Internal links must resolve: every root-relative `href`/`src` (e.g.
  `/projects/other-thing/`, `/static/images/photo.webp`) is checked against
  the generated output, and **a broken one fails the build**. Reference
  static assets by their plain name (`/static/images/foo.png`) — cache-bust
  hashing is applied to CSS/JS automatically.

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

## Step 5 — Understand what search does with your file (nothing to do, but worth knowing)

On every build, `build.py` indexes **all projects and articles** into
`dist/search-index.json`. The client (`static/js/search.js`) fetches that
file and ranks matches with BM25. Because indexing re-runs from scratch each
build, your new page is searchable the moment the build succeeds.

How the indexer reads your file — and how to write with that in mind:

- **Weighting: title ×3, tags ×2, body ×1.** A word in your `title` counts
  triple; `discipline`/`tech` tags count double. Put the words people would
  actually search for in the title.
- **The `description` is the search-result excerpt**, shown under the title
  in every result. It is *also* indexed as part of the body text.
- **Tokenization** (identical in `build.py` and `search.js`, keep them in
  sync if you ever touch one): lowercase → strip accents (`López` matches
  `lopez`) → split on anything non-alphanumeric → drop English/Spanish
  stop-words → crude singularization (a trailing `s` is dropped from words
  longer than 3 letters, so `motors` matches `motor`).
- **HTML tags and comments are stripped** before indexing — markup, class
  names, and `<!-- comments -->` are not searchable. Alt text inside
  attributes is not indexed either; important words belong in visible text.
- **Known quirks** of the deliberately simple stemmer: `robotics` stems to
  `robotic`, not `robot`, so a query for "robot" only finds pages that
  contain the word "robot" literally somewhere. Spanish `-es` plurals
  (`sensores`) don't reduce to their singular. If a term matters, make sure
  the form people will type appears in your text.

## Step 6 — Build and verify locally

From the repo root (**`python3`, not `python` — plain `python` is not on
this machine's PATH**):

```
python3 build.py
```

A successful build ends with `OK: <n> pages, all internal links resolve`.
If it fails instead, the message names the file and the problem — see the
table in Step 8.

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

## Step 7 — Deploy

```
git add content/ docs/
git commit -m "Add <title>"
git push
```

The GitHub Action rebuilds and publishes `dist/` to
johanalejandrolopezarias.com. Never commit `dist/` — it's gitignored and
regenerated on every deploy.

## Step 8 — If the build fails

| Message | Cause / fix |
|---|---|
| `missing frontmatter (expected two '---' lines)` | The file doesn't start with a `---` block, or the closing `---` is missing. |
| `missing frontmatter field(s): …` | Add the named fields. `tech` may be empty but the key must exist. |
| `date must be YYYY-MM-DD` | Fix the date format (e.g. `2026-07-11`). |
| `unknown discipline '…'` / `unknown tech tag(s): …` | Typo, or the tag isn't in `docs/taxonomies.md` yet — add it there first (Step 3). |
| `duplicate slug '…'` | Two files in the same folder share a `slug`; make them unique. |
| `broken internal link(s): …` | Each listed `page: target` pair is a link to something that doesn't exist in `dist/`. Fix the path or add the missing asset. |

The build either succeeds completely or fails loudly — there is no state
where a page half-exists or is published but missing from search.
