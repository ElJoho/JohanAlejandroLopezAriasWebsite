# Adding, renaming, or removing a tag

Step-by-step guide for changing the site's tag vocabulary. Companion to
[`adding-content.md`](adding-content.md) (which covers using tags on a page);
this one covers changing the vocabulary itself.

The one rule everything else follows from: **`docs/taxonomies.md` is the
single source of truth.** `build.py` validates every tag in every content
file against it and **fails the build** on anything it doesn't recognize.
So the order is always: taxonomy first, content second.

---

## Background: the two taxonomies (they have different rules)

| | `discipline` | `tech` |
|---|---|---|
| Per item | **exactly one** | zero or more |
| Vocabulary | controlled, deliberately small (currently 4) | grows freely |
| Answers | "what field is this work in?" | "what tools/technologies did it use?" |
| Tag page URL | `/discipline/<tag>/` | `/tags/<tag>/` |
| Adding one is… | **a rare, deliberate decision** — the whole point is that there are only a handful | routine — do it whenever a project genuinely uses something new |

If you're about to add a fifth discipline, stop and ask whether it's really a
discipline or just a tech tag. Almost everything is a tech tag.

## Step 1 — Check whether the tag (or a synonym) already exists

Open `docs/taxonomies.md` and read the list. The vocabulary only works if
each concept has exactly one name. Before adding, ask:

- **Is there already a synonym?** Don't add `additive-manufacturing` when
  `3d-printing` exists, or `rpi` when `raspberry-pi` exists. Use the
  existing tag.
- **Is it just a different form of an existing tag?** Plural, verb form,
  abbreviation — same tag.

If a synonym exists, you're done: use the existing name in your frontmatter.

## Step 2 — Pick the name (conventions are enforced by convention, not code)

The build checks that a tag *is in the file*, not that it's well-formed — so
the discipline here is yours. The conventions:

- **lowercase** — `opencv`, never `OpenCV`
- **hyphen-separated** — `raspberry-pi`, never `raspberry_pi` or `raspberrypi`
- **singular** — `article`, not `articles` (existing multi-word tags like
  `3d-printing` name the activity, which is fine)
- **no version numbers** — `plc`, not `plc-s7`; the exception is when the
  version *is* the identity of the thing (`ros2` is a different ecosystem
  from ROS 1, `cpp` is the language name)
- **no synonyms** of anything already in the list (Step 1)

The tag string becomes part of a URL (`/tags/<tag>/`), so stick to
`a–z`, `0–9`, and hyphens.

## Step 3 — Add it to `docs/taxonomies.md`

Add one bullet line under the correct heading:

```markdown
## tech — many per item, grows freely

- ros2
- moveit2
...
- esp32
- your-new-tag        ← add it like this
```

How the file is parsed (so you don't accidentally break it): `build.py`
reads it line by line — a line starting with `## ` opens a vocabulary named
by the **first word** after the `##` (so `## tech — many per item…` defines
`tech`), and every following line starting with `- ` adds one tag to it.
Anything else (prose, blank lines) is ignored. Practical consequences:

- The bullet must be exactly `- tagname` — `*` bullets or indented bullets
  are invisible to the parser.
- Don't add comments *on* a tag line (`- plc  # Siemens` would register a
  tag named `plc  # Siemens`).
- Keep the two `##` headings' first words as exactly `discipline` and
  `tech` — the build fails if either vocabulary comes out empty.

Alphabetical order isn't required, but keep the list tidy — it's a public
file in a repo reviewers read.

## Step 4 — Use the tag in content

In the frontmatter of any project or article:

```
discipline: automation
tech: opencv, python, your-new-tag
```

(`discipline` takes exactly one value; `tech` is comma-separated. See
[`adding-content.md`](adding-content.md) Step 2 for the full frontmatter
reference.)

## Step 5 — Rebuild

```
python3 build.py
```

(`python3`, not `python` — plain `python` isn't on this machine's PATH.)

Everything downstream of the taxonomy regenerates automatically — there is
no other file to touch:

- a tag page at `/tags/your-new-tag/` (or `/discipline/…/`), listing every
  item carrying the tag, newest first
- clickable chips for it on the detail page and on cards in every index
  where a tagged item appears
- an entry in the header search dropdown's "browse by tag" view
- a filter chip on `/search/` (both are built from tags *in use*, so the
  tag appears the moment content uses it)
- the search index: the tag's tokens are indexed at double weight for each
  tagged item, so searching the tag name finds those pages

Note the phrase **in use**: a tag that's in `taxonomies.md` but on zero
content files is valid but invisible — no page, no chips, no search entry.
That's by design; the taxonomy is the *allowed* list, the content decides
what exists.

## Step 6 — Verify locally

```
python3 -m http.server 8000 -d dist
```

At `http://localhost:8000`:

1. `/tags/your-new-tag/` exists and lists the right items.
2. The chip shows on the tagged item's page and card, and clicking it goes
   to the tag page.
3. Focus the header search box with an empty query — the new tag is in the
   browse list.
4. On `/search/`, the chip is present and toggling it filters correctly.
5. Typing the tag name in the search box surfaces the tagged items.

Then commit and push as usual (`docs/taxonomies.md` + the content file
together — pushing content that uses a tag without the taxonomy change will
fail the deploy build, by design).

---

## Renaming a tag

There's no aliasing — a rename is a coordinated edit:

1. In `docs/taxonomies.md`: replace the old name with the new one.
2. In **every content file that uses it**: update the frontmatter. Find them
   with: `grep -rl "old-tag" content/`
3. Rebuild. Two failure modes will catch a half-done rename: content still
   using the old name fails validation, and (if you got them all) the old
   tag page simply stops being generated.

⚠️ The old URL `/tags/old-tag/` **disappears**. Anyone who bookmarked or
linked it gets a 404. Before renaming a tag that's been live for a while,
decide whether that's acceptable — this is the strongest reason to get
names right the first time (Step 2).

## Removing a tag

1. Remove it from every content file first (`grep -rl "the-tag" content/`),
   or delete/retag the content.
2. Then remove the bullet from `docs/taxonomies.md`.

Order matters: if you remove it from the taxonomy while content still uses
it, the build fails (which is your safety net — it can't half-happen). If
you remove it from content but leave it in the taxonomy, nothing breaks; it
just sits there as an allowed-but-unused tag, and its page and chips vanish
from the built site.

## Adding a discipline (rare — read this first)

The four disciplines (`robotics`, `automation`, `manufacturing`, `writing`)
are fixed in the project brief (CLAUDE.md), which treats the discipline list
as a hard constraint: *exactly one per item, controlled, kept small*.
Mechanically, adding one works exactly like Steps 2–6 (bullet under
`## discipline` instead). But treat it as a real decision, not a routine
edit:

- Every item has exactly one discipline, so a new one must be clearly
  disjoint from the existing four — if items could plausibly go either way,
  it's fragmenting the taxonomy, not extending it.
- Ask first whether it's actually a `tech` tag; it almost always is.
- Update the brief (CLAUDE.md) in the same change so the two files don't
  disagree about what the controlled list is.
