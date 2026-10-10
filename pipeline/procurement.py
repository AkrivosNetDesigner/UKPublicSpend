"""Public procurement red-flag screening from Contracts Finder award notices.

Everything here is a screening indicator on public award notices, not an allegation. Contracts Finder does NOT publish
the number of bidders, so single-bidder tests are impossible; the tests below use what is published: how the buyer
bought (competitive, framework, direct award), values, dates, buyers and (registered) suppliers.

Privacy: only organisation-level fields are kept. Suppliers that cannot be recognised as organisations (no registered
number and no company-style name) are never named, so private individuals are not singled out.
"""
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import date

import analysis as A

PARAMS = {
    "direct_min_m": 0.25, "direct_sev2_m": 1.0, "direct_sev3_m": 5.0,         # non-competitive award size, £m
    "late_days": 90, "late_min_m": 0.1,                                        # published this long after award / start
    "estimate_ratio": 2.0, "estimate_min_m": 0.25,                             # award vs advertised estimate
    "long_years": 10, "long_min_m": 1.0,
    "split_n": 3, "split_window_days": 90, "split_min_total_m": 0.15,
    "conc_min_awards": 20, "conc_min_value_m": 5.0, "conc_share": 0.40,
    "unspec_min_awards": 20, "unspec_share": 0.40,
    "bunch_min_below": 30, "bunch_z": 3.0, "bunch_window": 0.05,
}

TYPE_INFO = {
    "proc_direct": ("Large award without competition",
                    "A contract was awarded by direct award, single tender action or waiver rather than competition. These are lawful in defined circumstances but deserve a reason."),
    "proc_late": ("Published long after the award",
                  "The award notice appeared months after the award date, so the public could not see it in good time."),
    "proc_estimate": ("Award far from the advertised value",
                      "The awarded value is much higher (or lower) than the estimate the buyer first published."),
    "proc_long": ("Very long contract", "A contract running for more than ten years."),
    "proc_split": ("Repeat awards to one supplier in a short window",
                   "The same buyer made several separate awards to the same supplier within a few months, which can be legitimate or can be a contract split to stay below a limit."),
    "proc_conc": ("One supplier dominates a buyer's spend", "A single supplier received a large share of a buyer's awarded value."),
    "proc_unspec": ("Buyer rarely states how it bought", "Many of the buyer's award notices do not say which procedure was used."),
}
SEV_NAMES = {1: "Low", 2: "Medium", 3: "High"}

ORG_RE = re.compile(r"\b(LTD|LIMITED|LLP|LLC|PLC|CIC|C\.I\.C|COUNCIL|NHS|TRUST|UNIVERSITY|COLLEGE|SCHOOL|ACADEMY|FOUNDATION|ASSOCIATION|GROUP|SERVICES|"
                    r"SOLUTIONS|HOLDINGS|PARTNERS|PARTNERSHIP|AUTHORITY|SOCIETY|CHARITY|INC|CORP|CORPORATION|GMBH|BV|AG|SA|LP|COMPANY|CO|CONSULTING|"
                    r"SYSTEMS|TECHNOLOGIES|TECHNOLOGY|ENTERPRISES|INTERNATIONAL|UK|DEPARTMENT|AGENCY|BOARD|INSTITUTE|HOSPITAL|HOUSING|CONSTRUCTION|"
                    r"ENGINEERING|DEVELOPMENTS|PROPERTIES|MANAGEMENT|RECRUITMENT|MEDIA|DIGITAL|LABS|STUDIO|ASSOCIATES|CHURCH|CLUB|FEDERATION)\b", re.I)
SUFFIX_RE = re.compile(r"\b(LTD|LIMITED|PLC|LLP|INC|CORP|CORPORATION|CO|COMPANY|THE|UK|GROUP)\b\.?", re.I)


def norm_name(n):
    n = re.sub(r"[^A-Z0-9 &]", " ", (n or "").upper())
    n = SUFFIX_RE.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def supplier_key(s):
    if s.get("id") and s.get("scheme"):
        return f"{s['scheme']}:{s['id']}"
    return "N:" + norm_name(s.get("name"))


def is_organisation(s):
    return bool(s.get("scheme")) or bool(ORG_RE.search(s.get("name") or ""))


def method_class(pm, pmd):
    d = (pmd or "").lower()
    if "framework" in d or "dynamic purchasing" in d or "dps" in d:
        return "framework"
    if re.search(r"direct award|single tender|waiver|without prior publication|limited tender|negotiated procedure without", d) or pm == "direct":
        return "direct"
    if re.search(r"open procedure|restricted procedure|competitive|competitive flexible|competitive dialogue|negotiated procedure with|innovation partnership", d) or pm == "open":
        return "competitive"
    if re.search(r"not specified|not applicable|other -\s*$|^other\s*-?\s*$", d) or (not d.strip() and pm in (None, "")):
        return "unspecified"
    return "other"


