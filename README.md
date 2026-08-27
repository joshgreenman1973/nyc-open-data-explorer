# New York City Open Data Explorer

A colorful, plain-language map of every dataset on the New York City Open Data portal. Browse 3,000+ datasets by category, search across them in plain English, and see at a glance what's been refreshed and what's stale.

Live: https://joshgreenman1973.github.io/nyc-open-data-explorer/

## What it does

- Pulls the full NYC Open Data catalog (~3,012 datasets, 12 categories) from Socrata's public Discovery API
- Renders the catalog as 12 color-coded category tiles, sized by dataset count
- Shows each dataset as a card with a plain-language summary, agency, and freshness pill
- Provides a fuzzy search across names, summaries, tags, and agencies — much more forgiving than the City portal's literal search
- Links every result back to the authoritative dataset on data.cityofnewyork.us
- **What changed** — diffs daily catalog snapshots to log datasets the City added, removed, renamed or re-described (`changes.html`, `feeds/changes.xml`)
- **Overdue flag** — compares each dataset's agency-declared update frequency with its actual last update
- **Column search** — `col:bbl` finds every dataset with a BBL field; column names are also fuzzy-searched
- **Preview drawer** — columns, live sample rows + row count, copy-API/CSV buttons, similar datasets, recent listing changes, without leaving the page
- **What people ask for** — the City's own log of public dataset requests (`requests.html`, plus a rail summary): what New Yorkers asked it to publish, what the agency answered, and the 558 requests sitting past the City's 60-day deadline
- Table/map twins collapsed into one card; stalled feeds flagged instead of shown as zero in the weekly cards

## Repo layout

```
nyc-open-data-explorer/
├── build/
│   ├── fetch_catalog.py        # Pulls the full catalog from the Socrata API (+ frequency, columns)
│   ├── changelog.py            # Diffs snapshots -> data/changelog.json (--backfill rebuilds from git history)
│   ├── generate_feeds.py       # Per-category RSS/JSON + feeds/changes.xml
│   ├── weekly_stats.py         # "Week in city data" cards, with stall detection
│   └── news_match.py           # Headlines -> datasets (Google News, Bing fallback)
├── data/
│   ├── catalog.json            # Full archive (descriptions, columns, all fields)
│   ├── catalog.min.json        # Search-optimized payload the front end loads
│   ├── changelog.json          # Catalog change events (front end + changes.html)
│   └── changelog_state.json    # Ids ever seen + pending removals (build state only)
├── css/styles.css
├── js/app.js                   # Render, search (Fuse.js), filter, sort, drawer
├── js/searchParser.js          # Operators: agency: tag: type: cat: col: freq: updated:
├── index.html
├── changes.html                # Full changelog page
├── requests.html               # Full public-request log
├── methodology.html
└── README.md
```

## Rebuild the catalog

```bash
python3 build/fetch_catalog.py
```

Pulls all ~3,014 datasets, writes both `catalog.json` and `catalog.min.json`. Takes about 60 seconds. Then `python3 build/changelog.py && python3 build/generate_feeds.py && python3 build/weekly_stats.py && python3 build/news_match.py && python3 build/helpdesk.py`. The GitHub Actions workflow in `.github/workflows/refresh.yml` runs all of this daily.

## Deploy

Static files only. GitHub Pages, Netlify, or any static host will work. There is no build step beyond the Python catalog fetch.

## Methodology

See [methodology.html](methodology.html) — covers the data source, plain-language summary process, freshness logic, search engine, refresh cadence, and known limitations.

## License

MIT for the code. The underlying data is published by the City of New York under the NYC Open Data terms of use.
