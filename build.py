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
            # i18n chrome
            "lang_switcher_aria": "Language",
            "fallback_banner": "This content isn't available in English yet, so it's shown in its original language.",
        },
    },
    "es": {
        "name": "Español",
        "months": ("enero", "febrero", "marzo", "abril", "mayo", "junio",
                   "julio", "agosto", "septiembre", "octubre", "noviembre",
                   "diciembre"),
        "date_fmt": "{day} de {month} de {year}",
        "strings": {
            # header / nav
            "nav_aria": "Principal",
            "nav_home": "Inicio",
            "nav_projects": "Proyectos",
            "nav_articles": "Artículos",
            "nav_about": "Sobre mí",
            "nav_contact": "Contacto",
            "nav_search": "Buscar",
            "search_placeholder": "Buscar…",
            "search_aria": "Buscar proyectos y artículos",
            # footer
            "footer_copyright": "&copy; 2026 Johan Alejandro López Arias.",
            # detail pages
            "filed_under": "archivado en",
            # section index pages (the lede doubles as the meta description)
            "projects_title": "Proyectos",
            "projects_lede": "Cosas que he construido en robótica, automatización y manufactura.",
            "articles_title": "Artículos",
            "articles_lede": "Escritura ocasional sobre ingeniería, herramientas y este mismo sitio.",
            "empty_listing": "Aún no hay nada aquí — vuelve pronto.",
            # tag pages
            "discipline_lede": "Todo lo archivado en la disciplina {tag}.",
            "tech_heading": "Etiqueta “{tag}”",
            "tech_lede": "Proyectos y artículos con la etiqueta {tag}.",
            # search page
            "search_title": "Buscar",
            "search_lede": "Encuentra proyectos y artículos por texto, por etiqueta o ambos.",
            "search_description": "Busca proyectos y artículos por texto o filtra por etiqueta.",
            "search_disciplines": "Disciplinas",
            "search_tech": "Tecnologías",
            "search_mode_legend": "Coincidencia de etiquetas",
            "search_mode_or": "cualquier etiqueta seleccionada",
            "search_mode_and": "todas las etiquetas seleccionadas",
            # feeds
            "rss_link_title": "Artículos — RSS",
            "rss_feed_title": "{site} — Artículos",
            "rss_feed_description": "Artículos de {site}.",
            # i18n chrome
            "lang_switcher_aria": "Idioma",
            "fallback_banner": "Este contenido aún no está disponible en español, así que se muestra en su idioma original.",
        },
    },
    "de": {
        "name": "Deutsch",
        "months": ("Januar", "Februar", "März", "April", "Mai", "Juni",
                   "Juli", "August", "September", "Oktober", "November",
                   "Dezember"),
        "date_fmt": "{day}. {month} {year}",
        "strings": {
            # header / nav
            "nav_aria": "Hauptnavigation",
            "nav_home": "Start",
            "nav_projects": "Projekte",
            "nav_articles": "Artikel",
            "nav_about": "Über mich",
            "nav_contact": "Kontakt",
            "nav_search": "Suche",
            "search_placeholder": "Suchen…",
            "search_aria": "Projekte und Artikel durchsuchen",
            # footer
            "footer_copyright": "&copy; 2026 Johan Alejandro López Arias.",
            # detail pages
            "filed_under": "abgelegt unter",
            # section index pages (the lede doubles as the meta description)
            "projects_title": "Projekte",
            "projects_lede": "Dinge, die ich in Robotik, Automatisierung und Fertigung gebaut habe.",
            "articles_title": "Artikel",
            "articles_lede": "Gelegentliche Texte über Technik, Werkzeuge und diese Website selbst.",
            "empty_listing": "Hier gibt es noch nichts — schau bald wieder vorbei.",
            # tag pages
            "discipline_lede": "Alles aus der Disziplin {tag}.",
            "tech_heading": "Schlagwort „{tag}“",
            "tech_lede": "Projekte und Artikel mit dem Schlagwort {tag}.",
            # search page
            "search_title": "Suche",
            "search_lede": "Finde Projekte und Artikel über Text, Schlagwörter oder beides.",
            "search_description": "Durchsuche Projekte und Artikel oder filtere nach Schlagwort.",
            "search_disciplines": "Disziplinen",
            "search_tech": "Technologien",
            "search_mode_legend": "Schlagwort-Logik",
            "search_mode_or": "beliebiges gewähltes Schlagwort",
            "search_mode_and": "alle gewählten Schlagwörter",
            # feeds
            "rss_link_title": "Artikel — RSS",
            "rss_feed_title": "{site} — Artikel",
            "rss_feed_description": "Artikel von {site}.",
            # i18n chrome
            "lang_switcher_aria": "Sprache",
            "fallback_banner": "Dieser Inhalt ist noch nicht auf Deutsch verfügbar und wird in der Originalsprache angezeigt.",
        },
    },
}

