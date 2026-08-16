#!/usr/bin/env python3
"""
Catalog changelog: what the City added, removed, renamed or re-described.

Compares the freshly fetched data/catalog.json against the previous snapshot
(the version committed at git HEAD) and appends events to data/changelog.json.

    python3 build/changelog.py            # daily: diff HEAD snapshot vs working file
    python3 build/changelog.py --backfill # rebuild from every snapshot in git history

Event kinds:
    added                new dataset id appeared in the catalog
    removed              id disappeared and stayed gone (see below)
    renamed              name changed
    description_changed  description text changed
    agency_changed       attribution changed
    columns_changed      column names added/removed (only when both snapshots carry columns)

Removal is confirmed cautiously: the Discovery API occasionally drops an item
for a day, so an id must be missing from two consecutive snapshots before it is
logged as removed. In daily mode we also ask the portal directly
(api/views/<id>) — a 200 means the dataset still exists and the miss was a
glitch. Pending removals live in changelog.json under "pending_removed".
"""
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
OUT = ROOT / "data" / "changelog.json"
STATE = ROOT / "data" / "changelog_state.json"   # ids ever seen + pending removals (not loaded by the front end)
DOMAIN = "data.cityofnewyork.us"
KEEP_DAYS = 365
MAX_EVENTS = 5000
DESC_SNIPPET = 220


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def load_snapshot_from_git(rev):
    try:
        raw = git("show", f"{rev}:data/catalog.json")
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def index(snapshot):
    return {d["id"]: d for d in (snapshot or {}).get("datasets", []) if d.get("id")}


def snip(s):
    s = (s or "").strip()
    return s if len(s) <= DESC_SNIPPET else s[:DESC_SNIPPET].rsplit(" ", 1)[0] + "..."


def diff_window(a, b, before=70, after=150):
    """Snippets of a and b centred on the first character where they differ,
    so a one-word edit deep in a long description is actually visible."""
    p = 0
    n = min(len(a), len(b))
    while p < n and a[p] == b[p]:
        p += 1
    # back up to a word boundary
    start = max(0, p - before)
    if start > 0:
        sp = a.rfind(" ", 0, start)
        start = sp + 1 if sp > 0 else start
    def win(t):
        seg = t[start:p + after]
        return ("..." if start > 0 else "") + seg + ("..." if p + after < len(t) else "")
    return win(a), win(b), p


import re as _re
_acro = _re.compile(r"\s*\([A-Z][A-Z0-9 &/\-]+\)\s*$")


def agency_key(name):
    """Fold spelling variants so canonicalization changes in our own build don't count as events."""
    s = (name or "").replace("’", "'").replace("‘", "'").replace("&", "and")
    s = _acro.sub("", s).strip().lower()
    s = _re.sub(r"\s+", " ", s)
    if s in ("", "other / unspecified", "no agency listed", "other"):
        return ""
    return s


def brief(d):
    return {"id": d["id"], "name": d.get("name", ""), "agency": d.get("agency", ""),
            "category": d.get("category", ""), "type": d.get("type", ""),
            "url": d.get("url") or f"https://{DOMAIN}/d/{d['id']}"}


def diff(prev, cur, date, known):
    """Return (events, missing_ids). Events exclude removals — those are
    handled by the caller with the two-snapshot rule. `known` is the set of
    every id ever seen; an id that flickers out and back is not "added"."""
    events = []
    for i, d in cur.items():
        p = prev.get(i)
        if p is None:
            if i not in known:
                e = brief(d); e.update({"kind": "added", "date": date, "summary": snip(d.get("summary") or d.get("description"))})
                events.append(e)
            continue
        if (p.get("name") or "") != (d.get("name") or ""):
            e = brief(d); e.update({"kind": "renamed", "date": date, "before": p.get("name", ""), "after": d.get("name", "")})
            events.append(e)
        pd, cd = (p.get("description") or "").strip(), (d.get("description") or "").strip()
        if pd != cd:
            wb, wa, at = diff_window(pd, cd)
            e = brief(d); e.update({"kind": "description_changed", "date": date, "before": wb, "after": wa,
                                    "before_len": len(pd), "after_len": len(cd), "diff_at": at})
            events.append(e)
        if agency_key(p.get("agency")) != agency_key(d.get("agency")) and agency_key(d.get("agency")):
            e = brief(d); e.update({"kind": "agency_changed", "date": date, "before": p.get("agency", ""), "after": d.get("agency", "")})
            events.append(e)
        pc, cc = p.get("columns"), d.get("columns")
        if pc and cc and pc != cc:
            ps, cs = set(pc), set(cc)
            added, removed = sorted(cs - ps), sorted(ps - cs)
            if added or removed:
                e = brief(d); e.update({"kind": "columns_changed", "date": date, "columns_added": added, "columns_removed": removed})
                events.append(e)
    missing = [i for i in prev if i not in cur]
    return events, missing


