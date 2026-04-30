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
from collections import Counter
from datetime import datetime, timezone, timedelta
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

    if any(k in tag_set for k in ("gis", "map", "aerial", "imagery", "ortho", "boundary", "boundaries", "planimetric", "tile", "district", "districts")):
        return "Maps & Geography"
    if any(k in name.lower() for k in ("map of", "boundary", "boundaries", "shapefile", "aerial", "ortho", "pluto")):
        return "Maps & Geography"
    if any(a in agency for a in _FINANCE_AGENCIES):
        return "Finance & Budget"
    if any(k in hay for k in _FINANCE_KEYWORDS) and "school" not in name.lower():
        return "Finance & Budget"
    if any(a in agency for a in _PROCUREMENT_AGENCIES):
        return "Procurement & Contracts"
    if any(k in hay for k in _PROCUREMENT_KEYWORDS):
        return "Procurement & Contracts"
    if any(a in agency for a in _ELECTIONS_AGENCIES):
        return "Elections & Ethics"
    if any(k in hay for k in _ELECTIONS_KEYWORDS):
        return "Elections & Ethics"
    if "Parks" in agency:
        return "Recreation"
    if any(a in agency for a in _OPERATIONS_AGENCIES):
        return "Government Operations"
    return "Government Operations"


# ---------- Agency normalization ----------

_paren_acronym_re = re.compile(r"\s*\([A-Z][A-Z0-9 &/\-]+\)\s*$")


def normalize_agency(raw):
    """Return a (canonical_name, slug) pair. Folds curly apostrophes,
    strips trailing acronym in parens, lowercases for grouping."""
    if not raw:
        return "", ""
    s = raw.replace("’", "'").replace("‘", "'")
    s = s.replace("&", "and")
    s = _ws_re.sub(" ", s).strip()
    # fold to a key for grouping
    key = _paren_acronym_re.sub("", s).strip().lower()
    return s, key


def to_record(item):
    r = item.get("resource", {})
    c = item.get("classification", {})
    cat = c.get("domain_category") or "Uncategorized"
    tags = c.get("domain_tags") or c.get("tags") or []
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
    for r in records:
        r["category"] = refine_government(r)

    # Agency normalization: pick the most common original spelling per key
    raw_by_key = {}
    for r in records:
        _, key = normalize_agency(r["agency"])
        if key:
            raw_by_key.setdefault(key, Counter())[r["agency"]] += 1
    canonical_for_key = {k: cnt.most_common(1)[0][0] for k, cnt in raw_by_key.items()}
    for r in records:
        _, key = normalize_agency(r["agency"])
        r["agency_key"] = key
        if key:
            r["agency"] = canonical_for_key[key]
        if not r["agency"]:
            r["agency"] = "Other / unspecified"
            r["agency_key"] = "other"

    # de-dupe by id
    seen = set()
    unique = []
    for r in records:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        unique.append(r)

    # Category counts
    by_cat = Counter(r["category"] for r in unique)

    # Agency counts (using canonical names)
    by_agency = Counter(r["agency"] for r in unique)
    agencies = sorted(
        [{"name": k, "key": normalize_agency(k)[1] or "other", "count": v} for k, v in by_agency.items()],
        key=lambda x: -x["count"],
    )

    # Type counts
    by_type = Counter(r["type"] for r in unique)

    # ---------- Fresh-strip precompute ----------
    # "New" uses a sliding window: try last 30 days, fall back to last 90, then to
    # "newest 12 in the catalog" so the strip is never empty. "Updated this week"
    # always uses the strict 7-day window — it's the most actionable signal.
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    def parse_iso(s):
        try:
            return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        except Exception:
            return None

    by_created = sorted(
        [(parse_iso(r.get("created")), r) for r in unique if parse_iso(r.get("created"))],
        key=lambda x: x[0], reverse=True,
    )
    new_label = "Brand new this month"
    new_this_month = [pair for pair in by_created if (now - pair[0]).days <= 30]
    if len(new_this_month) < 6:
        new_this_month = [pair for pair in by_created if (now - pair[0]).days <= 90]
        new_label = "Recently added (last 90 days)"
    if len(new_this_month) < 6:
        new_this_month = by_created[:20]
        new_label = "Most recently added to the catalog"

    updated_this_week = []
    for r in unique:
        udt = parse_iso(r.get("updated"))
        if udt and udt >= week_ago:
            updated_this_week.append((udt, r))
    updated_this_week.sort(key=lambda x: -x[1].get("views", 0))

    def to_strip(r):
        return {"i": r["id"], "n": r["name"], "c": r["category"], "a": r["agency"],
                "u": r["updated"], "x": r.get("created", ""), "v": r.get("views", 0)}

    fresh = {
        "new_label": new_label,
        "new_this_month": [to_strip(r) for _, r in new_this_month[:20]],
        "updated_this_week": [to_strip(r) for _, r in updated_this_week[:20]],
    }

    out = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "domain": DOMAIN,
        "count": len(unique),
        "categories": sorted(
            [{"name": k, "count": v} for k, v in by_cat.items()],
            key=lambda x: -x["count"],
        ),
        "agencies": agencies,
        "types": sorted([{"name": k, "count": v} for k, v in by_type.items()], key=lambda x: -x["count"]),
        "fresh": fresh,
        "datasets": unique,
    }

    (DATA_DIR / "catalog.json").write_text(json.dumps(out, ensure_ascii=False))
    min_records = [
        {
            "i": r["id"],
            "n": r["name"],
            "s": r["summary"],
            "c": r["category"],
            "a": r["agency"],
            "ak": r["agency_key"],
            "t": r["type"],
            "g": r["tags"],
            "u": r["updated"],
            "x": r.get("created", ""),
            "v": r["views"],
            "d": r["downloads"],
        }
        for r in unique
    ]
    min_out = {
        "fetched_at": out["fetched_at"],
        "count": out["count"],
        "categories": out["categories"],
        "agencies": agencies,
        "types": out["types"],
        "fresh": fresh,
        "datasets": min_records,
    }
    (DATA_DIR / "catalog.min.json").write_text(json.dumps(min_out, ensure_ascii=False, separators=(",", ":")))
    print(f"Wrote {out['count']} datasets across {len(out['categories'])} categories", file=sys.stderr)
    print(f"  Agencies: {len(agencies)}  Types: {len(out['types'])}", file=sys.stderr)
    print(f"  New this month: {len(fresh['new_this_month'])}  Updated this week: {len(fresh['updated_this_week'])}", file=sys.stderr)
    for c in out["categories"]:
        print(f"  {c['name']}: {c['count']}", file=sys.stderr)


if __name__ == "__main__":
    main()