def parse_date(s):
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def prepare(records):
    """Deduplicate awards, keep GBP awards with a value that were *originally published inside the window*.

    A notice tagged `awardUpdate` is an amendment to an older award and is returned in whichever period it was amended.
    Those are counted but not analysed, so the window describes new awards only. Months are the date the notice was
    published (or last amended) on Contracts Finder.
    """
    latest = {}
    for r in records:
        k = r.get("id") or (r.get("ocid"), r.get("title"))
        key = r.get("rel") or r.get("pub") or ""
        if k not in latest or key >= (latest[k].get("rel") or latest[k].get("pub") or ""):
            latest[k] = r
    rels = sorted({(r.get("rel") or r.get("pub") or "")[:7] for r in latest.values() if (r.get("rel") or r.get("pub"))})
    window_start = (rels[0] + "-01") if rels else ""
    out, excluded = [], Counter()
    for r in latest.values():
        if window_start and (r.get("pub") or "") < window_start:
            excluded["amendments to awards first published before the window"] += 1
            continue
        if r.get("av") is None:
            excluded["no value"] += 1
            continue
        if r.get("cur") not in (None, "GBP"):
            excluded["not GBP"] += 1
            continue
        sup = r["sups"][0] if r.get("sups") else {}
        x = dict(r)
        x["mc"] = method_class(r.get("pm"), r.get("pmd"))
        x["skey"] = supplier_key(sup) if sup else None
        x["sname"] = sup.get("name") if sup else None
        x["sorg"] = is_organisation(sup) if sup else False
        x["registered"] = bool(sup.get("scheme"))
        pub, aw, cs, ce = parse_date(r.get("pub")), parse_date(r.get("aw")), parse_date(r.get("cs")), parse_date(r.get("ce"))
        x["lag_aw"] = (pub - aw).days if pub and aw else None
        x["lag_cs"] = (pub - cs).days if pub and cs else None
        x["years"] = (ce - cs).days / 365.25 if cs and ce and ce >= cs else None
        x["bad_dates"] = bool(cs and ce and ce < cs)
        x["m"] = (r.get("rel") or r.get("pub") or "")[:7]
        out.append(x)
    return out, excluded


def m(v):
    return v / 1e6


def fmt(v):
    a = abs(v)
    s = "−" if v < 0 else ""
    return f"{s}£{a/1e9:,.2f}bn" if a >= 1e9 else f"{s}£{a/1e6:,.1f}m" if a >= 1e6 else f"{s}£{a/1e3:,.0f}k"


# ------------------------------------------------------------ flags
def record_flags(rows, p=PARAMS):
    flags = []
    for r in rows:
        v = r["av"]
        base = {"buyer": r["buyer"], "title": r["title"], "value": v, "date": r["pub"], "url": r.get("url"),
                "supplier": r["sname"] if r["sorg"] else None, "method": r.get("pmd")}
        if r["mc"] == "direct" and m(v) >= p["direct_min_m"]:
            sev = 3 if m(v) >= p["direct_sev3_m"] else 2 if m(v) >= p["direct_sev2_m"] else 1
            flags.append({**base, "type": "proc_direct", "sev": sev,
                          "detail": f"{r['buyer']} awarded {fmt(v)} without competition ({r.get('pmd') or 'direct award'}): “{r['title']}”."})
        late = r["lag_aw"] if r["lag_aw"] is not None else r["lag_cs"]
        if late is not None and late >= p["late_days"] and m(v) >= p["late_min_m"]:
            sev = 3 if late >= 365 and m(v) >= 1 else 2 if late >= 180 else 1
            flags.append({**base, "type": "proc_late", "sev": sev,
                          "detail": f"{r['buyer']}: the {fmt(v)} award “{r['title']}” was published {late} days after it was awarded."})
        tv = r.get("tv")
        if tv and tv > 0 and m(max(v, tv)) >= p["estimate_min_m"]:
            ratio = v / tv
            if ratio >= p["estimate_ratio"] or ratio <= 1 / (p["estimate_ratio"] * 5):
                sev = 3 if ratio >= 5 and m(v) >= 1 else 2 if ratio >= 3 else 1
                flags.append({**base, "type": "proc_estimate", "sev": sev,
                              "detail": f"{r['buyer']}: “{r['title']}” was advertised at {fmt(tv)} and awarded at {fmt(v)} ({ratio:.1f}× the estimate)."})
        if r["years"] and r["years"] > p["long_years"] and m(v) >= p["long_min_m"]:
            flags.append({**base, "type": "proc_long", "sev": 1,
                          "detail": f"{r['buyer']}: {fmt(v)} contract “{r['title']}” runs for {r['years']:.0f} years."})
    return flags


