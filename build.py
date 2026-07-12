#!/usr/bin/env python3
"""Static site generator. Reads content/, wraps it in templates/, writes dist/.

Content lives in page bundles: one folder per page, named by its slug,
holding a hand-written HTML fragment per language (`en.html` mandatory;
translations come with i18n — see docs/i18n-design.md), each with `---`
frontmatter:
  content/pages/<slug>/     -> dist/<slug>.html        fixed pages
  content/projects/<slug>/  -> dist/projects/<slug>/   portfolio items
  content/articles/<slug>/  -> dist/articles/<slug>/   writing

Derived output regenerated on every run: the projects/articles index pages,
one page per tag in use (/discipline/<d>/ and /tags/<t>/), sitemap.xml, and
an RSS feed of articles. static/ is copied across with content-hash cache
busting on CSS/JS filenames.

Quality gates — the build FAILS on: missing frontmatter fields, tags not
listed in docs/taxonomies.md, and broken internal links.
"""

import hashlib
import html
import json
import re
import shutil
import sys
import unicodedata
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
DIST = ROOT / "dist"
TAXONOMY_FILE = ROOT / "docs" / "taxonomies.md"

SITE_URL = "https://www.johanalejandrolopezarias.com"
SITE_NAME = "Johan Alejandro López Arias"

# ---------------------------------------------------------------------------
# Language registry — languages are data, not code (docs/i18n-design.md).
# Every i18n feature (output trees, switcher, hreflang, search, RSS) will
# iterate over this table; adding a language means adding an entry plus
# translated content, never a new code path. `strings` holds every
# human-visible chrome string; templates reference them as {{s.key}} and
# {tag}/{site} slots are filled with str.format() at the point of use.
# ---------------------------------------------------------------------------
LANGUAGES = {
    "en": {
        "name": "English",
        "default": True,
        "months": ("January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November",
                   "December"),
        "date_fmt": "{day} {month} {year}",
        "strings": {
            # header / nav
            "nav_aria": "Primary",
            "nav_home": "Home",
            "nav_projects": "Projects",
            "nav_articles": "Articles",
            "nav_about": "About",
            "nav_contact": "Contact",
            "nav_search": "Search",
            "search_placeholder": "Search…",
            "search_aria": "Search projects and articles",
            # footer
            "footer_copyright": "&copy; 2026 Johan Alejandro López Arias.",
            # detail pages
            "filed_under": "filed under",
            # section index pages (the lede doubles as the meta description)
            "projects_title": "Projects",
            "projects_lede": "Things I've built across robotics, automation, and manufacturing.",
            "articles_title": "Articles",
            "articles_lede": "Occasional writing about engineering, tooling, and this site itself.",
            "empty_listing": "Nothing here yet — check back soon.",
            # tag pages
            "discipline_lede": "Everything filed under the {tag} discipline.",
            "tech_heading": "Tagged “{tag}”",
            "tech_lede": "Projects and articles tagged {tag}.",
            # search page
            "search_title": "Search",
            "search_lede": "Find projects and articles by text, by tag, or both.",
            "search_description": "Search projects and articles by text or filter by tag.",
            "search_disciplines": "Disciplines",
            "search_tech": "Tech",
            "search_mode_legend": "Tag matching",
            "search_mode_or": "any selected tag",
            "search_mode_and": "all selected tags",
            # feeds
            "rss_link_title": "Articles — RSS",
            "rss_feed_title": "{site} — Articles",
            "rss_feed_description": "Articles by {site}.",
        },
    },
}

DEFAULT_LANG = next(code for code, cfg in LANGUAGES.items() if cfg.get("default"))

REQUIRED_PAGE_FIELDS = ("title", "description")
REQUIRED_ITEM_FIELDS = REQUIRED_PAGE_FIELDS + ("date", "discipline", "tech")

# The two sections that share the item pipeline, mapped to their type
# templates. Their index titles and ledes live in the language registry
# as <section>_title / <section>_lede.
SECTIONS = {"projects": "project.html", "articles": "article.html"}


def fail(message):
    sys.exit(f"build failed: {message}")


def parse_frontmatter(text):
    """Split a `---`-delimited frontmatter block from the HTML body.

    Frontmatter here is flat `key: value` lines only (no lists/nesting),
    so a hand-rolled parser is enough and avoids a YAML dependency.
    """
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("missing frontmatter (expected two '---' lines)")
    _, frontmatter_block, body = parts

    fields = {}
    for line in frontmatter_block.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    return fields, body.strip()