DEFAULT_LANG = next(code for code, cfg in LANGUAGES.items() if cfg.get("default"))


def lang_root(lang):
    """A language tree's URL root: '/' for the default language, '/es/'
    etc. for the rest (docs/i18n-design.md URL scheme)."""
    return "/" if lang == DEFAULT_LANG else f"/{lang}/"

REQUIRED_PAGE_FIELDS = ("title", "description")
REQUIRED_ITEM_FIELDS = REQUIRED_PAGE_FIELDS + ("date", "discipline", "tech")

# Shared metadata lives only in en.html so it can never drift between
# translations; a translation file redefining it is a build error.
FORBIDDEN_TRANSLATION_FIELDS = ("date", "discipline", "tech")

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


def tag_list_html(tech, root):
    """A list of tech tags rendered as chips linking to their tag pages
    in the current language's tree."""
    if not tech:
        return ""
    links = "\n".join(
        f'      <li><a class="tag" href="{root}tags/{t}/">{t}</a></li>' for t in tech
    )
    return f'<ul class="tag-list">\n{links}\n    </ul>'


def switcher_html(variants, lang):
    """The header language switcher: EN | ES | DE, each a plain link to
    this same page in that language — which always exists, because pages
    without a translation are generated as fallbacks."""
    links = "".join(
        f'<li><a href="{variants[code]}" lang="{code}" hreflang="{code}"'
        + (' aria-current="page"' if code == lang else "")
        + f">{code.upper()}</a></li>"
        for code in LANGUAGES)
    aria = LANGUAGES[lang]["strings"]["lang_switcher_aria"]
    return f'<nav class="lang-switcher" aria-label="{aria}"><ul>{links}</ul></nav>'


def fallback_body(body, lang):
    """Body for a page not translated into `lang`: a banner in the
    visitor's language on top, the original body underneath keeping its
    own lang attribute for accessibility."""
    banner = LANGUAGES[lang]["strings"]["fallback_banner"]
    return (f'<p class="fallback-banner">{banner}</p>\n'
            f'<div lang="{DEFAULT_LANG}">\n{body}\n</div>')


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


def load_bundle(bundle):
    """Read every <lang>.html in a bundle -> {lang: fields + "body"}.

    The filename must be a registry code. Translations carry only the
    localized fields (title, description, body); everything else belongs
    to en.html alone.
    """
    translations = {}
    for source in sorted(bundle.glob("*.html")):
        code = source.stem
        if code not in LANGUAGES:
            fail(f"{source}: '{code}.html' is not a language in the registry")
        fields, body = parse_frontmatter(source.read_text(encoding="utf-8"))
        if "slug" in fields:
            fail(f"{source}: drop the 'slug' field — the bundle folder name is the slug")
        if code != DEFAULT_LANG:
            banned = [f for f in FORBIDDEN_TRANSLATION_FIELDS if f in fields]
            if banned:
                fail(f"{source}: {', '.join(banned)} belong(s) only in en.html")
        missing = [f for f in REQUIRED_PAGE_FIELDS if not fields.get(f)]
        if missing:
            fail(f"{source}: missing frontmatter field(s): {', '.join(missing)}")
        translations[code] = {**fields, "body": body}
    return translations


def bundle_assets(bundle):
    """A bundle's co-located asset files: everything in it, recursively,
    except the top-level <lang>.html translations and dotfiles."""
    return sorted(
        p for p in bundle.rglob("*")
        if p.is_file() and not p.name.startswith(".")
        and not (p.parent == bundle and p.suffix == ".html"))


def copy_bundle_assets(bundle, dest_dir):
    """Copy a bundle's assets into one language's output folder. Every
    language gets a full copy so asset paths are identical in all trees
    (duplicated bytes in dist/ only — accepted at current scale)."""
    for asset in bundle_assets(bundle):
        dest = dest_dir / asset.relative_to(bundle)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, dest)


def load_pages():
    """Read the fixed-page bundles. Their output is a flat file (about.html),
    where a bundle asset's relative path would not resolve — so fixed pages
    may not carry assets; media belongs in projects/articles or static/."""
    pages = []
    for slug, source in bundle_sources(CONTENT / "pages"):
        if bundle_assets(source.parent):
            fail(f"{source.parent}: fixed-page bundles can't hold assets"
                 " (their output is a flat .html file)")
        pages.append({"slug": slug, "i18n": load_bundle(source.parent)})
    return pages


