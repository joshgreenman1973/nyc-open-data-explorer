#!/usr/bin/env python3
"""
Pull a small set of interesting numbers from NYC Open Data datasets that
update at least weekly. Writes data/weekly_stats.json for the front end.

Each stat is a small object: { headline (number), label, sub (one-line context),
dataset_id, dataset_name, computed_at }. Failures are soft — if a query times
out or 500s, that stat is skipped and noted in the file's `errors` array, but
the build keeps going.
"""
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "weekly_stats.json"
DOMAIN = "data.cityofnewyork.us"
TIMEOUT = 45


def soql(rid, query, retries=2):
    url = f"https://{DOMAIN}/resource/{rid}.json?{urllib.parse.urlencode({'$query': query})}"
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            if attempt < retries:
                import time as _t
                _t.sleep(1.5 * (attempt + 1))
    raise last


def fmt_int(n):
    try:
        return f"{int(float(n)):,}"
    except Exception:
        return str(n)


def main():
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    stats = []
    errors = []

    def safe(label, fn):
        try:
            stat = fn()
            if stat:
                stats.append(stat)
        except Exception as e:
            errors.append({"label": label, "err": str(e)})
            print(f"  skip {label}: {e}", file=sys.stderr)

    # 1) 311 complaints in the last 7 days + top type
    def stat_311():
        c = soql("erm2-nwe9", f"SELECT count(*) AS n WHERE created_date > '{start}'")[0]["n"]
        top = soql("erm2-nwe9", f"SELECT complaint_type, count(*) AS n WHERE created_date > '{start}' GROUP BY complaint_type ORDER BY n DESC LIMIT 1")[0]
        return {
            "key": "311",
            "headline": fmt_int(c),
            "label": "311 complaints in the past 7 days",
            "sub": f"Most common: {top['complaint_type']} ({fmt_int(top['n'])})",
            "dataset_id": "erm2-nwe9",
            "dataset_name": "311 Service Requests from 2020 to Present",
            "category": "Social Services",
        }

    # 2) Motor vehicle collisions
    def stat_mvc():
        c = soql("h9gi-nx95", f"SELECT count(*) AS n WHERE crash_date > '{start}'")[0]["n"]
        try:
            inj = soql("h9gi-nx95", f"SELECT sum(number_of_persons_injured) AS n WHERE crash_date > '{start}'")[0].get("n", "0")
        except Exception:
            inj = "0"
        return {
            "key": "mvc",
            "headline": fmt_int(c),
            "label": "Motor-vehicle crashes reported",
            "sub": f"{fmt_int(inj)} people injured",
            "dataset_id": "h9gi-nx95",
            "dataset_name": "Motor Vehicle Collisions - Crashes",
            "category": "Public Safety",
        }

    # 3) DOB approved permits
    def stat_dob():
        c = soql("rbx6-tga4", f"SELECT count(*) AS n WHERE issued_date > '{start}'")[0]["n"]
        return {
            "key": "dob",
            "headline": fmt_int(c),
            "label": "DOB construction permits issued",
            "sub": "Excludes electrical and elevator filings",
            "dataset_id": "rbx6-tga4",
            "dataset_name": "DOB NOW: Build – Approved Permits",
            "category": "Housing & Development",
        }

    # 4) Restaurant inspections + grade A share
    def stat_rest():
        rows = soql("43nn-pn8j", f"SELECT grade, count(*) AS n WHERE inspection_date > '{start}' GROUP BY grade")
        total = sum(int(r["n"]) for r in rows)
        a = next((int(r["n"]) for r in rows if r.get("grade") == "A"), 0)
        share = round(100 * a / total) if total else 0
        return {
            "key": "rest",
            "headline": fmt_int(total),
            "label": "Restaurant inspections completed",
            "sub": f"{share}% earned an A grade ({fmt_int(a)} of {fmt_int(total)})",
            "dataset_id": "43nn-pn8j",
            "dataset_name": "DOHMH NYC Restaurant Inspection Results",
            "category": "Health",
        }

    # 5) Catalog meta — datasets updated this week
    def stat_meta():
        cat = json.loads((ROOT / "data" / "catalog.min.json").read_text())
        n = len(cat.get("fresh", {}).get("updated_this_week", []))
        # Plus full count from the catalog: rescan because fresh array is capped at 20
        total = sum(1 for d in cat["datasets"] if d.get("u", "") >= start)
        return {
            "key": "catalog",
            "headline": fmt_int(total),
            "label": "Datasets refreshed by City agencies",
            "sub": f"{fmt_int(len(cat['datasets']))} total datasets in the catalog",
            "dataset_id": None,
            "dataset_name": "NYC Open Data catalog metadata",
            "category": None,
        }

    safe("311", stat_311)
    safe("mvc", stat_mvc)
    safe("dob", stat_dob)
    safe("rest", stat_rest)
    safe("meta", stat_meta)

    out = {
        "computed_at": now.isoformat(timespec="seconds"),
        "window_start": start,
        "window_label": "the past 7 days",
        "stats": stats,
        "errors": errors,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {len(stats)} stats ({len(errors)} errors) to {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