def repeat_award_flags(rows, p=PARAMS):
    """Same buyer + same registered/organisation supplier, several non-framework awards inside a short window."""
    by = defaultdict(list)
    for r in rows:
        if r["skey"] and r["sorg"] and r["mc"] != "framework" and r["aw"] and r["av"] > 0:
            by[(r["buyer_id"] or r["buyer"], r["skey"])].append(r)
    flags = []
    for (_, _), lst in by.items():
        lst.sort(key=lambda r: r["aw"])
        i = 0
        while i < len(lst):
            j = i
            while j + 1 < len(lst) and (parse_date(lst[j + 1]["aw"]) - parse_date(lst[i]["aw"])).days <= p["split_window_days"]:
                j += 1
            grp = lst[i:j + 1]
            tot = sum(r["av"] for r in grp)
            if len(grp) >= p["split_n"] and m(tot) >= p["split_min_total_m"]:
                r0 = grp[0]
                flags.append({"type": "proc_split", "sev": 2 if m(tot) >= 1 else 1, "buyer": r0["buyer"], "supplier": r0["sname"], "title": f"{len(grp)} awards", "value": tot,
                              "date": grp[-1]["pub"], "url": None, "method": ", ".join(sorted({g["mc"] for g in grp})),
                              "detail": f"{r0['buyer']} made {len(grp)} separate awards to {r0['sname']} within {p['split_window_days']} days, together worth {fmt(tot)} "
                                        f"(largest {fmt(max(g['av'] for g in grp))})."})
            i = j + 1
    return flags


# ----------------------------------------------------------- buyers
def buyer_table(rows, p=PARAMS):
    by = defaultdict(list)
    for r in rows:
        by[r["buyer"] or "Unknown"].append(r)
    out, flags = [], []
    for b, lst in by.items():
        n, tot = len(lst), sum(r["av"] for r in lst)
        mv = Counter()
        mn = Counter()
        for r in lst:
            mv[r["mc"]] += r["av"]
            mn[r["mc"]] += 1
        sup = defaultdict(float)
        for r in lst:
            if r["skey"] and r["sorg"]:
                sup[r["skey"]] += r["av"]
        top_key = max(sup, key=sup.get) if sup else None
        top_name = next((r["sname"] for r in lst if r["skey"] == top_key), None) if top_key else None
        top_share = sup[top_key] / tot if top_key and tot > 0 else 0
        late = sum(1 for r in lst if (r["lag_aw"] or 0) >= p["late_days"])
        row = {"buyer": b, "n": n, "value": tot, "median": statistics.median([r["av"] for r in lst]),
               "direct_n": mn["direct"], "direct_value": mv["direct"], "unspec_n": mn["unspecified"], "framework_n": mn["framework"],
               "competitive_n": mn["competitive"], "late_n": late,
               "sme_n": sum(1 for r in lst if r.get("sme")), "top_supplier": top_name, "top_share": top_share}
        out.append(row)
        if n >= p["conc_min_awards"] and m(tot) >= p["conc_min_value_m"] and top_share >= p["conc_share"] and top_name:
            flags.append({"type": "proc_conc", "sev": 2 if top_share >= 0.6 else 1, "buyer": b, "supplier": top_name, "title": f"{n} awards", "value": sup[top_key], "date": None, "url": None,
                          "method": None, "detail": f"{b}: {top_name} received {top_share*100:.0f}% ({fmt(sup[top_key])}) of its {fmt(tot)} awarded across {n} awards."})
        if n >= p["unspec_min_awards"] and mn["unspecified"] / n >= p["unspec_share"]:
            flags.append({"type": "proc_unspec", "sev": 2 if mn["unspecified"] / n >= 0.7 else 1, "buyer": b, "supplier": None, "title": f"{n} awards", "value": tot, "date": None, "url": None,
                          "method": None, "detail": f"{b}: {mn['unspecified']} of {n} award notices ({mn['unspecified']/n*100:.0f}%) do not say which procurement procedure was used."})
    out.sort(key=lambda r: -r["value"])
    return out, flags


# ------------------------------------------------------------ bunching
def bunching(rows, p=PARAMS):
    """Excess of awards just below round-number values, compared with just above (equal log-width windows)."""
    vals = [r["av"] for r in rows if r["av"] > 0]
    w = p["bunch_window"]
    cands = [x * 1000 for x in (10, 20, 25, 30, 40, 50, 60, 75, 100, 150, 200, 250, 300, 400, 500, 750)] + [1e6, 2e6, 5e6]
    res = []
    for X in cands:
        below = sum(1 for v in vals if X / (1 + w) <= v < X)
        above = sum(1 for v in vals if X <= v < X * (1 + w))
        n = below + above
        if n < 30:
            continue
        p0 = 0.55          # equal log-width windows; allow a little extra mass below because values thin out upwards
        z = (below - n * p0) / math.sqrt(n * p0 * (1 - p0))
        res.append({"threshold": X, "below": below, "above": above, "ratio": below / above if above else None, "z": round(z, 1), "flag": bool(z >= p["bunch_z"] and below >= p["bunch_min_below"])})
    res.sort(key=lambda r: -r["z"])
    return res