def still_on_portal(rid):
    """True if the portal still serves metadata for this id (so the miss was a glitch)."""
    req = urllib.request.Request(f"https://{DOMAIN}/api/views/{rid}.json", method="GET",
                                 headers={"User-Agent": "nyc-open-data-explorer changelog"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return False
        return None  # 403 / 5xx: unknown
    except Exception:
        return None


def load_out():
    out = {"generated_at": None, "events": []}
    if OUT.exists():
        try:
            out = json.loads(OUT.read_text())
        except Exception:
            pass
    state = {"known_ids": [], "pending_removed": {}}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except Exception:
            pass
    out["pending_removed"] = state.get("pending_removed", {})
    out["known_ids"] = set(state.get("known_ids", []))
    return out


def prune(events):
    cutoff = (datetime.now(timezone.utc).timestamp() - KEEP_DAYS * 86400)
    kept = []
    for e in events:
        try:
            t = datetime.fromisoformat(e["date"]).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            t = 0
        if t >= cutoff:
            kept.append(e)
    kept.sort(key=lambda e: e["date"], reverse=True)
    return kept[:MAX_EVENTS]


def apply_removals(out, prev, missing, date, verify):
    """Two-snapshot rule for removals, with optional live check."""
    pending = out.setdefault("pending_removed", {})
    events = []
    # confirm those already pending that are still missing
    for rid in list(pending.keys()):
        if rid in missing:
            info = pending.pop(rid)
            if verify:
                alive = still_on_portal(rid)
                if alive:  # glitch — forget it
                    continue
                info["verified_gone"] = (alive is False)
            e = {"kind": "removed", "date": info["date"], **{k: info[k] for k in ("id", "name", "agency", "category", "type", "url")}}
            if "verified_gone" in info:
                e["verified_gone"] = info["verified_gone"]
            events.append(e)
        else:
            pending.pop(rid)  # came back
    # newly missing → pending
    for rid in missing:
        if rid in pending:
            continue
        p = prev.get(rid)
        if p:
            info = brief(p); info["date"] = date
            pending[rid] = info
    return events


def dedupe(events):
    seen, out = set(), []
    for e in events:
        key = (e["kind"], e["id"], e["date"], e.get("after", ""), e.get("before", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def main():
    backfill = "--backfill" in sys.argv
    out = load_out()
    cur = json.loads(CATALOG.read_text())
    today = (cur.get("fetched_at") or datetime.now(timezone.utc).isoformat())[:10]

    if backfill:
        revs = git("log", "--format=%H %cs", "--reverse", "--", "data/catalog.json").decode().split("\n")
        revs = [r.split() for r in revs if r.strip()]
        print(f"Backfilling from {len(revs)} snapshots", file=sys.stderr)
        events, out["pending_removed"], out["known_ids"] = [], {}, set()
        prev = None
        for i, (sha, date) in enumerate(revs):
            snap = load_snapshot_from_git(sha)
            if not snap:
                continue
            idx = index(snap)
            if prev is not None:
                ev, missing = diff(prev, idx, date, out["known_ids"])
                events.extend(ev)
                events.extend(apply_removals(out, prev, missing, date, verify=False))
            out["known_ids"].update(idx)
            prev = idx
            if i % 10 == 0:
                print(f"  {i}/{len(revs)} {date}: {len(events)} events so far", file=sys.stderr)
        # working copy vs last committed
        idx = index(cur)
        if prev is not None:
            ev, missing = diff(prev, idx, today, out["known_ids"])
            events.extend(ev)
            events.extend(apply_removals(out, prev, missing, today, verify=True))
        out["known_ids"].update(idx)
        # anything still in the current catalog was never really removed
        live = set(idx)
        events = [e for e in events if not (e["kind"] == "removed" and e["id"] in live)]
        out["events"] = dedupe(events)
    else:
        prev_snap = load_snapshot_from_git("HEAD")
        if not prev_snap:
            sys.exit("ABORT: no previous catalog.json at HEAD to diff against.")
        prev, idx = index(prev_snap), index(cur)
        if len(idx) < len(prev) * 0.9:
            sys.exit(f"ABORT: new catalog has {len(idx)} datasets vs {len(prev)} before — looks like a partial fetch, not real removals.")
        ev, missing = diff(prev, idx, today, out["known_ids"])
        ev.extend(apply_removals(out, prev, missing, today, verify=True))
        out["known_ids"].update(idx)
        out["events"] = dedupe(ev + out.get("events", []))

    out["events"] = prune(out["events"])
    out["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {}
    for e in out["events"]:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    out["counts"] = counts
    state = {"known_ids": sorted(out.pop("known_ids")), "pending_removed": out.pop("pending_removed")}
    STATE.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"Wrote {len(out['events'])} events {counts}; {len(state['pending_removed'])} pending removals", file=sys.stderr)


if __name__ == "__main__":
    main()
