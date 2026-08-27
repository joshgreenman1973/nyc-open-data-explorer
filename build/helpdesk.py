#!/usr/bin/env python3
"""
Build the public dataset-request log: what New Yorkers have asked the City to publish,
and what the City said back.

Source: NYC Open Data Help Desk — Public Dataset Requests (63us-eqtq), the log of
nominations submitted through the Contact Us form at nyc.gov/opendata. Each row carries
the request in the requester's own words, the agency it was routed to, the agency's
written response, a legislated due date and a status.

Writes data/helpdesk.json: every request, plus the counts the rail and requests.html show.
Where a request or response names a dataset id that exists in the catalog, the id is
attached so the log links back into the explorer.

Usage: python3 build/helpdesk.py
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path

DATASET = "63us-eqtq"
BASE = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

FOURBYFOUR = re.compile(r"\b([a-z0-9]{4}-[a-z0-9]{4})\b")
WS = re.compile(r"\s+")


def fetch():
    out, offset = [], 0
    while True:
        qs = urllib.parse.urlencode({"$limit": 2000, "$offset": offset, "$order": "submission_date"})
        page = None
        for attempt in range(5):
            try:
                req = urllib.request.Request(f"{BASE}?{qs}", headers={"User-Agent": "nyc-open-data-explorer/1.0"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    page = json.load(r)
                break
            except Exception as e:      # a 403 here is anonymous throttling, so retry
                print(f"  retry {attempt + 1} ({e})", file=sys.stderr)
                time.sleep(3 * (attempt + 1))
        if page is None:
            raise RuntimeError("help desk fetch failed")
        out.extend(page)
        if len(page) < 2000:
            break
        offset += 2000
    if len(out) < 2000:
        raise RuntimeError(f"only {len(out)} requests came back — refusing to publish a short pull")
    return out


def clean(s, limit=None):
    # City text carries raw cp1252 curly quotes that arrive as stray control bytes.
    s = WS.sub(" ", (s or "").replace("\x92", "'").replace("\x93", '"').replace("\x94", '"')).strip()
    return s[:limit].rstrip() + "…" if limit and len(s) > limit else s


def day(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "")).date()
    except ValueError:
        return None


def main():
    print("Fetching the Open Data help desk log…", file=sys.stderr)
    rows = fetch()
    print(f"  {len(rows):,} requests", file=sys.stderr)

    catalog_ids = set()
    cat_path = DATA / "catalog.min.json"
    if cat_path.exists():
        cat = json.loads(cat_path.read_text())
        items = cat.get("datasets") if isinstance(cat, dict) else cat
        for d in items or []:                       # catalog.min.json keys the id as "i"
            if isinstance(d, dict) and (d.get("i") or d.get("id")):
                catalog_ids.add(d.get("i") or d.get("id"))
    print(f"  {len(catalog_ids):,} catalog ids available for linking", file=sys.stderr)

    today = date.today()
    out, by_agency, by_year, by_status = [], Counter(), Counter(), Counter()
    overdue_days = []
    for r in rows:
        status = (r.get("request_status") or "").strip()
        sub, due = day(r.get("submission_date")), day(r.get("legislated_due_date"))
        agency = clean(r.get("assigned_agency")) or "Not yet assigned"
        if agency.startswith("Agency not assigned"):
            agency = "Not yet assigned"
        text = clean(r.get("request"))
        resp = clean(r.get("response"))
        linked = sorted({m for m in FOURBYFOUR.findall((text + " " + resp).lower()) if m in catalog_ids})

        # The City gives itself 60 days: every legislated due date in this file is exactly
        # 60 days after submission. "Past Due" is its own label, so it is taken as given
        # rather than recomputed — the two disagree on a single freshly-flipped row.
        pending = status.startswith("Pending")
        waiting = (today - sub).days if (pending and sub) else None
        if pending and status.endswith("Past Due") and sub:
            overdue_days.append((today - sub).days)

        by_agency[agency] += 1
        by_status[status or "—"] += 1
        if sub:
            by_year[sub.year] += 1
        out.append({
            "id": r.get("request_id"),
            "agency": agency,
            "request": text,
            "response": resp,
            "status": status,
            "pending": pending,
            "submitted": sub.isoformat() if sub else None,
            "due": due.isoformat() if due else None,
            "waiting_days": waiting,
            "datasets": linked,
        })

    out.sort(key=lambda x: (x["submitted"] or ""), reverse=True)
    pending_past_due = by_status.get("Pending: Past Due", 0)
    oldest = min((x for x in out if x["pending"] and x["submitted"]), key=lambda x: x["submitted"], default=None)

    payload = {
        "generated": today.isoformat(),
        "source": {
            "dataset": DATASET,
            "url": f"https://data.cityofnewyork.us/d/{DATASET}",
            "name": "NYC Open Data Help Desk: Public Dataset Requests",
            "publisher": "NYC Open Data Team",
            "rows": len(out),
        },
        "stats": {
            "total": len(out),
            "closed": sum(1 for x in out if not x["pending"]),
            "pending": sum(1 for x in out if x["pending"]),
            "pending_past_due": pending_past_due,
            "closed_past_due": by_status.get("Closed: Past Due", 0),
            "with_dataset_link": sum(1 for x in out if x["datasets"]),
            "median_wait_days": sorted(overdue_days)[len(overdue_days) // 2] if overdue_days else None,
            "response_window_days": 60,
            "oldest_pending": {"submitted": oldest["submitted"], "agency": oldest["agency"]} if oldest else None,
            "first_request": min((x["submitted"] for x in out if x["submitted"]), default=None),
            "by_status": [{"status": s, "n": n} for s, n in by_status.most_common()],
            "by_agency": [{"agency": a, "n": n} for a, n in by_agency.most_common(15)],
            "by_year": [{"year": y, "n": by_year[y]} for y in sorted(by_year)],
        },
        "requests": out,
    }

    DATA.mkdir(exist_ok=True)
    p = DATA / "helpdesk.json"
    p.write_text(json.dumps(payload, separators=(",", ":")))
    s = payload["stats"]
    print(f"wrote {p} ({p.stat().st_size / 1024:.0f} KB)", file=sys.stderr)
    print(f"  {s['total']:,} requests · {s['pending_past_due']:,} pending past due · "
          f"{s['with_dataset_link']:,} linked to a catalog dataset", file=sys.stderr)


if __name__ == "__main__":
    main()
