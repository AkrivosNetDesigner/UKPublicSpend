#!/usr/bin/env python3
"""Download award notices from Contracts Finder (OCDS API) into a compact JSONL cache, one day at a time.

    python3 pipeline/fetch_contracts.py                  # the last 60 days (new days only on later runs)
    python3 pipeline/fetch_contracts.py --from 2026-04-01   # extend further back

Why one day at a time: the API treats `publishedTo` as exclusive and caps how many results a single query returns, so
whole-month queries silently lose data. A day is a small, complete unit. A day is recorded as done only once it is in the
past, so re-running fetches just the days not yet seen (and today again, which is still filling up). That makes it
incremental: run it whenever you like and it only asks for what is new.

Polite and resumable: one request at a time at the pace the API allows (about 12 per 5 minutes), backing off on HTTP
429/403. Only organisation-level fields are kept. Named contact people (name, email, phone) in the notices are dropped.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "raw" / "cf_awards.jsonl"
DONE = ROOT / "raw" / "cf_days_done.txt"
BASE = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
UA = "UKPublicSpend/1.0 (public-interest spending explorer; reads public award notices)"
PAUSE = 26.0         # the API allows about 12 requests per 5 minutes; this keeps just under it (adaptive on a 429)
SPLIT_AT_PAGES = 10  # a day this big may hit the result cap: refetch it in smaller windows


class Pace:
    """Adaptive politeness: slow down after a rate-limit response, ease back after a run of successes."""
    delay, ok = PAUSE, 0

    @classmethod
    def success(cls):
        cls.ok += 1
        if cls.ok >= 15:
            cls.delay, cls.ok = max(PAUSE, cls.delay * 0.85), 0

    @classmethod
    def limited(cls):
        cls.delay, cls.ok = min(60.0, cls.delay * 1.5), 0


def get(url, tries=8):
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90, context=ctx) as r:
                data = json.loads(r.read())
                Pace.success()
                return data
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503):
                wait = int(e.headers.get("Retry-After", 0) or 0) or 300 if e.code == 403 else int(e.headers.get("Retry-After", 0) or 0) or 120
                Pace.limited()
                print(f"  HTTP {e.code}; waiting {wait}s, then pacing at {Pace.delay:.0f}s per request", flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"  network error {e}; retrying", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("giving up on " + url)


def compact(rel):
    """One record per award, organisation-level fields only."""
    t = rel.get("tender", {}) or {}
    parties = {p.get("id"): p for p in rel.get("parties", [])}
    buyer = rel.get("buyer", {}) or {}
    out = []
    for a in rel.get("awards", []) or []:
        sups = []
        for s in a.get("suppliers", []) or []:
            p = parties.get(s.get("id"), {})
            ident = p.get("identifier") or {}
            det = p.get("details") or {}
            sups.append({"name": s.get("name") or p.get("name"), "scheme": ident.get("scheme"), "id": ident.get("id"), "scale": det.get("scale")})
        doc = next((d.get("url") for d in a.get("documents", []) or [] if d.get("url")), None)
        out.append({
            "id": a.get("id"), "ocid": rel.get("ocid"), "tag": rel.get("tag"),
            "pub": (a.get("datePublished") or rel.get("date") or "")[:10], "rel": (rel.get("date") or "")[:10], "aw": (a.get("date") or "")[:10],
            "buyer": buyer.get("name"), "buyer_id": buyer.get("id"),
            "title": (t.get("title") or "")[:140], "cpv": (t.get("classification") or {}).get("id"), "cpvd": (t.get("classification") or {}).get("description"),
            "cat": t.get("mainProcurementCategory"), "pm": t.get("procurementMethod"), "pmd": t.get("procurementMethodDetails"),
            "tv": (t.get("value") or {}).get("amount"), "tmin": (t.get("minValue") or {}).get("amount"),
            "av": (a.get("value") or {}).get("amount"), "cur": (a.get("value") or {}).get("currency"),
            "sups": sups, "sme": (t.get("suitability") or {}).get("sme"), "vcse": (t.get("suitability") or {}).get("vcse"),
            "cs": ((a.get("contractPeriod") or t.get("contractPeriod") or {}).get("startDate") or "")[:10],
            "ce": ((a.get("contractPeriod") or t.get("contractPeriod") or {}).get("endDate") or "")[:10],
            "te": ((t.get("tenderPeriod") or {}).get("endDate") or "")[:10], "url": doc,
        })
    return out


def plan(first, today, done):
    """Days to fetch, newest first. A past day is done once fetched; today is always refetched (it is still filling up)."""
    days, d = [], today
    while d >= first:
        if d == today or d.isoformat() not in done:
            days.append(d)
        d -= timedelta(days=1)
    return days


def windows(day, parts=1):
    """(publishedFrom, publishedTo) pairs covering `day`; the end of the range is exclusive."""
    start = datetime(day.year, day.month, day.day)
    step = timedelta(hours=24 // parts)
    f = "%Y-%m-%dT%H:%M:%S"
    return [((start + i * step).strftime(f), (start + (i + 1) * step).strftime(f)) for i in range(parts)]


def fetch_window(a, b):
    """All pages for one window -> (releases_seen, award_records, pages)."""
    url = f"{BASE}?publishedFrom={a}&publishedTo={b}&limit=100&stages=award"
    n, recs, pages = 0, [], 0
    while url:
        d = get(url)
        for rel in d.get("releases", []):
            recs += compact(rel)
        n += len(d.get("releases", []))
        pages += 1
        url = (d.get("links") or {}).get("next")
        if url:
            time.sleep(Pace.delay)
    return n, recs, pages


def fetch_day(day):
    n, recs, pages = fetch_window(*windows(day)[0])
    if pages >= SPLIT_AT_PAGES:      # possibly truncated by the API's result cap: redo in 6-hour windows
        print(f"  {day}: {pages} pages, refetching in 6-hour windows to be safe", flush=True)
        n, recs, pages = 0, [], 0
        for a, b in windows(day, 4):
            time.sleep(Pace.delay)
            n2, r2, p2 = fetch_window(a, b)
            n, recs, pages = n + n2, recs + r2, pages + p2
    return n, recs, pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="a", default=(date.today() - timedelta(days=60)).isoformat(), help="first day to fetch (default: 60 days ago)")
    args = ap.parse_args()
    CACHE.parent.mkdir(exist_ok=True)
    done = set(DONE.read_text().split()) if DONE.exists() else set()
    today = date.today()
    todo = plan(date.fromisoformat(args.a), today, done)
    print(f"{len(todo)} day(s) to fetch ({len(done)} already done)", flush=True)
    for i, day in enumerate(todo):
        n, recs, pages = fetch_day(day)
        with open(CACHE, "a") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
        if day < today:
            with open(DONE, "a") as f:
                f.write(day.isoformat() + "\n")
        print(f"{day}: {n} notices, {pages} page(s) [{i + 1}/{len(todo)}]", flush=True)
        if i + 1 < len(todo):
            time.sleep(Pace.delay)


if __name__ == "__main__":
    sys.exit(main())
