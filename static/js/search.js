/* Client-side half of the site's own search engine. Two components share
 * this module:
 *
 *   <site-search>  — compact dropdown in the header: BM25 results while
 *                    typing, tag browser when the box is empty.
 *   <search-page>  — the /search/ page: full result list plus tag filter
 *                    toggles (AND/OR), state mirrored into the URL so
 *                    searches are shareable.
 *
 * build.py emits /search-index.json: an inverted index (term -> {docId:
 * freq}) plus doc metadata and token counts. It is fetched once, lazily —
 * on first focus for the header box, on connect for the search page.
 *
 * tokenize() MUST stay in step with tokenize() in build.py: same lowercase,
 * accent-strip, split, and singularize rules. The one deliberate difference
 * is stop-words: the build strips them, so a stop-word query term is simply
 * absent from the index and scores nothing — no client-side list needed.
 */

const K1 = 1.5; // BM25 term-frequency saturation
const B = 0.75; // BM25 length normalization
const MAX_DROPDOWN_RESULTS = 8;

let indexPromise;

/** One shared fetch of the index; header box and search page reuse it. */
function loadIndex() {
  indexPromise ??= fetch("/search-index.json")
    .then((res) => {
      if (!res.ok) throw new Error(res.status);
      return res.json();
    })
    .then((data) => {
      data.avgLen = data.docs.reduce((sum, d) => sum + d.len, 0) / data.docs.length;
      return data;
    });
  return indexPromise;
}

function tokenize(text) {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // strip combining accents, matching build.py
    .split(/[^a-z0-9]+/)
    .filter(Boolean)
    .map((t) =>
      t.length > 3 && t.endsWith("s") && !t.endsWith("ss") ? t.slice(0, -1) : t
    );
}

function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

/** BM25 over the query terms; returns all matching docs, best first. */
function bm25(data, query) {
  const { docs, index } = data;
  const scores = new Map();
  for (const term of new Set(tokenize(query))) {
    const postings = index[term];
    if (!postings) continue;
    const df = Object.keys(postings).length;
    const idf = Math.log(1 + (docs.length - df + 0.5) / (df + 0.5));
    for (const [id, tf] of Object.entries(postings)) {
      const norm = 1 - B + (B * docs[id].len) / data.avgLen;
      const score = (idf * tf * (K1 + 1)) / (tf + K1 * norm);
      scores.set(id, (scores.get(id) ?? 0) + score);
    }
  }
  return [...scores.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([id]) => docs[id]);
}

function resultItem(d) {
  return `
      <li>
        <a href="${d.url}">${escapeHtml(d.title)}</a>
        <span class="search-result-meta">${d.section}</span>
        <p>${escapeHtml(d.excerpt)}</p>
      </li>`;
}

/* ------------------------------------------------------------------ */
/* <site-search> — header dropdown                                     */
/* ------------------------------------------------------------------ */

class SiteSearch extends HTMLElement {
  connectedCallback() {
    this.input = this.querySelector("input");
    this.results = document.createElement("ul");
    this.results.className = "search-results";
    this.results.hidden = true;
    this.append(this.results);

    this.input.addEventListener("focus", () => this.load(), { once: true });
    this.input.addEventListener("focus", () => this.update());
    this.input.addEventListener("input", () => this.update());
    this.addEventListener("keydown", (e) => this.onKeydown(e));
    document.addEventListener("click", (e) => {
      if (!this.contains(e.target)) this.close();
    });
  }

  async load() {
    try {
      this.data = await loadIndex();
    } catch {
      return; // search quietly degrades to nothing if the fetch fails
    }
    this.update(); // catch up if the user typed while the index loaded
  }

  update() {
    if (!this.data) {
      this.close();
      return;
    }
    const query = this.input.value.trim();
    if (!query) {
      // Empty query: show the tag vocabulary so visitors who don't know
      // what to type can browse instead. Chips are plain links to the
      // build-time tag pages.
      this.renderBrowse();
      return;
    }
    const hits = bm25(this.data, query).slice(0, MAX_DROPDOWN_RESULTS);
    this.results.innerHTML = hits.length
      ? hits.map(resultItem).join("") +
        `<li class="search-more"><a href="/search/?q=${encodeURIComponent(query)}">All results &amp; filters →</a></li>`
      : '<li class="search-empty">No results. <a href="/search/">Browse everything →</a></li>';
    this.results.hidden = false;
  }

