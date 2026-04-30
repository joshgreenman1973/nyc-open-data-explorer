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


_GIS_KEYWORDS = ("map", "gis", "aerial", "imagery", "ortho", "photogr", "tile", "boundary", "boundaries", "planimetric", "geograph", "shapefile", "district", "lion", "pluto", "lots")
_FINANCE_AGENCIES = ("Department of Finance", "Office of Management and Budget", "OMB", "Comptroller", "Independent Budget", "IBO", "Tax")
_FINANCE_KEYWORDS = ("budget", "spending", "expenditure", "revenue", "tax", "fiscal", "finance", "audit")
_PROCUREMENT_AGENCIES = ("Contract Services", "MOCS", "Citywide Administrative", "DCAS")
_PROCUREMENT_KEYWORDS = ("contract", "procurement", "vendor", "rfp", "bid", "purchas")
_ELECTIONS_AGENCIES = ("Campaign Finance", "CFB", "Conflicts of Interest", "COIB", "Board of Elections", "Voter", "Elections")
_ELECTIONS_KEYWORDS = ("election", "voter", "campaign", "ethics", "conflict of interest", "lobby")
_OPERATIONS_AGENCIES = ("Mayor's Office of Operations", "Mayor’s Office of Operations", "OPS", "311", "Records and Information")


def _hay(rec):
    parts = [rec.get("name", ""), rec.get("description", ""), " ".join(rec.get("tags", []) or []), rec.get("agency", "")]
    return " ".join(parts).lower()


def refine_government(rec):
    """Split the catch-all 'City Government' bucket into meaningful sub-buckets."""
    if rec["category"] != "City Government":
        return rec["category"]
    agency = rec.get("agency", "") or ""
    name = rec.get("name", "") or ""
    tags = rec.get("tags", []) or []
    hay = _hay(rec)
    tag_set = {t.lower() for t in tags}

    # Maps & GIS — strong tag signal
    if any(k in tag_set for k in ("gis", "map", "aerial", "imagery", "ortho", "boundary", "boundaries", "planimetric", "tile", "district", "districts")):
        return "Maps & Geography"
    if any(k in name.lower() for k in ("map of", "boundary", "boundaries", "shapefile", "aerial", "ortho", "pluto")):
        return "Maps & Geography"

    # Finance & budget
    if any(a in agency for a in _FINANCE_AGENCIES):
        return "Finance & Budget"
    if any(k in hay for k in _FINANCE_KEYWORDS) and "school" not in name.lower():
        return "Finance & Budget"

    # Procurement & contracts
    if any(a in agency for a in _PROCUREMENT_AGENCIES):
        return "Procurement & Contracts"
    if any(k in hay for k in _PROCUREMENT_KEYWORDS):
        return "Procurement & Contracts"

    # Elections & ethics
    if any(a in agency for a in _ELECTIONS_AGENCIES):
        return "Elections & Ethics"
    if any(k in hay for k in _ELECTIONS_KEYWORDS):
        return "Elections & Ethics"

    # Parks (mis-categorized in gov bucket)
    if "Parks" in agency:
        return "Recreation"

    # Operations & administrative
    if any(a in agency for a in _OPERATIONS_AGENCIES):
        return "Government Operations"

    return "Government Operations"


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
    # Refine the catch-all "City Government" bucket
    for r in records:
        r["category"] = refine_government(r)
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
