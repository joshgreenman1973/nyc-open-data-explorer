#!/usr/bin/env python3
"""
Generate per-category JSON + RSS 2.0 feeds plus a master "all-new" feed.
Reads data/catalog.min.json (already built by fetch_catalog.py) and writes
to feeds/<slug>.json and feeds/<slug>.xml.
"""
import json
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "catalog.min.json"
FEEDS = ROOT / "feeds"
FEEDS.mkdir(exist_ok=True)
SITE_BASE = "https://joshgreenman1973.github.io/nyc-open-data-explorer"
DOMAIN = "data.cityofnewyork.us"
PER_FEED = 50


def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "all"


def parse_iso(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None


def xml_escape(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_rss(path, title, link, items):
    now = datetime.now(timezone.utc)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        f'<title>{xml_escape(title)}</title>',
        f'<link>{xml_escape(link)}</link>',
        f'<description>{xml_escape(title)} — automatically generated from data.cityofnewyork.us</description>',
        f'<lastBuildDate>{format_datetime(now)}</lastBuildDate>',
        '<language>en-us</language>',
    ]
    for it in items:
        pub = parse_iso(it.get("u")) or parse_iso(it.get("x")) or now
        url = f"https://{DOMAIN}/d/{it['i']}"
        desc = f"Category: {it.get('c','')}. Agency: {it.get('a','')}. Updated: {it.get('u','')[:10]}."
        parts.append("<item>")
        parts.append(f"<title>{xml_escape(it['n'])}</title>")
        parts.append(f"<link>{xml_escape(url)}</link>")
        parts.append(f"<guid isPermaLink=\"true\">{xml_escape(url)}</guid>")
        parts.append(f"<pubDate>{format_datetime(pub)}</pubDate>")
        parts.append(f"<description>{xml_escape(desc)}</description>")
        parts.append("</item>")
    parts.append("</channel></rss>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_json(path, title, items):
    out = {
        "title": title,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": [
            {"id": it["i"], "name": it["n"], "category": it["c"], "agency": it["a"],
             "updated": it.get("u", ""), "created": it.get("x", ""), "views": it.get("v", 0),
             "url": f"https://{DOMAIN}/d/{it['i']}"}
            for it in items
        ],
    }
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    data = json.loads(DATA.read_text())
    datasets = data["datasets"]
    cats = sorted({d["c"] for d in datasets})

    # Master feed: most recently updated across the whole catalog
    master = sorted(datasets, key=lambda d: d.get("u", ""), reverse=True)[:PER_FEED]
    write_rss(FEEDS / "all.xml", "NYC Open Data — Most recently updated",
              f"{SITE_BASE}/", master)
    write_json(FEEDS / "all.json", "NYC Open Data — Most recently updated", master)

    # Per-category — recently updated
    for cat in cats:
        slug = slugify(cat)
        in_cat = [d for d in datasets if d["c"] == cat]
        items = sorted(in_cat, key=lambda d: d.get("u", ""), reverse=True)[:PER_FEED]
        write_rss(FEEDS / f"{slug}.xml", f"NYC Open Data — {cat} (recently updated)",
                  f"{SITE_BASE}/#cat={cat}", items)
        write_json(FEEDS / f"{slug}.json", f"NYC Open Data — {cat} (recently updated)", items)

    # Master feed: newest datasets (by created date)
    new = sorted([d for d in datasets if d.get("x")], key=lambda d: d.get("x", ""), reverse=True)[:PER_FEED]
    write_rss(FEEDS / "new.xml", "NYC Open Data — Newest datasets",
              f"{SITE_BASE}/", new)
    write_json(FEEDS / "new.json", "NYC Open Data — Newest datasets", new)

    print(f"Wrote {len(cats) + 2} feeds (RSS + JSON each) to feeds/", file=sys.stderr)


if __name__ == "__main__":
    main()