# ----------------------------------------------------------- summary
def summarise(rows, excluded):
    tot = sum(r["av"] for r in rows)
    months = sorted({r["m"] for r in rows if r["m"]})
    by_m = defaultdict(lambda: defaultdict(float))
    by_mn = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_m[r["m"]][r["mc"]] += r["av"]
        by_mn[r["m"]][r["mc"]] += 1
    cls = Counter()
    clsn = Counter()
    cat = defaultdict(float)
    cpv = defaultdict(lambda: [0, 0.0, ""])
    for r in rows:
        cls[r["mc"]] += r["av"]
        clsn[r["mc"]] += 1
        cat[r.get("cat") or "unknown"] += r["av"]
        k = (r.get("cpv") or "")[:2]
        c = cpv[k]
        c[0] += 1
        c[1] += r["av"]
        c[2] = c[2] or (r.get("cpvd") or "")
    sup = defaultdict(lambda: {"name": None, "n": 0, "value": 0.0, "buyers": set(), "registered": False})
    for r in rows:
        if r["skey"] and r["sorg"]:
            s = sup[r["skey"]]
            s["name"] = s["name"] or r["sname"]
            s["n"] += 1
            s["value"] += r["av"]
            s["buyers"].add(r["buyer"])
            s["registered"] = s["registered"] or r["registered"]
    top_sup = sorted(sup.values(), key=lambda s: -s["value"])[:40]
    n_ind = sum(1 for r in rows if not r["sorg"])
    quality = {"awards": len(rows), "excluded": dict(excluded), "unspecified_method": clsn["unspecified"], "zero_or_negative_value": sum(1 for r in rows if r["av"] <= 0),
               "no_supplier_registration": sum(1 for r in rows if not r["registered"]), "not_named_as_organisation": n_ind,
               "no_tender_estimate": sum(1 for r in rows if not r.get("tv")), "bad_dates": sum(1 for r in rows if r["bad_dates"]),
               "number_of_bidders_published": 0}
    return {
        "total_value": tot, "n": len(rows), "median": statistics.median([r["av"] for r in rows]) if rows else 0, "months": months,
        "by_month_value": {mm: dict(by_m[mm]) for mm in months}, "by_month_n": {mm: dict(by_mn[mm]) for mm in months},
        "by_class": {k: {"n": clsn[k], "value": cls[k]} for k in cls}, "by_category": dict(cat),
        "cpv": sorted([{"division": k, "n": v[0], "value": v[1], "label": v[2]} for k, v in cpv.items() if k], key=lambda x: -x["value"])[:30],
        "top_suppliers": [{"name": s["name"], "n": s["n"], "value": s["value"], "buyers": len(s["buyers"]), "registered": s["registered"]} for s in top_sup],
        "quality": quality,
    }


def checks(rows, summary, raw_count):
    cks = []
    ids = [r.get("id") for r in rows]
    cks.append(A._check("proc_unique", "Contracts Finder: each award appears once after removing updates (count)", [("awards", len(set(ids)), len(ids))], 0))
    tv = summary["total_value"]
    cks.append(A._check("proc_class", "Contracts Finder: value by procedure type adds up to the total (£)", [("all awards", tv, sum(v["value"] for v in summary["by_class"].values()))], 1))
    mv = sum(sum(d.values()) for d in summary["by_month_value"].values())
    cks.append(A._check("proc_month", "Contracts Finder: monthly values add up to the total (£)", [("all awards", tv, mv)], 1))
    for c in cks:
        c["source"] = "Contracts Finder"
    return cks


def build(records, top_flags=300):
    rows, excluded = prepare(records)
    summary = summarise(rows, excluded)
    flags = record_flags(rows) + repeat_award_flags(rows)
    buyers, bflags = buyer_table(rows)
    flags += bflags
    flags.sort(key=lambda f: (-f["sev"], -(f["value"] or 0)))
    counts = Counter(f["type"] for f in flags)
    sev = Counter(f["sev"] for f in flags)
    bunch = bunching(rows)
    for f in flags:
        f["value_fmt"] = fmt(f["value"] or 0)
    return {"summary": summary, "buyers": buyers[:200], "flags": flags[:top_flags], "flag_counts": dict(counts), "sev_counts": {str(k): v for k, v in sev.items()},
            "bunching": bunch, "types": {k: {"title": v[0], "text": v[1]} for k, v in TYPE_INFO.items()}, "params": PARAMS}, checks(rows, summary, len(records))
