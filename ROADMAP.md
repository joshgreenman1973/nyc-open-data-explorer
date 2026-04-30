# NYC Open Data Explorer — v2 Roadmap

Goal: close the parity gap with the City portal on filtering, then pull decisively ahead on discovery and journalist usefulness. Ten improvements grouped into four shippable phases. Each phase is independently deployable.

---

## Phase 1 — Filter parity with the City portal

**Why first:** these are the features the City already has and journalists already expect. Without them we can't honestly claim "better than the city portal."

### 1. Agency filter (multi-select sidebar)
- Build step: aggregate agency counts in `fetch_catalog.py`; write `agencies` array (name, count, slug) into `catalog.min.json`. Normalize obvious duplicates ("Department of Finance" vs "Department of Finance (DOF)", curly-quote variants).
- Front end: collapsible left sidebar (or top filter bar on mobile). Show top 20 agencies with counts; "Show all" reveals the rest. Multi-select OR logic. Active selections render as removable chips next to the search bar.
- Files: `build/fetch_catalog.py`, `js/app.js`, `css/styles.css`, `index.html`.

### 2. View-type filter (Dataset / Map / File / Chart / External)
- Already have `type` in the catalog. Add a small pill row above results: All · Datasets · Maps · Files · Charts. Single-select. Cheap to ship.
- Files: `js/app.js`, `css/styles.css`.

### 3. Clickable tag chips on each card
- Already store tags. Render top 4 tag chips at the bottom of each card. Click → adds a tag filter (chip in the active-filters area, AND-combined with category/agency). Top tags also exposed in a "Browse tags" overlay.
- Files: `js/app.js`, `css/styles.css`.

### 9. Shareable URL state
- Encode current state into the URL hash: `#q=street+trees&cat=Environment&agency=Parks&type=map&age=year&sort=updated`. On load, parse hash → restore state. On any filter change, update hash without scroll jump (`history.replaceState`).
- Files: `js/app.js`.

**Phase 1 ships as one PR.** All four features touch the same filter UI; doing them together avoids three separate redesigns.

---

## Phase 2 — Discovery wins (where we beat the City portal)

### 4. "What's actually fresh" landing strip
- Above the category tiles, a horizontal carousel-style strip with two rows:
  - **Brand new this month** — datasets with `createdAt` in the last 30 days. NEW badge.
  - **Updated this week** — datasets with `data_updated_at` in the last 7 days, sorted by view count.
- Each card in the strip is a small horizontally-scrolling tile (name + agency + relative date). Clicking opens the dataset.
- Build step: precompute these two arrays in `catalog.min.json` so the front end doesn't have to scan 3,012 records on every load.
- Files: `build/fetch_catalog.py`, `index.html`, `js/app.js`, `css/styles.css`.

### 5. Plain-English category descriptions
- One-sentence description per category, written by hand (16 categories, takes 20 minutes — no API needed). Examples:
  - Public Safety: "NYPD complaint and arrest data, fire incidents, jail demographics, traffic crashes."
  - Maps & Geography: "Building footprints, district boundaries, aerial imagery, and base GIS layers."
- Show on hover (desktop) and on tap-to-expand (mobile) in each category tile. Also shown as the header on the category-detail view.
- Files: `js/categoryDescriptions.js` (new), `js/app.js`, `css/styles.css`.

### 6. "Most-used by journalists" curated layer
- A hand-picked list of ~30 datasets that newsrooms actually rely on (NYPD complaint, 311, motor vehicle collisions, DOB permits, ACRIS sales, restaurant inspections, evictions, school quality, MTA ridership, etc.). Stored in `data/journalist_picks.json` with: id, why-it-matters note, common-uses bullet, gotchas (one-liner).
- Surfaced two ways:
  1. A small "Journalist picks" pill that filters to just these 30.
  2. A gold star badge on these cards anywhere they appear, with the why-it-matters note shown on hover.
- Files: `data/journalist_picks.json` (new, hand-edited), `js/app.js`, `css/styles.css`, `methodology.html` (disclose the editorial layer).

---

## Phase 3 — Power features

### 7. Boolean / phrase / field search
- Extend the search parser before passing to Fuse.js:
  - Quoted phrases: `"motor vehicle"` → exact phrase match.
  - Field operators: `agency:nypd`, `tag:permits`, `type:map`, `updated:<30d`. Parsed into Fuse-equivalent filters.
  - Negation: `-tag:historical`.
  - AND default; OR with `|`.
- Show a small "Search tips" link below the box that opens a cheat-sheet popover.
- Files: `js/searchParser.js` (new), `js/app.js`.

### 8. Smart empty state
- When results = 0:
  - If query matches a tag with results in another filter, suggest "Try removing the [Public Safety] filter — 12 results match in other categories."
  - Suggest closest tag by Levenshtein distance ("Did you mean: `permits`?").
  - Show top 3 most-viewed datasets in the active category as a fallback.
- Files: `js/app.js`, `css/styles.css`.

---

## Phase 4 — Notification layer

### 10. Per-category JSON feeds + RSS
- Build step: emit `feeds/<category-slug>.json` (last 50 new + last 50 updated) and `feeds/<category-slug>.xml` (RSS 2.0) for each of the 16 categories, plus a master `feeds/all-new.xml`. Generated on every weekly rebuild.
- Add a small RSS icon next to each category header on the category-detail view that links to the feed.
- Files: `build/generate_feeds.py` (new), `feeds/*` (generated), `js/app.js`, `index.html`.

---

## Cross-cutting work

- **Methodology page updates** for each phase: agency normalization rules (Phase 1), curated journalist picks editorial process (Phase 2), search syntax reference (Phase 3), feed generation (Phase 4). Per the no-black-boxes rule.
- **README** update with new features and rebuild steps.
- **Mobile pass** after each phase — verify at 375px.
- **Accessibility pass** at end of Phase 2: keyboard navigation across tiles and filters, ARIA labels on filter chips, screen-reader text on freshness pills.

## Order of operations

1. Phase 1 (one PR, ~all four features land together — biggest UX leap, ~half a day of work).
2. Phase 2 (discovery layer, makes us clearly better than the City — about a day, includes hand-curating the 30 journalist picks).
3. Phase 3 (power-user polish — half a day).
4. Phase 4 (feeds — quarter day, pure build-script work).

After each phase: rebuild, push to `joshgreenman1973/nyc-open-data-explorer`, verify the live URL in your browser, confirm with you before moving to the next phase.

## Open question for Josh

Do you want me to run all four phases straight through and only check in at the end, or pause after each phase so you can sanity-check?
