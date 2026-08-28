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

# ---------------------------------------------------------------------------
# Three ways of cutting the log, all keyword rules run over the City's own text.
# They are heuristics, not the City's categories: the portal publishes none. Each
# residual bucket is labelled honestly rather than hidden, and the rules are
# printed in methodology.html so a reader can disagree with a call.

# Subject matter. Multi-label — a request about school bus routes is both
# Education and Transportation — so these counts sum to more than the total.
TOPICS = [
    ("Housing & buildings", r"housing|apartment|landlord|\brent\b|tenant|evict|building|\bdob\b|\bhpd\b|construction|"
                            r"zoning|\bpluto\b|violation|certificate of occupancy"),
    ("Police & courts", r"\bnypd\b|police|crime|arrest|precinct|summons|court|jail|rikers|\bccrb\b|shooting|felony|"
                        r"misdemeanor|inmate"),
    ("Transportation", r"traffic|subway|\bbus\b|\bmta\b|bike|taxi|\btlc\b|parking|street|collision|crash|vision zero|"
                       r"ferry|\bdot\b|vehicle"),
    ("Health", r"health|hospital|dohmh|covid|disease|mental|restaurant inspection|\blead\b|asthma|birth|death|"
               r"mortality|overdose|clinic"),
    ("Education", r"school|\bdoe\b|student|teacher|education|class size|charter|enrollment|cuny|pre-?k"),
    ("Money & contracts", r"budget|contract|spending|payroll|salary|expenditure|procurement|vendor|checkbook|"
                          r"comptroller|grant"),
    ("Environment & sanitation", r"air quality|water|\btree\b|climate|flood|energy|emission|noise|waste|recycl|"
                                 r"sanitation|\bdsny\b|compost"),
    ("Business & licensing", r"business|licens|dcwp|restaurant|sidewalk cafe|cannabis|liquor|storefront"),
    ("Elections & government", r"election|\bvote|voter|city council|community board|campaign|lobby|borough president|mayor"),
    ("Social services", r"shelter|homeless|\bsnap\b|benefit|medicaid|\bhra\b|\bacs\b|child welfare|senior|immigrant|"
                        r"\bdycd\b|food pantry"),
    ("Parks & recreation", r"\bpark\b|parks|playground|\bpool\b|beach|recreation|garden|library"),
    ("Property & taxes", r"property tax|assessment|acris|deed|sale price|exemption|mortgage|real estate|\bbbl\b"),
]

# What kind of ask it is. Single-label, first rule wins, in this order: the
# specific complaints are tested before the general nomination, because most
# requests are a plain "I would like data about X" and would otherwise swallow them.
ASK_KINDS = [
    ("A broken link, file or API", r"\bapi\b|download|\bcsv\b|\berror\b|broken|export|socrata|row limit|cannot open|"
                                   r"can't open|don't have access"),
    ("A dataset gone stale", r"has not been updated|not (been )?updated since|out ?of ?date|stale|last updated|"
                             r"update the data|updated more|more frequent"),
    ("Older or archived data", r"historical|archive|previous version|prior year|going back to|older data|back to \d{4}|used to be"),
    ("More detail in a set that exists", r"additional (field|column|variable)|add (a |the )?(field|column)|more granular|"
                                         r"broken (down|out) by|breakdown by|disaggregat|missing (field|column)|geocod|"
                                         r"latitude|zip ?code level|census tract|by borough"),
    ("Help finding something", r"where can i (find|get)|is there a (data ?set|dataset)|does the city (have|publish|collect)|"
                               r"i am trying to find|trying to locate|can you (point|direct)|not sure if|cannot find|could not find"),
    ("Publish this, please", r"publish|make .{0,25}available|should be (posted|published|open)|not on open data|"
                             r"does not exist|nominat|request(ing)? that the city"),
]
ASK_OTHER = "A straight ask for data"

