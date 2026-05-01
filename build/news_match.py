#!/usr/bin/env python3
"""
Pull recent NYC headlines from Google News, classify each by topic using a
curated keyword dictionary, and pair each topical headline with the relevant
dataset on data.cityofnewyork.us. Writes data/news_matches.json for the rail.

The curated mapping is the editorial layer — like journalist_picks, it's
hand-tuned, not a clever NLP guess. That's why matches are obvious rather than
surprising. Add or refine topics in the TOPICS list below.

Failures are soft: if Google News is unreachable, the file is rewritten
with an empty `matches` array and no errors propagate.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "catalog.min.json"
OUT = ROOT / "data" / "news_matches.json"

NEWS_QUERIES = [
    'q=%22New+York+City%22&hl=en-US&gl=US&ceid=US:en',
    'q=%22NYC%22+OR+%22Manhattan%22+OR+%22Brooklyn%22+OR+%22Queens%22+OR+%22Bronx%22&hl=en-US&gl=US&ceid=US:en',
]
NEWS_BASE = "https://news.google.com/rss/search?"

# Curated topic mapping: keywords (case-insensitive substring or word match)
# → dataset to surface. Order matters: earlier topics win on ties.
# Each `keywords` mixes single words (matched as whole words) and short phrases
# (matched as substrings). Phrases must contain a space or punctuation.
TOPICS = [
    {
        "keywords": ["shooting", "shootings", "gun violence", "gunfire", "shot dead", "shot and killed"],
        "topic": "Gun violence",
        "dataset_id": "833y-fsy8",
    },
    {
        "keywords": ["motor vehicle", "car crash", "vehicle crash", "crash kills", "fatal crash", "fatally struck", "struck by bus", "struck and killed", "pedestrian struck", "pedestrian killed", "cyclist killed", "bicyclist killed", "hit-and-run", "hit and run"],
        "topic": "Traffic crashes",
        "dataset_id": "h9gi-nx95",
    },
    {
        "keywords": ["school bus", "school buses"],
        "topic": "School-bus transportation",
        "dataset_id": "r2j4-rc64",
    },
    {
        "keywords": ["domestic violence", "domestic abuse", "intimate partner"],
        "topic": "Domestic violence services",
        "dataset_id": "7t9i-jsfp",
    },
    {
        "keywords": ["e-scooter", "e scooter", "electric scooter", "lime scooter", "lime bike", "bike share", "citi bike"],
        "topic": "Shared e-scooter and bike infrastructure",
        "dataset_id": "hjz2-y62k",
    },
    {
        "keywords": ["pre-k", "pre k", "pre kindergarten", "free childcare", "child care", "universal pre"],
        "topic": "Pre-K and child care",
        "dataset_id": "kiyv-ks3f",
    },
    {
        "keywords": ["hate crime", "hate crimes"],
        "topic": "Hate crimes",
        "dataset_id": "bqiq-cu78",
    },
    {
        "keywords": ["use of force", "police misconduct", "ccrb"],
        "topic": "Police use of force / civilian complaints",
        "dataset_id": "f4tj-796d",
    },
    {
        "keywords": ["arrest", "arrests", "arrested", "police arrested"],
        "topic": "NYPD arrests",
        "dataset_id": "8h9b-rp9u",
    },
    {
        "keywords": ["robbery", "burglary", "felony", "assault", "stabbing", "stabbed", "stabs", "stab", "homicide", "murder", "murdered", "killed in"],
        "topic": "Reported crime",
        "dataset_id": "qgea-i56i",
    },
    {
        "keywords": ["311 complaint", "311 complaints", "noise complaint", "noise complaints", "trash complaint"],
        "topic": "311 complaints",
        "dataset_id": "erm2-nwe9",
    },
    {
        "keywords": ["eviction", "evictions", "evicted", "tenant evicted"],
        "topic": "NYC evictions",
        "dataset_id": "6z8x-wfk4",
    },
    {
        "keywords": ["restaurant inspection", "restaurant inspections", "food safety", "letter grade", "doh"],
        "topic": "Restaurant inspections",
        "dataset_id": "43nn-pn8j",
    },
    {
        "keywords": ["construction permit", "building permit", "construction project", "high-rise", "skyscraper"],
        "topic": "Construction permits",
        "dataset_id": "rbx6-tga4",
    },
    {
        "keywords": ["affordable housing", "housing crisis", "new housing units"],
        "topic": "Affordable housing",
        "dataset_id": "hg8x-zxpr",
    },
    {
        "keywords": ["housing maintenance", "housing violation", "housing violations", "bad landlord", "landlord violations", "hpd"],
        "topic": "Housing maintenance violations",
        "dataset_id": "wvxf-dwi5",
    },
    {
        "keywords": ["heat", "no heat", "heat complaint", "heat complaints", "hot water"],
        "topic": "Heat / hot-water complaints",
        "dataset_id": "erm2-nwe9",
    },
    {
        "keywords": ["payroll", "city worker pay", "city employee pay", "city salary", "salaries"],
        "topic": "Citywide payroll",
        "dataset_id": "k397-673e",
    },
    {
        "keywords": ["mayor's budget", "budget crisis", "budget cuts", "budget deficit", "budget proposal", "city budget"],
        "topic": "City capital budget",
        "dataset_id": "2cmn-uidm",
    },
    {
        "keywords": ["jail", "rikers", "rikers island", "incarcerat", "department of correction"],
        "topic": "Daily jail population",
        "dataset_id": "7479-ugqb",
    },
    {
        "keywords": ["lobby", "lobbyist", "lobbying"],
        "topic": "Lobbying disclosures",
        "dataset_id": "fmf3-knd8",
    },
    {
        "keywords": ["campaign donor", "campaign donors", "campaign finance", "campaign contribution", "campaign contributions", "fundraising"],
        "topic": "Campaign contributions",
        "dataset_id": "rjkp-yttg",
    },
    {
        "keywords": ["election", "election results", "primary", "voter turnout"],
        "topic": "Voter analysis",
        "dataset_id": "psx2-aqx3",
    },
    {
        "keywords": ["mta", "subway", "subway delay", "subway ridership", "ferry", "bus ridership"],
        "topic": "Bicycle counts",
        "dataset_id": "uczf-rk3c",
    },
    {
        "keywords": ["pied-à-terre", "pied a terre", "tax break", "property tax", "real estate tax"],
        "topic": "Property tax data",
        "dataset_id": "8h5j-fqxa",
    },
    {
        "keywords": ["air quality", "asthma", "pollution"],
        "topic": "Air quality and health",
        "dataset_id": "c3uy-2p5r",
    },
    {
        "keywords": ["acris", "deed", "real estate sale", "property sale", "property sales"],
        "topic": "Real estate transactions",
        "dataset_id": "bnx9-e6tj",
    },
    {
        "keywords": ["school quality", "school report card", "test scores", "doe"],
        "topic": "School quality reports",
        "dataset_id": "dnpx-dfnc",
    },
]


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NYC-Open-Data-Explorer/1.0)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_rss(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title", "") or "").strip()
        link = (item.findtext("link", "") or "").strip()
        pub = (item.findtext("pubDate", "") or "").strip()
        source_el = item.find("source")
        src_attr = source_el.text.strip() if source_el is not None and source_el.text else ""
        source = src_attr
        headline = title
        m = re.search(r"\s+-\s+([^-]+)$", title)
        if m:
            if not source:
                source = m.group(1).strip()
            headline = title[:m.start()].strip()
        items.append({"headline": headline, "source": source, "link": link, "pubDate": pub})
    return items


def keyword_in(headline_lc, kw):
    """Match kw as a phrase (substring) if it has a space, else as a whole word."""
    if " " in kw or "-" in kw:
        return kw in headline_lc
    return bool(re.search(r"\b" + re.escape(kw) + r"\b", headline_lc))


def classify(headline, topics):
    hl = headline.lower()
    best_topic = None
    best_hits = 0
    best_terms = []
    for t in topics:
        hits = []
        for kw in t["keywords"]:
            if keyword_in(hl, kw):
                hits.append(kw)
        if hits and len(hits) > best_hits:
            best_topic = t
            best_hits = len(hits)
            best_terms = hits
    return best_topic, best_terms


def main():
    if not DATA.exists():
        print("catalog.min.json not found; run fetch_catalog.py first", file=sys.stderr)
        sys.exit(1)
    catalog = json.loads(DATA.read_text())
    by_id = {d["i"]: d for d in catalog["datasets"]}

    # Validate topic dataset IDs and drop any that aren't in the catalog
    valid_topics = []
    for t in TOPICS:
        if t["dataset_id"] in by_id:
            valid_topics.append(t)
        else:
            print(f"  skip topic {t['topic']} — dataset {t['dataset_id']} not found in catalog", file=sys.stderr)

    items = []
    for qs in NEWS_QUERIES:
        try:
            xml = fetch_url(NEWS_BASE + qs)
            items.extend(parse_rss(xml))
        except Exception as e:
            print(f"  fetch failed for {qs[:40]}: {e}", file=sys.stderr)

    # Dedupe headlines
    seen_h = set()
    unique_items = []
    for it in items:
        key = it["headline"][:80].lower()
        if key in seen_h or not it["headline"]:
            continue
        seen_h.add(key)
        unique_items.append(it)
    items = unique_items[:50]

    matches = []
    for it in items:
        topic, terms = classify(it["headline"], valid_topics)
        if not topic:
            continue
        d = by_id[topic["dataset_id"]]
        matches.append({
            "headline": it["headline"],
            "source": it["source"],
            "link": it["link"],
            "pubDate": it["pubDate"],
            "topic": topic["topic"],
            "dataset_id": d["i"],
            "dataset_name": d["n"],
            "dataset_category": d.get("c", ""),
            "dataset_agency": d.get("a", ""),
            "dataset_url": f"https://data.cityofnewyork.us/d/{d['i']}",
            "match_terms": terms[:4],
        })

    # Dedupe by dataset (don't show same dataset twice)
    seen_ds = set()
    unique = []
    for m in matches:
        if m["dataset_id"] in seen_ds:
            continue
        seen_ds.add(m["dataset_id"])
        unique.append(m)

    out = {
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Google News — NYC search results",
        "headlines_scanned": len(items),
        "topics_in_dictionary": len(valid_topics),
        "matches": unique[:6],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Scanned {len(items)} headlines, wrote {len(unique[:6])} matches to {OUT.relative_to(ROOT)}", file=sys.stderr)
    for m in unique[:6]:
        print(f"  [{m['topic']}] '{m['headline'][:55]}…' -> {m['dataset_name'][:55]}", file=sys.stderr)


if __name__ == "__main__":
    main()
