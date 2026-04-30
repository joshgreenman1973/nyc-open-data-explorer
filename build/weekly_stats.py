#!/usr/bin/env python3
"""
Pull a small set of interesting numbers from NYC Open Data datasets that
update at least weekly, plus a 12-week trend for each so the headline number
has context. Writes data/weekly_stats.json for the front end.

Each stat: { headline, label, sub, trend (12 weekly buckets), delta_pct
(latest week vs prior week), dataset_id, dataset_name, computed_at }.
Failures are soft — if a query times out, that stat is skipped.
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
TIMEOUT = 60
WEEKS = 12


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


def daily_to_buckets(rows, date_field, end_dt, n_buckets=WEEKS):
    """Convert a list of {date_field: 'YYYY-MM-DD...', n: '123'} rows into
    n_buckets non-overlapping 7-day buckets ending at end_dt."""
    by_day = {}
    for r in rows:
        d = (r.get(date_field) or "")[:10]
        if not d:
            continue
        try:
            by_day[d] = by_day.get(d, 0) + int(r.get("n", 0))
        except Exception:
            pass
    buckets = []
    for i in range(n_buckets - 1, -1, -1):
        end = end_dt - timedelta(days=7 * i)
        start = end - timedelta(days=7)
        total = 0
        cur = start
        while cur < end:
            total += by_day.get(cur.strftime("%Y-%m-%d"), 0)
            cur += timedelta(days=1)
        buckets.append(total)
    return buckets


def delta_pct(buckets):
    if len(buckets) < 2 or buckets[-2] == 0:
        return None
    return round(100 * (buckets[-1] - buckets[-2]) / buckets[-2])


def main():
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    trend_start = (now - timedelta(days=7 * WEEKS)).strftime("%Y-%m-%dT%H:%M:%S")
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

    # 1) 311
    def stat_311():
        top = soql("erm2-nwe9", f"SELECT complaint_type, count(*) AS n WHERE created_date > '{start}' GROUP BY complaint_type ORDER BY n DESC LIMIT 1")[0]
        daily = soql("erm2-nwe9", f"SELECT date_trunc_ymd(created_date) AS d, count(*) AS n WHERE created_date > '{trend_start}' GROUP BY d ORDER BY d")
        trend = daily_to_buckets(daily, "d", now)
        return {
            "key": "311",
            "headline": fmt_int(trend[-1]),
            "label": "311 complaints in the past 7 days",
            "sub": f"Most common: {top['complaint_type']} ({fmt_int(top['n'])})",
            "trend": trend,
            "delta_pct": delta_pct(trend),
            "dataset_id": "erm2-nwe9",
            "dataset_name": "311 Service Requests from 2020 to Present",
            "category": "Social Services",
        }

    # 2) Motor vehicle collisions
    def stat_mvc():
        try:
            inj = soql("h9gi-nx95", f"SELECT sum(number_of_persons_injured) AS n WHERE crash_date > '{start}'")[0].get("n", "0")
        except Exception:
            inj = "0"
        daily = soql("h9gi-nx95", f"SELECT date_trunc_ymd(crash_date) AS d, count(*) AS n WHERE crash_date > '{trend_start}' GROUP BY d ORDER BY d")
        trend = daily_to_buckets(daily, "d", now)
        return {
            "key": "mvc",
            "headline": fmt_int(trend[-1]),
            "label": "Motor-vehicle crashes reported",
            "sub": f"{fmt_int(inj)} people injured",
            "trend": trend,
            "delta_pct": delta_pct(trend),
            "dataset_id": "h9gi-nx95",
            "dataset_name": "Motor Vehicle Collisions - Crashes",
            "category": "Public Safety",
        }

    # 3) DOB approved permits
    def stat_dob():
        daily = soql("rbx6-tga4", f"SELECT date_trunc_ymd(issued_date) AS d, count(*) AS n WHERE issued_date > '{trend_start}' GROUP BY d ORDER BY d")
        trend = daily_to_buckets(daily, "d", now)
        return {
            "key": "dob",
            "headline": fmt_int(trend[-1]),
            "label": "DOB construction permits issued",
            "sub": "Excludes electrical and elevator filings",
            "trend": trend,
            "delta_pct": delta_pct(trend),
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
        daily = soql("43nn-pn8j", f"SELECT date_trunc_ymd(inspection_date) AS d, count(*) AS n WHERE inspection_date > '{trend_start}' GROUP BY d ORDER BY d")
        trend = daily_to_buckets(daily, "d", now)
        return {
            "key": "rest",
            "headline": fmt_int(trend[-1]),
            "label": "Restaurant inspections completed",
            "sub": f"{share}% earned an A grade ({fmt_int(a)} of {fmt_int(total)} graded)",
            "trend": trend,
            "delta_pct": delta_pct(trend),
            "dataset_id": "43nn-pn8j",
            "dataset_name": "DOHMH NYC Restaurant Inspection Results",
            "category": "Health",
        }

    # 5) Catalog meta — datasets refreshed (computed locally from catalog metadata)
    def stat_meta():
        cat = json.loads((ROOT / "data" / "catalog.min.json").read_text())
        # Trend: per-week count of datasets whose last `u` falls in each bucket
        buckets = [0] * WEEKS
        for d in cat["datasets"]:
            u = (d.get("u") or "")[:10]
            if not u:
                continue
            try:
                udt = datetime.fromisoformat(u).replace(tzinfo=timezone.utc)
            except Exception:
                continue
            days_ago = (now - udt).days
            if days_ago < 0 or days_ago >= 7 * WEEKS:
                continue
            idx = WEEKS - 1 - (days_ago // 7)
            if 0 <= idx < WEEKS:
                buckets[idx] += 1
        total = buckets[-1]
        return {
            "key": "catalog",
            "headline": fmt_int(total),
            "label": "Datasets refreshed by City agencies",
            "sub": f"{fmt_int(len(cat['datasets']))} total datasets in the catalog",
            "trend": buckets,
            "delta_pct": delta_pct(buckets),
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
        "trend_weeks": WEEKS,
        "stats": stats,
        "errors": errors,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {len(stats)} stats ({len(errors)} errors) to {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
