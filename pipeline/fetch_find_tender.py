#!/usr/bin/env python3
"""Download award notices from Find a Tender (OCDS API) into a compact JSONL cache.

    python3 pipeline/fetch_find_tender.py                    # the last 60 days (new days only on later runs)
    python3 pipeline/fetch_find_tender.py --from 2026-04-01  # extend further back

Find a Tender is the government's newer procurement service (above-threshold contracts, and notices under the
Procurement Act 2023). Unlike Contracts Finder its API is not tightly rate-limited: about 20 requests fetch two months of
awards. Records use the same fields as fetch_contracts.py, plus `src: "fts"`, so the Contracts page can combine both.

Care is taken not to mislabel framework call-offs: most notices published as "award procedure without prior publication
of a call for competition" give "outside the scope of the directive" as the reason, which is how call-offs from
frameworks and other exempt contracts are reported. Only the reasons that describe a real direct award (urgency, a single
possible supplier, repetition, no tenders received and so on) are treated as direct awards, and the reason is kept.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "raw" / "fts_awards.jsonl"
STATE = ROOT / "raw" / "fts_done.txt"
BASE = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
NOTICE = "https://www.find-tender.service.gov.uk/Notice/"
UA = "UKPublicSpend/1.0 (public-interest spending explorer; reads public award notices)"
WINDOW_DAYS = 5
OVERLAP_DAYS = 3        # notices are updated after first publication: re-read the last few days each run
PAUSE = 0.5

NO_CALL = "Award procedure without prior publication of a call for competition"
OUTSIDE = "D_OUTSIDE_SCOPE"
REASONS = {
    "D_TECHNICAL": "only one supplier could provide it for technical reasons",
    "D_PROTECT_RIGHTS": "only one supplier could provide it because of exclusive or protected rights",
    "D_REPETITION_EXISTING": "a repeat of earlier works or services",
    "D_EXTREME_URGENCY": "extreme urgency",
    "D_PROC_OPEN": "no suitable tenders in an earlier open procedure",
    "D_PROC_RESTRICTED": "no suitable tenders in an earlier restricted procedure",
    "D_PROC_NEGOTIATED_PRIOR_CALL_COMPETITION": "no suitable tenders in an earlier negotiated procedure",
    "D_NO_TENDERS_REQUESTS": "no tenders or requests to take part were received",
    "D_ADD_DELIVERIES_ORDERED": "additional deliveries from the original supplier",
    "D_CONTRACT_AWARDED_DESIGN_CONTEST": "awarded to the winner of a design contest",
    "D_MANUF_FOR_RESEARCH": "goods made purely for research or experiment",
    "D_COMMODITY_MARKET": "goods bought on a commodity market",
}


def get(url, tries=6):
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90, context=ctx) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503):
                wait = int(e.headers.get("Retry-After", 0) or 0) or 60 * (attempt + 1)
                print(f"  HTTP {e.code}; waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"  network error {e}; retrying", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("giving up on " + url)


def procedure(tender, release_text=""):
    """(procurementMethodDetails, why) with call-offs and exempt contracts kept apart from real direct awards."""
    pm, pmd = tender.get("procurementMethod"), tender.get("procurementMethodDetails")
    if pm != "limited" and NO_CALL not in (pmd or ""):
        return pmd, None
    ids = [c.get("id") for c in tender.get("procurementMethodRationaleClassifications") or []]
    text = ((tender.get("procurementMethodRationale") or "") + " " + release_text).lower()
    if OUTSIDE in ids:
        if "framework" in text or "dynamic purchasing" in text or "call-off" in text or "call off" in text:
            return "Call-off from a framework agreement", None
        return "Outside the scope of the procurement rules (no call for competition)", None
    why = next((REASONS[i] for i in ids if i in REASONS), None)
    return NO_CALL, why or (tender.get("procurementMethodRationale") or "")[:140] or None


def compact(rel):
    """One record per award, organisation-level fields only (named contact people are never read)."""
    t = rel.get("tender", {}) or {}
    parties = {p.get("id"): p for p in rel.get("parties", []) or []}
    buyer = rel.get("buyer", {}) or {}
    contracts = {c.get("awardID"): c for c in rel.get("contracts", []) or []}
    pmd, why = procedure(t, rel.get("description") or "")
    out = []
    for a in rel.get("awards", []) or []:
        c = contracts.get(a.get("id")) or {}
        sups = []
        for s in a.get("suppliers", []) or []:
            p = parties.get(s.get("id"), {})
            ident = p.get("identifier") or {}
            sups.append({"name": s.get("name") or p.get("name"), "scheme": ident.get("scheme"), "id": ident.get("id"), "scale": (p.get("details") or {}).get("scale")})
        period = c.get("period") or {}
        out.append({
            "id": a.get("id"), "ocid": rel.get("ocid"), "tag": rel.get("tag"), "src": "fts",
            "pub": (rel.get("date") or "")[:10], "rel": (rel.get("date") or "")[:10], "aw": (c.get("dateSigned") or "")[:10],
            "buyer": buyer.get("name"), "buyer_id": buyer.get("id"),
            "title": (a.get("title") or t.get("title") or "")[:140], "cpv": (t.get("classification") or {}).get("id"), "cpvd": (t.get("classification") or {}).get("description"),
            "cat": t.get("mainProcurementCategory"), "pm": t.get("procurementMethod"), "pmd": pmd, "why": why,
            "fw": bool((t.get("techniques") or {}).get("hasFrameworkAgreement") or (t.get("techniques") or {}).get("hasDynamicPurchasingSystem")),
            "tv": (t.get("value") or {}).get("amount"), "tmin": None,
            "av": (c.get("value") or {}).get("amount"), "cur": (c.get("value") or {}).get("currency"),
            "sups": sups, "sme": None, "vcse": None,
            "cs": (period.get("startDate") or "")[:10], "ce": (period.get("endDate") or "")[:10], "te": "",
            "url": NOTICE + str(rel.get("id")),
        })
    return out


def fetch_window(a, b):
    url = f"{BASE}?updatedFrom={a}T00:00:00&updatedTo={b}T00:00:00&limit=100&stages=award"
    recs, n, pages = [], 0, 0
    while url:
        d = get(url)
        for rel in d.get("releases", []):
            recs += compact(rel)
        n += len(d.get("releases", []))
        pages += 1
        url = (d.get("links") or {}).get("next")
        if url:
            time.sleep(PAUSE)
    return n, recs, pages


def dedupe(path):
    """Keep the latest version of each award (notices are updated in place)."""
    latest = {}
    for line in open(path):
        r = json.loads(line)
        k = r["id"]
        if k not in latest or (r.get("rel") or "") >= (latest[k].get("rel") or ""):
            latest[k] = r
    with open(path, "w") as f:
        for r in latest.values():
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(latest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="a", default=(date.today() - timedelta(days=60)).isoformat())
    args = ap.parse_args()
    CACHE.parent.mkdir(exist_ok=True)
    start = date.fromisoformat(args.a)
    if STATE.exists():
        last = date.fromisoformat(STATE.read_text().split()[-1])
        start = max(start, last - timedelta(days=OVERLAP_DAYS))
    end = date.today() + timedelta(days=1)
    day, total = start, 0
    while day < end:
        nxt = min(day + timedelta(days=WINDOW_DAYS), end)
        n, recs, pages = fetch_window(day.isoformat(), nxt.isoformat())
        with open(CACHE, "a") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
        total += len(recs)
        print(f"{day} to {nxt}: {n} notices, {pages} page(s)", flush=True)
        day = nxt
    STATE.write_text(date.today().isoformat() + "\n")
    print(f"{total} award records fetched; {dedupe(CACHE)} awards in the cache", flush=True)


if __name__ == "__main__":
    sys.exit(main())