# What came back. Single-label, first rule wins. A response carrying a portal link
# is counted as an answer before the refusal rules run, so that "we don't have all
# of it, but here is what we do have" reads as pointing at data rather than a no.
ANSWER_KINDS = [
    ("No answer yet", r"^response not sent yet"),
    ("__portal_link", r"https?://data\.cityofnewyork\.us|data\.cityofnewyork\.us/[a-z]"),
    ("Not a City dataset", r"not maintained by a new york city agency|not a nyc agency|is not a city agency|"
                           r"not maintained by the city|metropolitan transportation authority|state agency|federal agency"),
    ("Withheld as not public", r"confidential|tax secret|personally identifiable|\bpii\b|privacy|"
                               r"cannot be (publicly )?(released|shared)|not (considered )?public (data|information)|"
                               r"not publicly available|would not be considered public|law enforcement sensitive"),
    ("Agency says it holds no such data", r"do(es)? not (collect|maintain|track|capture|have)|we do not have|"
                                          r"is not collected|no such data"),
    ("Promised to publish or update", r"will be (published|posted|added|made available|available|updated)|"
                                      r"plan(s|ning)? to (publish|post|add)|we are working (on|to)|working to (upload|publish|add)|"
                                      r"scheduled to be|data enhancement|in the coming (weeks|months)|has (since )?been (added|published|posted)"),
    ("Pointed to data that already exists", r"you can (find|access|download)|can be found|is available|are available|"
                                            r"available (at|on|here|via)|is published|please (see|visit|use)|"
                                            r"the (data ?set|dataset) (is|can|includes|contains)"),
    ("Sent somewhere else", r"\bfoil\b|openrecords|records request|contact 3-?1-?1|call 3-?1-?1|infohub|"
                            r"please contact|reach out to"),
]
POINTED = "Pointed to data that already exists"
ANSWER_OTHER = "Some other reply"

TOPICS_RE = [(name, re.compile(pat)) for name, pat in TOPICS]
ASK_RE = [(name, re.compile(pat)) for name, pat in ASK_KINDS]
ANSWER_RE = [(name, re.compile(pat)) for name, pat in ANSWER_KINDS]


def topics_of(text):
    t = text.lower()
    return [name for name, rx in TOPICS_RE if rx.search(t)]


def ask_kind(text):
    t = text.lower()
    for name, rx in ASK_RE:
        if rx.search(t):
            return name
    return ASK_OTHER


def answer_kind(response, has_link):
    t = (response or "").lower()
    for name, rx in ANSWER_RE:
        if rx.search(t):
            return POINTED if name == "__portal_link" else name
    return POINTED if has_link else ANSWER_OTHER


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
    by_topic, by_ask, by_answer = Counter(), Counter(), Counter()
    pending_by_agency, pending_by_year = Counter(), Counter()
    no_topic = 0
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

        topics = topics_of(text)
        ask = ask_kind(text)
        answer = answer_kind(resp, bool(linked))
        if not topics:
            no_topic += 1
        for t in topics:
            by_topic[t] += 1
        by_ask[ask] += 1
        by_answer[answer] += 1
        by_agency[agency] += 1
        by_status[status or "—"] += 1
        if pending:
            pending_by_agency[agency] += 1
        if sub:
            by_year[sub.year] += 1
            if pending:
                pending_by_year[sub.year] += 1
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
            "topics": topics,
            "ask": ask,
            "answer": answer,
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
            "by_agency": [{"agency": a, "n": n, "pending": pending_by_agency.get(a, 0)}
                          for a, n in by_agency.most_common(20)],
            "agencies_total": len(by_agency),
            "by_year": [{"year": y, "n": by_year[y], "pending": pending_by_year.get(y, 0)} for y in sorted(by_year)],
            "by_topic": [{"topic": t, "n": n} for t, n in by_topic.most_common()],
            "no_topic": no_topic,
            "by_ask": [{"kind": k, "n": n} for k, n in by_ask.most_common()],
            "by_answer": [{"kind": k, "n": n} for k, n in by_answer.most_common()],
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