def load_taxonomies():
    """Read the controlled vocabularies from docs/taxonomies.md.

    That file is the single source of truth: a `## discipline …` or
    `## tech …` heading followed by one `- tag` bullet per allowed value.
    """
    vocab, current = {}, None
    for line in TAXONOMY_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].split()[0]
            vocab[current] = set()
        elif line.startswith("- ") and current:
            vocab[current].add(line[2:].strip())
    for required in ("discipline", "tech"):
        if not vocab.get(required):
            fail(f"{TAXONOMY_FILE} defines no '{required}' tags")
    return vocab


def render(template, mapping):
    """Fill a template's {{placeholders}} by plain string substitution."""
    for key, value in mapping.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def localize(template, lang):
    """Fill a template's {{s.key}} placeholders from the language registry."""
    return render(template, {"s." + key: value
                             for key, value in LANGUAGES[lang]["strings"].items()})


def display_date(d, lang):
    """Human-readable date in the page's language, e.g. '14 May 2026'."""
    cfg = LANGUAGES[lang]
    return cfg["date_fmt"].format(day=d.day, month=cfg["months"][d.month - 1],
                                  year=d.year)


def tag_list_html(tech):
    """A list of tech tags rendered as chips linking to their tag pages."""
    if not tech:
        return ""
    links = "\n".join(
        f'      <li><a class="tag" href="/tags/{t}/">{t}</a></li>' for t in tech
    )
    return f'<ul class="tag-list">\n{links}\n    </ul>'


def bundle_sources(folder):
    """Yield (slug, en.html path) for each page bundle in a content folder.

    A bundle is a directory named by its slug containing en.html (English
    is the mandatory default language — docs/i18n-design.md). Both checks
    here exist so content can never be silently skipped: a flat .html left
    over from the pre-bundle layout fails loudly, as does a bundle folder
    with no en.html in it.
    """
    for stray in sorted(folder.glob("*.html")):
        fail(f"{stray}: flat content files are gone — move it to "
             f"{stray.relative_to(ROOT).with_suffix('')}/en.html")
    for bundle in sorted(p for p in folder.iterdir() if p.is_dir()):
        source = bundle / "en.html"
        if not source.is_file():
            fail(f"{bundle}: bundle has no en.html (English is mandatory)")
        yield bundle.name, source


def load_items(section, vocab):
    """Read one section's content bundles, validating frontmatter as we go."""
    items = []
    for slug, source in bundle_sources(CONTENT / section):
        fields, body = parse_frontmatter(source.read_text(encoding="utf-8"))
        if "slug" in fields:
            fail(f"{source}: drop the 'slug' field — the bundle folder name is the slug")

        # `tech` must be present but may be empty; everything else needs a value.
        missing = [
            f for f in REQUIRED_ITEM_FIELDS
            if f not in fields or (not fields[f] and f != "tech")
        ]
        if missing:
            fail(f"{source}: missing frontmatter field(s): {', '.join(missing)}")

        try:
            when = date.fromisoformat(fields["date"])
        except ValueError:
            fail(f"{source}: date must be YYYY-MM-DD (got '{fields['date']}')")

        if fields["discipline"] not in vocab["discipline"]:
            fail(f"{source}: unknown discipline '{fields['discipline']}'"
                 " — add it to docs/taxonomies.md first")
        tech = [t.strip() for t in fields["tech"].split(",") if t.strip()]
        unknown = sorted(set(tech) - vocab["tech"])
        if unknown:
            fail(f"{source}: unknown tech tag(s): {', '.join(unknown)}"
                 " — add them to docs/taxonomies.md first")

        items.append({
            **fields,
            "slug": slug,
            "tech": tech,
            "when": when,
            "url": f"/{section}/{slug}/",
            "body": body,
        })

    items.sort(key=lambda i: i["when"], reverse=True)
    return items


def card_html(card_template, item, lang):
    return render(card_template, {
        "url": item["url"],
        "title": item["title"],
        "date": item["date"],
        "date_display": display_date(item["when"], lang),
        "discipline": item["discipline"],
        "description": item["description"],
        "tech_list": tag_list_html(item["tech"]),
    })


def listing_body(heading, lede, items, card_template, lang):
    """Shared body for index pages and tag pages: heading + card list."""
    if items:
        cards = "\n".join(card_html(card_template, i, lang) for i in items)
        cards_block = f'<ul class="card-grid">\n{cards}\n</ul>'
    else:
        cards_block = f'<p>{LANGUAGES[lang]["strings"]["empty_listing"]}</p>'
    return f'<h1>{heading}</h1>\n<p class="lede">{lede}</p>\n{cards_block}'