def load_items(section, vocab):
    """Read one section's content bundles, validating frontmatter as we go.

    Shared metadata (date, discipline, tech) is read from en.html only.
    The top-level title/description/body stay the English ones (the search
    index reads those for now); translations live under item["i18n"].
    """
    items = []
    for slug, source in bundle_sources(CONTENT / section):
        i18n = load_bundle(source.parent)
        fields, body = i18n[DEFAULT_LANG], i18n[DEFAULT_LANG]["body"]

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
            "section": section,
            "tech": tech,
            "when": when,
            "url": f"/{section}/{slug}/",
            "body": body,
            "i18n": i18n,
            "bundle": source.parent,
        })

    items.sort(key=lambda i: i["when"], reverse=True)
    return items


def card_html(card_template, item, lang, root):
    """One index card. Untranslated items show their original title and
    description plus a small language badge — the fallback-listing policy
    (docs/i18n-design.md): every language's index lists everything."""
    txt = item["i18n"].get(lang) or item["i18n"][DEFAULT_LANG]
    badge = ("" if lang in item["i18n"]
             else f' <span class="lang-badge">{DEFAULT_LANG.upper()}</span>')
    return render(card_template, {
        "url": f"{root}{item['section']}/{item['slug']}/",
        "title": txt["title"],
        "date": item["date"],
        "date_display": display_date(item["when"], lang),
        "discipline": item["discipline"],
        "description": txt["description"],
        "tech_list": tag_list_html(item["tech"], root),
        "lang_badge": badge,
    })