  renderBrowse() {
    const { tags } = this.data;
    const group = (label, list, urlFor) =>
      list.length
        ? `
      <li class="search-browse">
        <span class="search-browse-label">${label}</span>
        <ul class="search-tag-group">
          ${list
            .map((t) => `<li><a class="tag" href="${urlFor(t)}">${t}</a></li>`)
            .join("")}
        </ul>
      </li>`
        : "";
    this.results.innerHTML =
      group("Browse by discipline", tags.discipline, (t) => `/discipline/${t}/`) +
      group("Browse by tech", tags.tech, (t) => `/tags/${t}/`);
    this.results.hidden = false;
  }

  close() {
    this.results.hidden = true;
  }

  onKeydown(event) {
    if (event.key === "Escape") {
      this.close();
      this.input.focus();
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    if (this.results.hidden) return;
    event.preventDefault();

    const links = [...this.results.querySelectorAll("a")];
    if (!links.length) return;
    const pos = links.indexOf(document.activeElement);
    if (event.key === "ArrowDown") {
      (links[pos + 1] ?? links[0]).focus();
    } else if (pos > 0) {
      links[pos - 1].focus();
    } else {
      this.input.focus();
    }
  }
}

/* ------------------------------------------------------------------ */
/* <search-page> — the /search/ page                                   */
/* ------------------------------------------------------------------ */

class SearchPage extends HTMLElement {
  async connectedCallback() {
    this.input = this.querySelector('input[type="search"]');
    this.chips = [...this.querySelectorAll("a.tag[data-tag]")];
    this.count = this.querySelector(".search-count");
    this.results = this.querySelector(".search-results");
    this.modeRadios = [...this.querySelectorAll('input[name="tag-mode"]')];

    // The chips arrive from the build as links to the tag pages (the
    // no-JS fallback); upgrade them to filter toggles.
    for (const chip of this.chips) {
      chip.setAttribute("role", "button");
      chip.setAttribute("aria-pressed", "false");
      chip.addEventListener("click", (e) => {
        e.preventDefault();
        this.toggleChip(chip);
      });
    }
    this.input.addEventListener("input", () => this.update());
    for (const radio of this.modeRadios) {
      radio.addEventListener("change", () => this.update());
    }

    try {
      this.data = await loadIndex();
    } catch {
      this.count.textContent = "Search is unavailable right now.";
      return;
    }
    this.applyUrlParams();
    this.update();
  }

  toggleChip(chip) {
    const on = chip.classList.toggle("tag--active");
    chip.setAttribute("aria-pressed", String(on));
    this.update();
  }

  /** Restore state from a shared /search/?q=…&tags=…&mode=and URL. */
  applyUrlParams() {
    const params = new URLSearchParams(location.search);
    this.input.value = params.get("q") ?? "";
    const active = new Set((params.get("tags") ?? "").split(",").filter(Boolean));
    for (const chip of this.chips) {
      if (active.has(chip.dataset.tag)) {
        chip.classList.add("tag--active");
        chip.setAttribute("aria-pressed", "true");
      }
    }
    if (params.get("mode") === "and") {
      this.modeRadios.find((r) => r.value === "and").checked = true;
    }
  }

  update() {
    const query = this.input.value.trim();
    const active = this.chips
      .filter((c) => c.classList.contains("tag--active"))
      .map((c) => c.dataset.tag);
    const mode = this.modeRadios.find((r) => r.checked)?.value ?? "or";

    // Text matches ranked by BM25; with no query, everything newest-first.
    let hits = query
      ? bm25(this.data, query)
      : [...this.data.docs].sort((a, b) => (a.date < b.date ? 1 : -1));
    if (active.length) {
      hits = hits.filter((d) =>
        mode === "and"
          ? active.every((t) => d.tags.includes(t))
          : active.some((t) => d.tags.includes(t))
      );
    }

    this.count.textContent = `${hits.length} result${hits.length === 1 ? "" : "s"}`;
    this.results.innerHTML = hits.map(resultItem).join("");

    // Mirror the state into the URL so searches are shareable.
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (active.length) params.set("tags", active.join(","));
    if (mode === "and") params.set("mode", "and");
    const qs = params.toString();
    history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
  }
}

customElements.define("site-search", SiteSearch);
customElements.define("search-page", SearchPage);
