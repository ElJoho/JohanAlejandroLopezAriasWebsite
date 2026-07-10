#!/usr/bin/env python3
"""Static site generator. Reads content/, wraps it in templates/, writes dist/."""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CONTENT_PAGES = ROOT / "content" / "pages"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
DIST = ROOT / "dist"

# TODO: replace with the real domain once purchased (Phase 0, step 1).
SITE_URL = "https://example.com"

REQUIRED_FIELDS = ("title", "description", "slug")


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


def render_page(fields, body, header, footer):
    template = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    return (
        template.replace("{{title}}", fields["title"])
        .replace("{{description}}", fields["description"])
        .replace("{{canonical_url}}", f"{SITE_URL}/{fields['slug']}.html")
        .replace("{{og_image}}", f"{SITE_URL}/static/images/og-default.png")
        .replace("{{header}}", header)
        .replace("{{content}}", body)
        .replace("{{footer}}", footer)
    )


def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    header = (TEMPLATES / "partials" / "header.html").read_text(encoding="utf-8")
    footer = (TEMPLATES / "partials" / "footer.html").read_text(encoding="utf-8")

    for source in sorted(CONTENT_PAGES.glob("*.html")):
        fields, body = parse_frontmatter(source.read_text(encoding="utf-8"))

        missing = [f for f in REQUIRED_FIELDS if not fields.get(f)]
        if missing:
            sys.exit(f"build failed: {source} is missing frontmatter field(s): {', '.join(missing)}")

        page_html = render_page(fields, body, header, footer)
        out_path = DIST / f"{fields['slug']}.html"
        out_path.write_text(page_html, encoding="utf-8")
        print(f"wrote {out_path.relative_to(ROOT)}")

    shutil.copytree(STATIC, DIST / "static")
    print(f"copied {STATIC.relative_to(ROOT)} -> {(DIST / 'static').relative_to(ROOT)}")

    # TODO (Phase 2, step 15): tag validation against docs/taxonomies.md,
    # broken internal link checking, and content-hash cache-busting on
    # CSS/JS filenames all belong here once projects/articles exist.


if __name__ == "__main__":
    build()