def listing_body(heading, lede, items, card_template, lang, root):
    """Shared body for index pages and tag pages: heading + card list."""
    if items:
        cards = "\n".join(card_html(card_template, i, lang, root) for i in items)
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
    """entries: (absolute URL, lastmod or None, {lang: absolute URL}).

    Only genuine translations get here (fallback pages are excluded at
    emit time); each URL carries its hreflang set plus x-default when the
    page exists in more than one language (docs/i18n-design.md SEO rules).
    """
    urls = []
    for url, lastmod, alternates in entries:
        entry = f"  <url>\n    <loc>{escape(url)}</loc>\n"
        if lastmod:
            entry += f"    <lastmod>{lastmod}</lastmod>\n"
        if len(alternates) > 1:
            for code, href in sorted(alternates.items()):
                entry += ('    <xhtml:link rel="alternate"'
                          f' hreflang="{code}" href="{escape(href)}"/>\n')
            entry += ('    <xhtml:link rel="alternate" hreflang="x-default"'
                      f' href="{escape(alternates[DEFAULT_LANG])}"/>\n')
        urls.append(entry + "  </url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def rss_xml(articles, lang):
    """One feed per language, holding only that language's genuine
    translations — the caller filters."""
    S = LANGUAGES[lang]["strings"]
    root = lang_root(lang)
    items_xml = []
    for a in articles:
        txt = a["i18n"][lang]
        url = f"{SITE_URL}{root}articles/{a['slug']}/"
        published = format_datetime(
            datetime(a["when"].year, a["when"].month, a["when"].day, tzinfo=timezone.utc)
        )
        items_xml.append(
            "    <item>\n"
            f"      <title>{escape(txt['title'])}</title>\n"
            f"      <link>{url}</link>\n"
            f"      <guid>{url}</guid>\n"
            f"      <description>{escape(txt['description'])}</description>\n"
            f"      <pubDate>{published}</pubDate>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(S['rss_feed_title'].format(site=SITE_NAME))}</title>\n"
        f"    <link>{SITE_URL}{root}articles/</link>\n"
        f"    <description>{escape(S['rss_feed_description'].format(site=SITE_NAME))}</description>\n"
        f'    <atom:link href="{SITE_URL}{root}feed.xml" rel="self" type="application/rss+xml"/>\n'
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
    base_t = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    # The header carries the search box, so the partial slots in here once
    # rather than on every page render.
    header_t = render(
        (TEMPLATES / "partials" / "header.html").read_text(encoding="utf-8"),
        {"search": (TEMPLATES / "partials" / "search.html").read_text(encoding="utf-8")},
    )
    footer_t = (TEMPLATES / "partials" / "footer.html").read_text(encoding="utf-8")
    card_template = (TEMPLATES / "partials" / "card.html").read_text(encoding="utf-8")
    type_templates_t = {
        section: (TEMPLATES / name).read_text(encoding="utf-8")
        for section, name in SECTIONS.items()
    }

    # Static goes first so every page can be rewritten to the hashed names.
    asset_map = copy_static()

    # Content loads once; the language loop below only renders it.
    items = {section: load_items(section, vocab) for section in SECTIONS}
    pages = load_pages()
    everything = sorted(items["projects"] + items["articles"],
                        key=lambda i: i["when"], reverse=True)
    disciplines = sorted({i["discipline"] for i in everything})
    tech_tags = sorted({t for i in everything for t in i["tech"]})

    written = {}          # dist-relative path -> final HTML, for the link check
    sitemap_entries = []  # (absolute URL, lastmod or None, {lang: absolute URL})

    def page_url(rel_path):
        # foo/index.html is served at foo/ — keep URLs directory-style.
        if rel_path.endswith("index.html"):
            rel_path = rel_path[: -len("index.html")]
        return f"{SITE_URL}/{rel_path}"

    # ---- one full page tree per language (docs/i18n-design.md) -----------
    for lang in LANGUAGES:
        root = lang_root(lang)
        prefix = root.lstrip("/")  # "" for the default language at the site root
        S = LANGUAGES[lang]["strings"]
        base = localize(base_t, lang)
        header = localize(render(header_t, {"root": root}), lang)
        footer = localize(footer_t, lang)

        def emit(rel_path, *, title, description, content, variants,
                 genuine, original=None, lastmod=None):
            """Write one page of this language's tree.

            variants: {lang: root-relative URL} of this page in every
            language — feeds the switcher. genuine: languages with a real
            translation — feeds hreflang (only emitted when there is more
            than one, plus x-default -> English). original: root-relative
            URL of the source-language page when this page is a fallback;
            it then gets canonical -> original + noindex and stays out of
            the sitemap (docs/i18n-design.md SEO rules).
            """
            url = page_url(rel_path)
            if original is None:
                alternates = {c: f"{SITE_URL}{variants[c]}" for c in genuine}
                head_lines = ""
                if len(alternates) > 1:
                    head_lines = "\n".join(
                        f'  <link rel="alternate" hreflang="{c}" href="{u}">'
                        for c, u in sorted(alternates.items()))
                    head_lines += ('\n  <link rel="alternate" hreflang="x-default"'
                                   f' href="{alternates[DEFAULT_LANG]}">')
                canonical = url
            else:
                head_lines = '  <meta name="robots" content="noindex">'
                canonical = f"{SITE_URL}{original}"
            html = render(base, {
                "title": title,
                "description": description,
                "canonical_url": canonical,
                "alternates": head_lines,
                "og_image": f"{SITE_URL}/static/images/og-default.png",
                "lang": lang,
                "feed_url": f"{root}feed.xml",
                "header": header.replace("{{switcher}}",
                                         switcher_html(variants, lang)),
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
            # Sitemap: genuine translations only; the 404 page has no place
            # there in any language.
            if original is None and not rel_path.endswith("404.html"):
                sitemap_entries.append((url, lastmod, alternates))
            print(f"wrote dist/{rel_path}")

        # ---- fixed pages --------------------------------------------------
        for page in pages:
            txt = page["i18n"].get(lang) or page["i18n"][DEFAULT_LANG]
            variants = {c: f"{lang_root(c)}{page['slug']}.html" for c in LANGUAGES}
            body, original = txt["body"], None
            if lang not in page["i18n"]:
                body = fallback_body(body, lang)
                original = variants[DEFAULT_LANG]
            emit(f"{prefix}{page['slug']}.html",
                 title=txt["title"], description=txt["description"],
                 content=body, variants=variants,
                 genuine=set(page["i18n"]), original=original)

        # ---- projects and articles ----------------------------------------
        for section, template_raw in type_templates_t.items():
            type_template = localize(template_raw, lang)
            for item in items[section]:
                txt = item["i18n"].get(lang) or item["i18n"][DEFAULT_LANG]
                variants = {c: f"{lang_root(c)}{section}/{item['slug']}/"
                            for c in LANGUAGES}
                body, original = txt["body"], None
                if lang not in item["i18n"]:
                    body = fallback_body(body, lang)
                    original = variants[DEFAULT_LANG]
                content = render(type_template, {
                    "title": txt["title"],
                    "date": item["date"],
                    "date_display": display_date(item["when"], lang),
                    "discipline": item["discipline"],
                    "discipline_url": f"{root}discipline/{item['discipline']}/",
                    "tech_list": tag_list_html(item["tech"], root),
                    "content": body,
                })
                copy_bundle_assets(item["bundle"],
                                   DIST / f"{prefix}{section}" / item["slug"])
                emit(f"{prefix}{section}/{item['slug']}/index.html",
                     title=f"{txt['title']} — {SITE_NAME}",
                     description=txt["description"],
                     content=content, variants=variants,
                     genuine=set(item["i18n"]), original=original,
                     lastmod=item["date"])

            index_title, lede = S[f"{section}_title"], S[f"{section}_lede"]
            emit(f"{prefix}{section}/index.html",
                 title=f"{index_title} — {SITE_NAME}",
                 description=lede,
                 content=listing_body(index_title, lede, items[section],
                                      card_template, lang, root),
                 variants={c: f"{lang_root(c)}{section}/" for c in LANGUAGES},
                 genuine=set(LANGUAGES))

        # ---- tag pages (only for tags actually in use) ----------------------
        for d in disciplines:
            tagged = [i for i in everything if i["discipline"] == d]
            lede = S["discipline_lede"].format(tag=d)
            emit(f"{prefix}discipline/{d}/index.html",
                 title=f"{d.capitalize()} — {SITE_NAME}", description=lede,
                 content=listing_body(d.capitalize(), lede, tagged,
                                      card_template, lang, root),
                 variants={c: f"{lang_root(c)}discipline/{d}/" for c in LANGUAGES},
                 genuine=set(LANGUAGES))

        for t in tech_tags:
            tagged = [i for i in everything if t in i["tech"]]
            lede = S["tech_lede"].format(tag=t)
            emit(f"{prefix}tags/{t}/index.html",
                 title=f"{t} — {SITE_NAME}", description=lede,
                 content=listing_body(S["tech_heading"].format(tag=t), lede,
                                      tagged, card_template, lang, root),
                 variants={c: f"{lang_root(c)}tags/{t}/" for c in LANGUAGES},
                 genuine=set(LANGUAGES))

        # ---- search page ----------------------------------------------------
        # The chips are real links to this language's tag pages, so /search/
        # works without JS; <search-page> (static/js/search.js) upgrades them
        # to filter toggles with AND/OR matching and keeps the URL shareable.
        def tag_chips(kind, tags, url_prefix):
            return "\n".join(
                f'      <li><a class="tag" data-kind="{kind}" data-tag="{t}"'
                f' href="{url_prefix}{t}/">{t}</a></li>'
                for t in tags)

        search_content = f"""<h1>{S["search_title"]}</h1>
<p class="lede">{S["search_lede"]}</p>
<search-page>
  <input type="search" placeholder="{S["search_placeholder"]}" aria-label="{S["search_aria"]}" autocomplete="off">
  <div class="search-filters">
    <span class="search-browse-label">{S["search_disciplines"]}</span>
    <ul class="search-tag-group">
{tag_chips("discipline", disciplines, f"{root}discipline/")}
    </ul>
    <span class="search-browse-label">{S["search_tech"]}</span>
    <ul class="search-tag-group">
{tag_chips("tech", tech_tags, f"{root}tags/")}
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
        emit(f"{prefix}search/index.html",
             title=f"{S['search_title']} — {SITE_NAME}",
             description=S["search_description"],
             content=search_content,
             variants={c: f"{lang_root(c)}search/" for c in LANGUAGES},
             genuine=set(LANGUAGES))

        # ---- RSS: one feed per language, genuine translations only ---------
        lang_articles = [a for a in items["articles"] if lang in a["i18n"]]
        (DIST / f"{prefix}feed.xml").write_text(rss_xml(lang_articles, lang),
                                                encoding="utf-8")
        print(f"wrote dist/{prefix}feed.xml")

    # ---- search index -------------------------------------------------------
    # Still a single English index; per-language indexes (and the matching
    # search.js changes) are the next i18n step.
    (DIST / "search-index.json").write_text(
        json.dumps(build_search_index(items), separators=(",", ":")),
        encoding="utf-8")
    print("wrote dist/search-index.json")

    # ---- sitemap (genuine translations only, with hreflang sets) -----------
    (DIST / "sitemap.xml").write_text(sitemap_xml(sitemap_entries), encoding="utf-8")
    print("wrote dist/sitemap.xml")

    check_internal_links(written)
    print(f"OK: {len(written)} pages, all internal links resolve")


if __name__ == "__main__":
    build()
