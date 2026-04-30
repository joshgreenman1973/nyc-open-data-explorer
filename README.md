# New York City Open Data Explorer

A colorful, plain-language map of every dataset on the New York City Open Data portal. Browse 3,000+ datasets by category, search across them in plain English, and see at a glance what's been refreshed and what's stale.

Live: _(URL added after deploy)_

## What it does

- Pulls the full NYC Open Data catalog (~3,012 datasets, 12 categories) from Socrata's public Discovery API
- Renders the catalog as 12 color-coded category tiles, sized by dataset count
- Shows each dataset as a card with a plain-language summary, agency, and freshness pill
- Provides a fuzzy search across names, summaries, tags, and agencies — much more forgiving than the City portal's literal search
- Links every result back to the authoritative dataset on data.cityofnewyork.us

## Repo layout

```
nyc-open-data-explorer/
├── build/
│   └── fetch_catalog.py        # Pulls the full catalog from the Socrata API
├── data/
│   ├── catalog.json            # Full archive (descriptions, all fields)
│   └── catalog.min.json        # Search-optimized payload the front end loads
├── css/styles.css
├── js/app.js                   # Render, search (Fuse.js), filter, sort
├── index.html
├── methodology.html
└── README.md
```

## Rebuild the catalog

```bash
python3 build/fetch_catalog.py
```

Pulls all ~3,012 datasets, writes both `catalog.json` and `catalog.min.json`. Takes about 60 seconds.

## Deploy

Static files only. GitHub Pages, Netlify, or any static host will work. There is no build step beyond the Python catalog fetch.

## Methodology

See [methodology.html](methodology.html) — covers the data source, plain-language summary process, freshness logic, search engine, refresh cadence, and known limitations.

## License

MIT for the code. The underlying data is published by the City of New York under the NYC Open Data terms of use.
