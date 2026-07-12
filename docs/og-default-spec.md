# og-default.png — Specification

The fallback **social share image** for the site. "OG" = Open Graph, the metadata
standard that social platforms and messaging apps (LinkedIn, WhatsApp, Slack, X,
Facebook…) read when someone pastes a link. The platform fetches the image named
in the `og:image` meta tag and shows it as the big preview card next to the
title and description.

Any page that doesn't declare its own `og:image` falls back to this file, so it
is effectively the site's first impression when shared — especially on LinkedIn.

**Target location:** `static/images/og-default.png`
(deployed as `https://johanalejandrolopezarias.com/images/og-default.png`)

---

## Technical requirements

| Parameter    | Value                                                        |
|--------------|--------------------------------------------------------------|
| Dimensions   | **1200 × 630 px** (the de-facto standard on every platform) |
| Aspect ratio | **1.91:1** — rectangular, landscape. Never square           |
| Format       | **PNG** (crisp text/flat graphics). JPG only for photos. No SVG/WebP — some crawlers ignore them |
| File size    | **< ~300 KB** (crawlers time out on slow fetches; a flat-color PNG easily stays < 100 KB) |
| Color space  | sRGB, 8-bit                                                  |
| Transparency | **None** — some platforms render transparent areas as black; use a solid background |

## Required meta tags in `base.html`

```html
<meta property="og:image" content="https://johanalejandrolopezarias.com/images/og-default.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Johan Alejandro López Arias — Mechatronics Engineer">
<meta name="twitter:card" content="summary_large_image">
```

Notes:
- The `og:image` URL must be **absolute** (full `https://…`) — crawlers don't
  resolve relative paths.
- `og:image:width`/`height` let platforms lay out the card before downloading.
- Without `twitter:card = summary_large_image`, X shows a tiny square thumbnail.

## Safe area / cropping rules

- Platforms crop differently (WhatsApp trims to exactly 1.91:1; some mobile
  layouts shave the edges). Keep all text and critical elements inside a
  **centered ~1120 × 560 px safe zone** — i.e. ≥ 40 px margin on all sides
  (60–80 px looks better anyway).
- Assume the image may be displayed as small as **~500 px wide** (mobile feed).
  Anything not legible at that size doesn't belong in the image.

## Design guidance

- **Content:** name + role is the core message —
  *"Johan Alejandro López Arias"* / *"Mechatronics Engineer · Robotics &
  Automation"*. Optionally the domain in small type. Nothing more; it's a
  business card, not a poster.
- **Text size:** ≥ ~48 px for the smallest text at full resolution; ~80–120 px
  for the name. Rule of thumb: zoom to 25% — if you can't read it, it's too
  small.
- **Contrast:** high (dark on light or light on dark), matching the site's
  design tokens so the card and the site feel like one thing. Aim for
  WCAG-level contrast (≥ 4.5:1) even though it's an image.
- **Typography:** same typeface family as the site if possible; one, max two
  weights.
- **Background:** flat color or very subtle gradient/pattern from the site
  palette. No busy imagery behind text. A low-contrast geometric motif nodding
  to robotics (grid, schematic lines) works well.
- **No screenshots** of the site — they read as noise at card size.
- **Design it as a template:** per-project OG images can come later (same
  background/layout, project title swapped in), so make the default a reusable
  layout, not a one-off.

## How to produce it

Any of:
1. Any image editor (GIMP, Figma, Inkscape…) at a 1200 × 630 canvas.
2. An HTML/CSS mockup using the site's design tokens, screenshotted at exactly
   1200 × 630.
3. A small Python script (e.g. Pillow) — build-time generation is allowed.

Then drop the file at `static/images/og-default.png` — the meta tag does the
rest.

## Verification after deploy

- LinkedIn Post Inspector: <https://www.linkedin.com/post-inspector/>
- Paste the URL into WhatsApp / Slack and check the preview card.
- Platforms **cache OG images aggressively** — after changing the image, use
  the inspector tools to force a re-scrape.