def copy_static():
    """Copy static/ into dist/static/, giving CSS and JS files a short
    content-hash suffix (styles.css -> styles.1a2b3c4d.css) so browsers can
    cache them forever yet pick up changes immediately. Returns the mapping
    of original -> hashed URLs so emitted HTML can be rewritten to match.
    """
    asset_map = {}
    for source in sorted(STATIC.rglob("*")):
        if source.is_dir() or source.name.startswith("."):
            continue
        rel = source.relative_to(STATIC)
        dest_rel = rel
        if source.suffix in (".css", ".js"):
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
            dest_rel = rel.with_name(f"{source.stem}.{digest}{source.suffix}")
            asset_map[f"/static/{rel.as_posix()}"] = f"/static/{dest_rel.as_posix()}"
        dest = DIST / "static" / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    print(f"copied static/ -> dist/static/ ({len(asset_map)} hashed assets)")
    return asset_map


def sitemap_xml(entries):
    urls = []
    for url, lastmod in entries:
        entry = f"  <url>\n    <loc>{escape(url)}</loc>\n"
        if lastmod:
            entry += f"    <lastmod>{lastmod}</lastmod>\n"
        urls.append(entry + "  </url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def rss_xml(articles, lang):
    S = LANGUAGES[lang]["strings"]
    items_xml = []
    for a in articles:
        url = f"{SITE_URL}{a['url']}"
        published = format_datetime(
            datetime(a["when"].year, a["when"].month, a["when"].day, tzinfo=timezone.utc)
        )
        items_xml.append(
            "    <item>\n"
            f"      <title>{escape(a['title'])}</title>\n"
            f"      <link>{url}</link>\n"
            f"      <guid>{url}</guid>\n"
            f"      <description>{escape(a['description'])}</description>\n"
            f"      <pubDate>{published}</pubDate>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(S['rss_feed_title'].format(site=SITE_NAME))}</title>\n"
        f"    <link>{SITE_URL}/articles/</link>\n"
        f"    <description>{escape(S['rss_feed_description'].format(site=SITE_NAME))}</description>\n"
        f'    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items_xml)
        + "\n  </channel>\n</rss>\n"
    )


# ---------------------------------------------------------------------------
# Search: build-time half of the site's own search engine. This emits
# search-index.json (inverted index + doc metadata); static/js/search.js
# fetches it and ranks matches with BM25 entirely client-side.
# ---------------------------------------------------------------------------

# Stop-words for both site languages (a Spanish version may land under /es/
# later, and Spanish words already appear in names/titles). Spanish entries
# are listed accent-stripped because tokenize() removes diacritics before
# this filter runs.
STOPWORDS = {
    # English
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "this", "to", "was", "were", "will", "with",
    # Spanish (accent-stripped)
    "al", "como", "con", "de", "del", "el", "en", "es", "esta", "la", "las",
    "lo", "los", "mas", "para", "pero", "por", "que", "se", "sin", "sobre",
    "su", "sus", "un", "una", "uno", "y", "ya",
}

TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")
TAG_STRIP_RE = re.compile(r"<[^>]+>")


def tokenize(text):
    """Lowercase, strip accents, split on non-alphanumerics, drop stop-words,
    and crudely singularize (trailing 's', so 'motors' matches 'motor' —
    a real English stemmer would mangle the Spanish that shows up here).

    MUST stay in step with tokenize() in static/js/search.js, or queries
    won't match the index. Stop-words are the one exception: the client
    skips that filter because a stop-word query term simply isn't in the
    index and scores nothing.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    tokens = []
    for token in TOKEN_SPLIT_RE.split(stripped):
        if not token or token in STOPWORDS:
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


def build_search_index(items_by_section):
    """Inverted index over projects and articles: term -> {docId: freq},
    plus per-doc metadata and token counts (BM25 needs document lengths).
    Title and tag tokens are repeated so matches there outrank body prose.

    Also carries the tag vocabulary actually in use, which powers the
    empty-query "browse by tag" view in the search dropdown, and per-doc
    tags for client-side tag filtering later.
    """
    docs, index = [], {}
    disciplines, tech_in_use = set(), set()
    for section, items in items_by_section.items():
        for item in items:
            body_text = html.unescape(TAG_STRIP_RE.sub(" ", item["body"]))
            tokens = (
                tokenize(item["title"]) * 3
                + tokenize(" ".join(item["tech"] + [item["discipline"]])) * 2
                + tokenize(body_text)
            )
            doc_id = len(docs)
            disciplines.add(item["discipline"])
            tech_in_use.update(item["tech"])
            docs.append({
                "title": item["title"],
                "url": item["url"],
                "section": section,
                "excerpt": item["description"],
                "tags": [item["discipline"]] + item["tech"],
                "date": item["date"],
                "len": len(tokens),
            })
            for token in tokens:
                postings = index.setdefault(token, {})
                postings[doc_id] = postings.get(doc_id, 0) + 1
    return {
        "docs": docs,
        "index": index,
        "tags": {"discipline": sorted(disciplines), "tech": sorted(tech_in_use)},
    }


INTERNAL_LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')


def check_internal_links(written):
    """Every root-relative href/src in the generated HTML must resolve to a
    real file in dist/. External URLs, mailto:, and fragments are ignored.
    """
    errors = []
    for rel_path, html in written.items():
        for target in INTERNAL_LINK_RE.findall(html):
            if not target.startswith("/") or target.startswith("//"):
                continue
            path = target.split("#", 1)[0].split("?", 1)[0].lstrip("/")
            if path == "" or path.endswith("/"):
                path += "index.html"
            resolved = DIST / path
            if not (resolved.is_file() or (resolved / "index.html").is_file()):
                errors.append(f"{rel_path}: {target}")
    if errors:
        fail("broken internal link(s):\n  " + "\n  ".join(sorted(errors)))


def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    vocab = load_taxonomies()
    lang = DEFAULT_LANG  # per-language output trees land in the next i18n step
    S = LANGUAGES[lang]["strings"]
    base = localize((TEMPLATES / "base.html").read_text(encoding="utf-8"), lang)
    # The header carries the search box, so the partial slots in here once
    # rather than on every page render.
    header = localize(render(
        (TEMPLATES / "partials" / "header.html").read_text(encoding="utf-8"),
        {"search": (TEMPLATES / "partials" / "search.html").read_text(encoding="utf-8")},
    ), lang)
    footer = localize((TEMPLATES / "partials" / "footer.html").read_text(encoding="utf-8"), lang)
    card_template = (TEMPLATES / "partials" / "card.html").read_text(encoding="utf-8")

    # Static goes first so every page can be rewritten to the hashed names.
    asset_map = copy_static()

    written = {}          # dist-relative path -> final HTML, for the link check
    sitemap_entries = []  # (absolute URL, lastmod or None)

    def page_url(rel_path):
        # foo/index.html is served at foo/ — keep URLs directory-style.
        if rel_path == "index.html":
            return f"{SITE_URL}/"
        if rel_path.endswith("/index.html"):
            return f"{SITE_URL}/{rel_path[:-len('index.html')]}"
        return f"{SITE_URL}/{rel_path}"

    def emit(rel_path, *, title, description, content, lastmod=None):
        html = render(base, {
            "title": title,
            "description": description,
            "canonical_url": page_url(rel_path),
            "og_image": f"{SITE_URL}/static/images/og-default.png",
            "lang": lang,
            "header": header,
            "content": content,
            "footer": footer,
        })
        for plain, hashed in asset_map.items():
            html = html.replace(plain, hashed)
        # A leftover {{s.…}} means a template references a string key the
        # registry doesn't define — fail rather than ship it to visitors.
        if "{{s." in html:
            fail(f"{rel_path}: unresolved chrome-string placeholder")
        out = DIST / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        written[rel_path] = html
        if rel_path != "404.html":  # error page has no place in a sitemap
            sitemap_entries.append((page_url(rel_path), lastmod))
        print(f"wrote dist/{rel_path}")

    # ---- fixed pages ----------------------------------------------------
    for slug, source in bundle_sources(CONTENT / "pages"):
        fields, body = parse_frontmatter(source.read_text(encoding="utf-8"))
        if "slug" in fields:
            fail(f"{source}: drop the 'slug' field — the bundle folder name is the slug")
        missing = [f for f in REQUIRED_PAGE_FIELDS if not fields.get(f)]
        if missing:
            fail(f"{source} is missing frontmatter field(s): {', '.join(missing)}")
        emit(f"{slug}.html",
             title=fields["title"], description=fields["description"], content=body)

    # ---- projects and articles -------------------------------------------
    items = {section: load_items(section, vocab) for section in SECTIONS}
    for section, template_name in SECTIONS.items():
        type_template = localize(
            (TEMPLATES / template_name).read_text(encoding="utf-8"), lang)
        for item in items[section]:
            content = render(type_template, {
                "title": item["title"],
                "date": item["date"],
                "date_display": display_date(item["when"], lang),
                "discipline": item["discipline"],
                "discipline_url": f"/discipline/{item['discipline']}/",
                "tech_list": tag_list_html(item["tech"]),
                "content": item["body"],
            })
            emit(f"{section}/{item['slug']}/index.html",
                 title=f"{item['title']} — {SITE_NAME}",
                 description=item["description"],
                 content=content, lastmod=item["date"])

        index_title, lede = S[f"{section}_title"], S[f"{section}_lede"]
        emit(f"{section}/index.html",
             title=f"{index_title} — {SITE_NAME}",
             description=lede,
             content=listing_body(index_title, lede,
                                  items[section], card_template, lang))

    # ---- tag pages (only for tags actually in use) -------------------------
    everything = sorted(items["projects"] + items["articles"],
                        key=lambda i: i["when"], reverse=True)

    for d in sorted({i["discipline"] for i in everything}):
        tagged = [i for i in everything if i["discipline"] == d]
        lede = S["discipline_lede"].format(tag=d)
        emit(f"discipline/{d}/index.html",
             title=f"{d.capitalize()} — {SITE_NAME}", description=lede,
             content=listing_body(d.capitalize(), lede, tagged,
                                  card_template, lang))

    for t in sorted({t for i in everything for t in i["tech"]}):
        tagged = [i for i in everything if t in i["tech"]]
        lede = S["tech_lede"].format(tag=t)
        emit(f"tags/{t}/index.html",
             title=f"{t} — {SITE_NAME}", description=lede,
             content=listing_body(S["tech_heading"].format(tag=t), lede,
                                  tagged, card_template, lang))

    # ---- search page --------------------------------------------------------
    # The chips are real links to the tag pages, so /search/ works without
    # JS; <search-page> (static/js/search.js) upgrades them to filter
    # toggles with AND/OR matching and keeps the URL shareable.
    def tag_chips(kind, tags, prefix):
        return "\n".join(
            f'      <li><a class="tag" data-kind="{kind}" data-tag="{t}"'
            f' href="{prefix}{t}/">{t}</a></li>'
            for t in tags)

    search_content = f"""<h1>{S["search_title"]}</h1>
<p class="lede">{S["search_lede"]}</p>
<search-page>
  <input type="search" placeholder="{S["search_placeholder"]}" aria-label="{S["search_aria"]}" autocomplete="off">
  <div class="search-filters">
    <span class="search-browse-label">{S["search_disciplines"]}</span>
    <ul class="search-tag-group">
{tag_chips("discipline", sorted({i["discipline"] for i in everything}), "/discipline/")}
    </ul>
    <span class="search-browse-label">{S["search_tech"]}</span>
    <ul class="search-tag-group">
{tag_chips("tech", sorted({t for i in everything for t in i["tech"]}), "/tags/")}
    </ul>
    <fieldset class="search-mode">
      <legend>{S["search_mode_legend"]}</legend>
      <label><input type="radio" name="tag-mode" value="or" checked> {S["search_mode_or"]}</label>
      <label><input type="radio" name="tag-mode" value="and"> {S["search_mode_and"]}</label>
    </fieldset>
  </div>
  <p class="search-count" aria-live="polite"></p>
  <ul class="search-results search-results--page"></ul>
</search-page>"""
    emit("search/index.html",
         title=f"{S['search_title']} — {SITE_NAME}",
         description=S["search_description"],
         content=search_content)

    # ---- search index -------------------------------------------------------
    (DIST / "search-index.json").write_text(
        json.dumps(build_search_index(items), separators=(",", ":")),
        encoding="utf-8")
    print("wrote dist/search-index.json")

    # ---- sitemap and RSS ----------------------------------------------------
    (DIST / "sitemap.xml").write_text(sitemap_xml(sitemap_entries), encoding="utf-8")
    print("wrote dist/sitemap.xml")
    (DIST / "feed.xml").write_text(rss_xml(items["articles"], lang), encoding="utf-8")
    print("wrote dist/feed.xml")

    check_internal_links(written)
    print(f"OK: {len(written)} pages, all internal links resolve")


if __name__ == "__main__":
    build()
