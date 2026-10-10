#!/usr/bin/env python3
"""Download award notices from Contracts Finder (OCDS API) into a compact JSONL cache.

    python3 pipeline/fetch_contracts.py [--from 2024-10] [--to 2026-09]

Polite and resumable: one request at a time, a pause between requests, backs off on HTTP 429, and skips months
already in the cache. Only organisation-level fields are kept. Named contact people (name, email, phone) that
appear in the notices are deliberately dropped and never stored.
"""
import argparse
import calendar
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "raw" / "cf_awards.jsonl"
DONE = ROOT / "raw" / "cf_months_done.txt"
BASE = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
UA = "UKPublicSpend/1.0 (public-interest spending explorer; reads public award notices)"
PAUSE = 26.0         # the API allows about 12 requests per 5 minutes; this keeps just under it (adaptive on a 429)
STATE = ROOT / "raw" / "cf_state.json"


class Pace:
    """Adaptive politeness: the API's rate limit is stricter than its documentation suggests."""
    delay, ok = PAUSE, 0

    @classmethod
    def success(cls):
        cls.ok += 1
        if cls.ok >= 15:
            cls.delay, cls.ok = max(PAUSE, cls.delay * 0.85), 0

    @classmethod
    def limited(cls):
        cls.delay, cls.ok = min(30.0, cls.delay * 1.6), 0


def get(url, tries=8):
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90, context=ctx) as r:
                data = json.loads(r.read())
                Pace.success()
                return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                wait = int(e.headers.get("Retry-After", 0) or 0) or 120
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


def month_range(a, b):
    y, m = map(int, a.split("-"))
    ye, me = map(int, b.split("-"))
    while (y, m) <= (ye, me):
        yield f"{y}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="a", default="2026-04")
    ap.add_argument("--to", dest="b", default="2026-09")
    args = ap.parse_args()
    CACHE.parent.mkdir(exist_ok=True)
    done = set(DONE.read_text().split()) if DONE.exists() else set()
    for ym in month_range(args.a, args.b):
        if ym in done:
            continue
        y, m = map(int, ym.split("-"))
        last = calendar.monthrange(y, m)[1]
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        url = state.get("next") if state.get("month") == ym else f"{BASE}?publishedFrom={ym}-01&publishedTo={ym}-{last:02d}&limit=100&stages=award"
        n = state.get("n", 0) if state.get("month") == ym else 0
        pages = state.get("pages", 0) if state.get("month") == ym else 0
        while url:
            d = get(url)
            recs = []
            for rel in d.get("releases", []):
                recs += compact(rel)
            n += len(d.get("releases", []))
            pages += 1
            url = (d.get("links") or {}).get("next")
            with open(CACHE, "a") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
            STATE.write_text(json.dumps({"month": ym, "next": url, "n": n, "pages": pages}))     # checkpoint: a restart resumes here
            print(f"  {ym} page {pages} ({n} notices so far)", flush=True)
            time.sleep(Pace.delay)
        STATE.unlink(missing_ok=True)
        with open(DONE, "a") as f:
            f.write(ym + "\n")
        print(f"{ym}: {n} notices, {pages} pages", flush=True)


if __name__ == "__main__":
    sys.exit(main())
