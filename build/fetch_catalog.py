#!/usr/bin/env python3
"""
Fetch the full NYC Open Data catalog via Socrata's discovery API and write
both a full archive (catalog.json) and a search-optimized minified index
(catalog.min.json) for the front end.
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

DOMAIN = "data.cityofnewyork.us"
API = "https://api.us.socrata.com/api/catalog/v1"
PAGE_SIZE = 100

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def fetch_page(offset):
    qs = urllib.parse.urlencode({
        "domains": DOMAIN,
        "limit": PAGE_SIZE,
        "offset": offset,
    })
    url = f"{API}?{qs}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def fetch_all():
    first = fetch_page(0)
    total = first.get("resultSetSize", 0)
    print(f"Total datasets: {total}", file=sys.stderr)
    results = list(first["results"])
    offset = PAGE_SIZE
    while offset < total:
        print(f"  fetching offset {offset}/{total}", file=sys.stderr)
        page = fetch_page(offset)
        results.extend(page["results"])
        offset += PAGE_SIZE
        time.sleep(0.2)
    return results


_html_re = re.compile(r"<[^>]+>")
_ws_re = re.compile(r"\s+")


def clean_text(s):
    if not s:
        return ""
    s = _html_re.sub(" ", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    s = _ws_re.sub(" ", s).strip()
    return s


def first_sentence(s, max_chars=240):
    """Return a plain-English first sentence, capped at max_chars."""
    s = clean_text(s)
    if not s:
        return ""
    # Split on sentence ends but keep the punctuation
    m = re.search(r"(.+?[\.!?])(\s|$)", s)
    sent = m.group(1) if m else s
    if len(sent) > max_chars:
        sent = sent[:max_chars].rsplit(" ", 1)[0] + "..."
    return sent


def to_record(item):
    r = item.get("resource", {})
    c = item.get("classification", {})
    cat = c.get("domain_category") or "Uncategorized"
    tags = c.get("domain_tags") or c.get("tags") or []
    agency = item.get("metadata", {}).get("domain", "") or ""
    attribution = clean_text(r.get("attribution") or "")
    desc_raw = r.get("description") or ""
    desc_clean = clean_text(desc_raw)
    summary = first_sentence(desc_raw)
    type_ = r.get("type", "dataset")
    rid = r.get("id") or r.get("resource_name") or ""
    name = clean_text(r.get("name") or "")
    return {
        "id": rid,
        "name": name,
        "summary": summary,
        "description": desc_clean,
        "category": cat,
        "agency": attribution,
        "type": type_,
        "tags": tags[:8],
        "updated": r.get("data_updated_at") or r.get("updatedAt") or "",
        "created": r.get("createdAt") or "",
        "views": int(r.get("page_views", {}).get("page_views_total") or 0) if isinstance(r.get("page_views"), dict) else 0,
        "downloads": int(r.get("download_count") or 0),
        "url": f"https://{DOMAIN}/d/{rid}",
    }


def main():
    raw = fetch_all()
    records = [to_record(it) for it in raw]
    records = [r for r in records if r["id"] and r["name"]]
    # de-dupe by id, preserving first occurrence
    seen = set()
    unique = []
    for r in records:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        unique.append(r)
    # Sort categories deterministically: high-count first
    by_cat = {}
    for r in unique:
        by_cat.setdefault(r["category"], 0)
        by_cat[r["category"]] += 1

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domain": DOMAIN,
        "count": len(unique),
        "categories": sorted(
            [{"name": k, "count": v} for k, v in by_cat.items()],
            key=lambda x: -x["count"],
        ),
        "datasets": unique,
    }

    (DATA_DIR / "catalog.json").write_text(json.dumps(out, ensure_ascii=False))
    # min: drop full description, keep summary
    min_records = [
        {
            "i": r["id"],
            "n": r["name"],
            "s": r["summary"],
            "c": r["category"],
            "a": r["agency"],
            "t": r["type"],
            "g": r["tags"],
            "u": r["updated"],
            "v": r["views"],
            "d": r["downloads"],
        }
        for r in unique
    ]
    min_out = {
        "fetched_at": out["fetched_at"],
        "count": out["count"],
        "categories": out["categories"],
        "datasets": min_records,
    }
    (DATA_DIR / "catalog.min.json").write_text(json.dumps(min_out, ensure_ascii=False, separators=(",", ":")))
    print(f"Wrote {out['count']} datasets across {len(out['categories'])} categories", file=sys.stderr)
    for c in out["categories"]:
        print(f"  {c['name']}: {c['count']}", file=sys.stderr)


if __name__ == "__main__":
    main()
