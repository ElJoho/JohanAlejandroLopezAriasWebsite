#!/usr/bin/env python3
"""Static site generator. Reads content/, wraps it in templates/, writes dist/.

Content types (all hand-written HTML fragments with `---` frontmatter):
  content/pages/     -> dist/<slug>.html        fixed pages
  content/projects/  -> dist/projects/<slug>/   portfolio items
  content/articles/  -> dist/articles/<slug>/   writing

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

REQUIRED_PAGE_FIELDS = ("title", "description", "slug")
REQUIRED_ITEM_FIELDS = REQUIRED_PAGE_FIELDS + ("date", "discipline", "tech")

# The two sections that share the item pipeline. `lede` doubles as the
# index page's intro paragraph and its meta description.
SECTIONS = {
    "projects": {
        "template": "project.html",
        "index_title": "Projects",
        "lede": "Things I've built across robotics, automation, and manufacturing.",
    },
    "articles": {
        "template": "article.html",
        "index_title": "Articles",
        "lede": "Occasional writing about engineering, tooling, and this site itself.",
    },
}


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


def display_date(d):
    return f"{d.day} {d.strftime('%B')} {d.year}"


def tag_list_html(tech):
    """A list of tech tags rendered as chips linking to their tag pages."""
    if not tech:
        return ""
    links = "\n".join(
        f'      <li><a class="tag" href="/tags/{t}/">{t}</a></li>' for t in tech
    )
    return f'<ul class="tag-list">\n{links}\n    </ul>'


def load_items(section, vocab):
    """Read one section's content files, validating frontmatter as we go."""
    items = []
    for source in sorted((CONTENT / section).glob("*.html")):
        fields, body = parse_frontmatter(source.read_text(encoding="utf-8"))

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
            "tech": tech,
            "when": when,
            "url": f"/{section}/{fields['slug']}/",
            "body": body,
        })

    # Duplicate slugs would silently overwrite each other's output.
    slugs = [i["slug"] for i in items]
    for slug in {s for s in slugs if slugs.count(s) > 1}:
        fail(f"duplicate slug '{slug}' in content/{section}/")

    items.sort(key=lambda i: i["when"], reverse=True)
    return items


def card_html(card_template, item):
    return render(card_template, {
        "url": item["url"],
        "title": item["title"],
        "date": item["date"],
        "date_display": display_date(item["when"]),
        "discipline": item["discipline"],
        "description": item["description"],
        "tech_list": tag_list_html(item["tech"]),
    })


def listing_body(heading, lede, items, card_template):
    """Shared body for index pages and tag pages: heading + card list."""
    if items:
        cards = "\n".join(card_html(card_template, i) for i in items)
        cards_block = f'<ul class="card-grid">\n{cards}\n</ul>'
    else:
        cards_block = "<p>Nothing here yet — check back soon.</p>"
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


def rss_xml(articles):
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
        f"    <title>{escape(SITE_NAME)} — Articles</title>\n"
        f"    <link>{SITE_URL}/articles/</link>\n"
        f"    <description>Articles by {escape(SITE_NAME)}.</description>\n"
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
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    # The header carries the search box, so the partial slots in here once
    # rather than on every page render.
    header = render(
        (TEMPLATES / "partials" / "header.html").read_text(encoding="utf-8"),
        {"search": (TEMPLATES / "partials" / "search.html").read_text(encoding="utf-8")},
    )
    footer = (TEMPLATES / "partials" / "footer.html").read_text(encoding="utf-8")
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
            "header": header,
            "content": content,
            "footer": footer,
        })
        for plain, hashed in asset_map.items():
            html = html.replace(plain, hashed)
        out = DIST / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        written[rel_path] = html
        if rel_path != "404.html":  # error page has no place in a sitemap
            sitemap_entries.append((page_url(rel_path), lastmod))
        print(f"wrote dist/{rel_path}")

    # ---- fixed pages ----------------------------------------------------
    for source in sorted((CONTENT / "pages").glob("*.html")):
        fields, body = parse_frontmatter(source.read_text(encoding="utf-8"))
        missing = [f for f in REQUIRED_PAGE_FIELDS if not fields.get(f)]
        if missing:
            fail(f"{source} is missing frontmatter field(s): {', '.join(missing)}")
        emit(f"{fields['slug']}.html",
             title=fields["title"], description=fields["description"], content=body)

    # ---- projects and articles -------------------------------------------
    items = {section: load_items(section, vocab) for section in SECTIONS}
    for section, cfg in SECTIONS.items():
        type_template = (TEMPLATES / cfg["template"]).read_text(encoding="utf-8")
        for item in items[section]:
            content = render(type_template, {
                "title": item["title"],
                "date": item["date"],
                "date_display": display_date(item["when"]),
                "discipline": item["discipline"],
                "discipline_url": f"/discipline/{item['discipline']}/",
                "tech_list": tag_list_html(item["tech"]),
                "content": item["body"],
            })
            emit(f"{section}/{item['slug']}/index.html",
                 title=f"{item['title']} — {SITE_NAME}",
                 description=item["description"],
                 content=content, lastmod=item["date"])

        emit(f"{section}/index.html",
             title=f"{cfg['index_title']} — {SITE_NAME}",
             description=cfg["lede"],
             content=listing_body(cfg["index_title"], cfg["lede"],
                                  items[section], card_template))

    # ---- tag pages (only for tags actually in use) -------------------------
    everything = sorted(items["projects"] + items["articles"],
                        key=lambda i: i["when"], reverse=True)

    for d in sorted({i["discipline"] for i in everything}):
        tagged = [i for i in everything if i["discipline"] == d]
        lede = f"Everything filed under the {d} discipline."
        emit(f"discipline/{d}/index.html",
             title=f"{d.capitalize()} — {SITE_NAME}", description=lede,
             content=listing_body(d.capitalize(), lede, tagged, card_template))

    for t in sorted({t for i in everything for t in i["tech"]}):
        tagged = [i for i in everything if t in i["tech"]]
        lede = f"Projects and articles tagged {t}."
        emit(f"tags/{t}/index.html",
             title=f"{t} — {SITE_NAME}", description=lede,
             content=listing_body(f"Tagged “{t}”", lede, tagged, card_template))

    # ---- search page --------------------------------------------------------
    # The chips are real links to the tag pages, so /search/ works without
    # JS; <search-page> (static/js/search.js) upgrades them to filter
    # toggles with AND/OR matching and keeps the URL shareable.
    def tag_chips(kind, tags, prefix):
        return "\n".join(
            f'      <li><a class="tag" data-kind="{kind}" data-tag="{t}"'
            f' href="{prefix}{t}/">{t}</a></li>'
            for t in tags)

    search_content = f"""<h1>Search</h1>
<p class="lede">Find projects and articles by text, by tag, or both.</p>
<search-page>
  <input type="search" placeholder="Search…" aria-label="Search projects and articles" autocomplete="off">
  <div class="search-filters">
    <span class="search-browse-label">Disciplines</span>
    <ul class="search-tag-group">
{tag_chips("discipline", sorted({i["discipline"] for i in everything}), "/discipline/")}
    </ul>
    <span class="search-browse-label">Tech</span>
    <ul class="search-tag-group">
{tag_chips("tech", sorted({t for i in everything for t in i["tech"]}), "/tags/")}
    </ul>
    <fieldset class="search-mode">
      <legend>Tag matching</legend>
      <label><input type="radio" name="tag-mode" value="or" checked> any selected tag</label>
      <label><input type="radio" name="tag-mode" value="and"> all selected tags</label>
    </fieldset>
  </div>
  <p class="search-count" aria-live="polite"></p>
  <ul class="search-results search-results--page"></ul>
</search-page>"""
    emit("search/index.html",
         title=f"Search — {SITE_NAME}",
         description="Search projects and articles by text or filter by tag.",
         content=search_content)

    # ---- search index -------------------------------------------------------
    (DIST / "search-index.json").write_text(
        json.dumps(build_search_index(items), separators=(",", ":")),
        encoding="utf-8")
    print("wrote dist/search-index.json")

    # ---- sitemap and RSS ----------------------------------------------------
    (DIST / "sitemap.xml").write_text(sitemap_xml(sitemap_entries), encoding="utf-8")
    print("wrote dist/sitemap.xml")
    (DIST / "feed.xml").write_text(rss_xml(items["articles"]), encoding="utf-8")
    print("wrote dist/feed.xml")

    check_internal_links(written)
    print(f"OK: {len(written)} pages, all internal links resolve")


if __name__ == "__main__":
    build()
