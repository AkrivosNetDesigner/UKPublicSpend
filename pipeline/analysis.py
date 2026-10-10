"""Anomaly / integrity tests for UK public spending data.

Everything here is a *screening* test. A flag means "this is unusual enough that
a human should look", never "this is fraud". All thresholds live in PARAMS and
are published on the site so anyone can challenge them.

Amounts in the PSS database are £ thousand; PARAMS thresholds are £ million and
converted internally.
"""
import math
import statistics
from collections import defaultdict

PARAMS = {
    "materiality_floor_m": 20,        # denominator floor when measuring relative change
    "jump_min_change_m": 50,          # a change smaller than this is never flagged
    "jump_z": 4.0,                    # robust (median/MAD) z-score vs peer lines
    "jump_mad_floor": 0.05,           # stops a very quiet peer group inflating z
    "jump_peer_min_obs": 30,
    "revision_min_change_m": 50,
    "revision_min_rel": 0.10,
    "newline_min_m": 100,             # line appears from nothing / drops to nothing
    "signflip_min_m": 20,
    "identical_min_m": 5,             # same amount to the £thousand two years running
    "round_min_m": 10,                # amount is an exact whole number of £ millions
    "trend_min_cagr": 0.30,
    "trend_min_latest_m": 200,
    "benford_min_n": 300,
    "opaque_share_flag": 0.30,
    "opaque_rise_pp": 5.0,
    "function_z": 3.0,
    "function_min_change_bn": 1.0,
    "check_tolerance_per_item": 0.06, # rounding allowance for 1-dp £bn tables
}

OPAQUE_GROUPS = {
    "UNALLOCATED FUNDS - RESOURCE", "UNALLOCATED FUNDS - CAPITAL",
    "TAKE UP OF PROVISIONS", "OTHER RESOURCE", "OTHER CAPITAL",
}

TYPE_INFO = {
    "jump": ("Unusual year-on-year change",
             "The line moved far more than comparable lines (same budget type and economic category) normally do."),
    "revision": ("Restated after publication",
                 "The Treasury later published a materially different figure for the same line and year."),
    "new_line": ("Line appears from nothing",
                 "A spending line with no spend the year before carries a large amount."),
    "closed_line": ("Line vanishes",
                    "A large spending line falls to nothing the following year."),
    "sign_flip": ("Switches between spend and income",
                  "The net figure changes sign, e.g. from net spending to net receipt."),
    "identical": ("Identical to the pound-thousand two years running",
                  "Real outturn almost never repeats exactly; this can indicate a budget carried over rather than measured."),
    "round": ("Exactly round amount",
              "An outturn that is an exact whole number of £ millions is unusual in accrued accounts."),
    "trend": ("Sustained rapid growth",
              "Four consecutive annual increases at a high compound rate."),
    "function_jump": ("Unusual change in a function total",
                      "A function (health, defence...) moved far more than its own history suggests."),
}
SEV_POINTS = {1: 1, 2: 3, 3: 6}


def M(x):  # £m -> £thousand
    return x * 1000.0


def robust_center_spread(xs):
    med = statistics.median(xs)
    mad = statistics.median([abs(x - med) for x in xs])
    return med, mad


# ---------------------------------------------------------------- segments
def clean_name(name, code):
    n = (name or code).replace("\xa0", " ")
    if n.startswith(code):
        n = n[len(code):].lstrip(" -")
    return " ".join(n.split()) or code


def build_segments(rows):
    """code -> {name, vals{year:£k}, dept{year:dept}, group, ctrl}"""
    acc = defaultdict(lambda: {"vals": defaultdict(float), "deptamt": defaultdict(lambda: defaultdict(float)),
                               "group": defaultdict(float), "ctrl": defaultdict(float), "name": None})
    for r in rows:
        s = acc[r["code"]]
        s["vals"][r["year"]] += r["amount"]
        s["deptamt"][r["year"]][r["dept"]] += abs(r["amount"])
        s["group"][r["group"]] += abs(r["amount"])
        s["ctrl"][r["ctrl"]] += abs(r["amount"])
        s["name"] = r["name"]
    out = {}
    for code, s in acc.items():
        out[code] = {
            "name": clean_name(s["name"], code),
            "vals": dict(s["vals"]),
            "dept": {y: max(d, key=d.get) for y, d in s["deptamt"].items()},
            "group": max(s["group"], key=s["group"].get),
            "ctrl": max(s["ctrl"], key=s["ctrl"].get),
        }
    return out


def _flag(code, seg, year, typ, sev, value, prev, detail, extra=None):
    f = {"code": code, "name": seg["name"], "dept": seg["dept"].get(year) or next(iter(seg["dept"].values()), ""),
         "year": year, "type": typ, "sev": sev, "value": value, "prev": prev, "detail": detail}
    if extra:
        f.update(extra)
    return f


def fmt_m(k):
    m = k / 1000.0
    sign = "-" if m < 0 else ""
    m = abs(m)
    return f"{sign}£{m:,.0f}m" if m < 1000 else f"{sign}£{m/1000:,.2f}bn"


def segment_flags(segs, years, params=PARAMS):
    p = params
    flags = []
    # ---- peer distribution of relative change
    peer = defaultdict(list)
    allobs = []
    trans = list(zip(years, years[1:]))
    for code, s in segs.items():
        for a, b in trans:
            x0, x1 = s["vals"].get(a, 0.0), s["vals"].get(b, 0.0)
            if max(abs(x0), abs(x1)) < M(5):
                continue
            r = _rel(x0, x1, p)
            peer[(s["ctrl"], s["group"])].append(r)
            allobs.append(r)
    stats = {}
    gmed, gmad = robust_center_spread(allobs) if allobs else (0, 0)
    for k, xs in peer.items():
        stats[k] = robust_center_spread(xs) if len(xs) >= p["jump_peer_min_obs"] else (gmed, gmad)

    for code, s in segs.items():
        v = s["vals"]
        med, mad = stats.get((s["ctrl"], s["group"]), (gmed, gmad))
        mad = max(mad, p["jump_mad_floor"])
        for a, b in trans:
            x0, x1 = v.get(a, 0.0), v.get(b, 0.0)
            d = x1 - x0
            absd = abs(d)
            # new / closed lines
            if x0 == 0 and abs(x1) >= M(p["newline_min_m"]):
                sev = 3 if abs(x1) >= M(2000) else 2 if abs(x1) >= M(500) else 1
                flags.append(_flag(code, s, b, "new_line", sev, x1, x0,
                                   f"No spend in {a}, then {fmt_m(x1)} in {b}."))
                continue
            if x1 == 0 and abs(x0) >= M(p["newline_min_m"]):
                sev = 3 if abs(x0) >= M(2000) else 2 if abs(x0) >= M(500) else 1
                flags.append(_flag(code, s, b, "closed_line", sev, x1, x0,
                                   f"{fmt_m(x0)} in {a}, then nothing in {b}."))
                continue
            if x0 * x1 < 0 and min(abs(x0), abs(x1)) >= M(p["signflip_min_m"]):
                sev = 2 if min(abs(x0), abs(x1)) >= M(250) else 1
                flags.append(_flag(code, s, b, "sign_flip", sev, x1, x0,
                                   f"Net {fmt_m(x0)} in {a} became {fmt_m(x1)} in {b}."))
            # jump
            if absd >= M(p["jump_min_change_m"]):
                r = _rel(x0, x1, p)
                raw = d / max(abs(x0), M(p["materiality_floor_m"]))
                z = 0.6745 * (r - med) / mad
                if abs(z) >= p["jump_z"]:
                    sev = 3 if abs(z) >= 10 and absd >= M(1000) else 2 if abs(z) >= 6 and absd >= M(250) else 1
                    flags.append(_flag(code, s, b, "jump", sev, x1, x0,
                                       f"Changed by {'+' if d >= 0 else ''}{fmt_m(d)} ({raw*100:+,.0f}% of the earlier amount, or of £{p['materiality_floor_m']}m if smaller) from {a} to {b}; "
                                       f"comparable lines typically move {med*100:,.0f}% (score {abs(z):.1f}).",
                                       {"z": round(z, 1)}))
            # identical
            if abs(x0) >= M(p["identical_min_m"]) and x0 == x1:
                sev = 2 if abs(x0) >= M(100) else 1
                flags.append(_flag(code, s, b, "identical", sev, x1, x0,
                                   f"{fmt_m(x1)} in both {a} and {b}, identical to the £thousand."))
        # round amounts
        for y in years:
            x = v.get(y, 0.0)
            if abs(x) >= M(p["round_min_m"]) and abs(x) % 1000 == 0:
                flags.append(_flag(code, s, y, "round", 1, x, None,
                                   f"{fmt_m(x)} is an exact whole number of £ millions."))
        # sustained growth
        series = [v.get(y, 0.0) for y in years]
        if len(series) >= 5 and all(series[i] > 0 for i in range(len(series))) and \
                all(series[i + 1] > series[i] for i in range(len(series) - 1)) and \
                series[-1] >= M(p["trend_min_latest_m"]):
            cagr = (series[-1] / series[0]) ** (1 / (len(series) - 1)) - 1
            if cagr >= p["trend_min_cagr"]:
                flags.append(_flag(code, s, years[-1], "trend", 2 if series[-1] >= M(1000) else 1,
                                   series[-1], series[0],
                                   f"Rose every year from {fmt_m(series[0])} to {fmt_m(series[-1])} "
                                   f"({cagr*100:,.0f}% a year compounded)."))
    return flags


def _rel(x0, x1, p):
    r = (x1 - x0) / max(abs(x0), M(p["materiality_floor_m"]))
    return max(-10.0, min(10.0, r))


# --------------------------------------------------------------- revisions
def revision_flags(releases, segs_by_release, params=PARAMS):
    """releases: ordered list of keys e.g. ['2024','2025','2026']."""
    p = params
    flags = []
    for ra, rb in zip(releases, releases[1:]):
        A, B = segs_by_release[ra], segs_by_release[rb]
        years_a = {y for s in A.values() for y in s["vals"]}
        years_b = {y for s in B.values() for y in s["vals"]}
        for y in sorted(years_a & years_b):
            for code in set(A) | set(B):
                sa, sb = A.get(code), B.get(code)
                x0 = sa["vals"].get(y, 0.0) if sa else 0.0
                x1 = sb["vals"].get(y, 0.0) if sb else 0.0
                d = x1 - x0
                if abs(d) < M(p["revision_min_change_m"]):
                    continue
                rel = abs(d) / max(abs(x0), M(p["materiality_floor_m"]))
                if rel < p["revision_min_rel"]:
                    continue
                sev = 3 if rel >= 0.5 and abs(d) >= M(1000) else 2 if rel >= 0.25 and abs(d) >= M(250) else 1
                seg = sb or sa
                note, structural = "", False
                if sa and sb and sa["dept"].get(y) != sb["dept"].get(y):
                    note = (f" The line moved department ({sa['dept'].get(y)} → {sb['dept'].get(y)}), "
                            f"which may explain it.")
                    sev = 1
                elif not sa or not sb:
                    structural, sev = True, 1
                    note = (" The line code did not exist in the earlier release; it may be a re-coding or a move between "
                            "departments rather than new spending." if not sa else
                            " The line code no longer exists in the later release; it may have been re-coded or moved "
                            "rather than stopped.")
                flags.append(_flag(code, seg, y, "revision", sev, x1, x0,
                                   f"{y} was {fmt_m(x0)} in the July {ra} release and {fmt_m(x1)} in July {rb} "
                                   f"({'+' if d >= 0 else ''}{fmt_m(d)}).{note}",
                                   {"from_release": ra, "to_release": rb, "delta": d, "structural": structural}))
    # context: do all the added/removed line codes net out across the whole database?
    tot = defaultdict(lambda: [0.0, 0.0])
    for ra, rb in zip(releases, releases[1:]):
        A, B = segs_by_release[ra], segs_by_release[rb]
        for y in sorted({y for s in A.values() for y in s["vals"]} & {y for s in B.values() for y in s["vals"]}):
            for code in set(A) | set(B):
                if (code in A) != (code in B):
                    x = (B[code]["vals"].get(y, 0.0) if code in B else -A[code]["vals"].get(y, 0.0))
                    tot[(ra, rb, y)][0 if x > 0 else 1] += x
    for f in flags:
        if f.get("structural"):
            added, removed = tot[(f["from_release"], f["to_release"], f["year"])]
            f["detail"] += (f" Across the whole database, line codes added between these releases total {fmt_m(added)} "
                            f"and removed {fmt_m(removed)} for {f['year']} (net {fmt_m(added + removed)}).")
    return mark_offsets(flags)


def mark_offsets(flags, tol=0.15):
    """Revisions that cancel out inside one department/year are re-allocations
    between lines, not a change in what was spent. Pair each with the closest
    opposite-signed revision (within `tol`) and downgrade both to severity 1."""
    groups = defaultdict(list)
    for f in flags:
        groups[(f["dept"], f["year"], f["from_release"], f["to_release"])].append(f)
    for fl in groups.values():
        pos = sorted([f for f in fl if f["delta"] > 0], key=lambda f: -f["delta"])
        neg = sorted([f for f in fl if f["delta"] < 0], key=lambda f: f["delta"])
        used = set()
        for p_ in pos:
            best = None
            for n_ in neg:
                if id(n_) in used:
                    continue
                gap = abs(p_["delta"] + n_["delta"]) / p_["delta"]
                if gap <= tol and (best is None or gap < best[0]):
                    best = (gap, n_)
            if best:
                n_ = best[1]
                used.add(id(n_))
                for f, other in ((p_, n_), (n_, p_)):
                    f["offset_with"] = other["code"]
                    f["sev"] = 1
                    f["detail"] += (f" This is cancelled out by an opposite change of {fmt_m(other['delta'])} on "
                                    f"'{other['name']}' in the same department and year, so it looks like money "
                                    f"re-allocated between lines, not a different total.")
    return flags


def revision_summary(releases, rows_by_release, latest):
    """Like-for-like dept totals per release/year: segments regrouped by their latest-release department."""
    latest_dept = {}
    for r in rows_by_release[latest]:
        latest_dept[r["code"]] = r["dept"]
    out = defaultdict(lambda: defaultdict(dict))  # dept -> year -> release -> £k
    for rel in releases:
        tot = defaultdict(float)
        for r in rows_by_release[rel]:
            d = latest_dept.get(r["code"], r["dept"])
            tot[(d, r["year"])] += r["amount"]
            tot[("All departments", r["year"])] += r["amount"]
        for (d, y), v in tot.items():
            out[d][y][rel] = v
    return {d: {y: rels for y, rels in ys.items() if len(rels) > 1} for d, ys in out.items()}


# --------------------------------------------------------- score & rank
def rank_segments(flags, segs):
    by = defaultdict(list)
    for f in flags:
        by[f["code"]].append(f)
    ranked = []
    for code, fl in by.items():
        types = sorted({f["type"] for f in fl})
        score = sum(SEV_POINTS[f["sev"]] for f in fl) + 2 * (len(types) - 1)
        vals = segs[code]["vals"] if code in segs else {}
        mag = max([abs(x) for x in vals.values()] +
                  [abs(f["value"]) for f in fl] + [abs(f["prev"]) for f in fl if f["prev"] is not None], default=0)
        ranked.append({"code": code, "name": fl[0]["name"], "dept": fl[0]["dept"], "score": score,
                       "types": types, "n": len(fl), "max_m": round(mag / 1000, 1)})
    ranked.sort(key=lambda r: (-r["score"], -r["max_m"]))
    return ranked


# ------------------------------------------------------------- benford
BENFORD = [math.log10(1 + 1 / d) for d in range(1, 10)]


def first_digit(x):
    x = abs(x)
    if x <= 0:
        return None
    while x >= 10:
        x /= 10
    while x < 1:
        x *= 10
    return int(x)


def benford_by_dept(rows, params=PARAMS):
    amounts = defaultdict(list)
    for r in rows:
        if r["amount"]:
            amounts[r["dept"]].append(r["amount"])
    out = []
    amounts["All departments"] = [a for v in list(amounts.values()) for a in v]
    for d, xs in amounts.items():
        n = len(xs)
        if n < params["benford_min_n"]:
            continue
        cnt = [0] * 9
        for x in xs:
            cnt[first_digit(x) - 1] += 1
        freq = [c / n for c in cnt]
        mad = sum(abs(f - e) for f, e in zip(freq, BENFORD)) / 9
        label = ("close" if mad <= 0.006 else "acceptable" if mad <= 0.012
                 else "marginal" if mad <= 0.015 else "nonconforming")
        out.append({"dept": d, "n": n, "mad": round(mad, 4), "label": label, "reliable": n >= 1000,
                    "freq": [round(f, 4) for f in freq]})
    out.sort(key=lambda r: -r["mad"])
    return {"expected": [round(b, 4) for b in BENFORD], "depts": out}


# --------------------------------------------------------------- opacity
def opacity(rows, years, params=PARAMS):
    pos = defaultdict(lambda: defaultdict(float))
    opq = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["amount"] > 0:
            pos[r["dept"]][r["year"]] += r["amount"]
            if r["group"] in OPAQUE_GROUPS:
                opq[r["dept"]][r["year"]] += r["amount"]
    out = []
    for d in pos:
        shares = [opq[d][y] / pos[d][y] if pos[d].get(y) else None for y in years]
        tot = [pos[d].get(y, 0) / 1000 for y in years]
        first = next((s for s in shares if s is not None), None)
        last = next((s for s in reversed(shares) if s is not None), None)
        rise = (last - first) * 100 if first is not None and last is not None else 0
        flagged = last is not None and last >= params["opaque_share_flag"] and rise >= params["opaque_rise_pp"]
        out.append({"dept": d, "share": [None if s is None else round(s, 4) for s in shares],
                    "gross_m": [round(t, 1) for t in tot], "rise_pp": round(rise, 1), "flag": bool(flagged)})
    out.sort(key=lambda r: -(r["share"][-1] or 0))
    return out


# ---------------------------------------------------------- functions
def function_flags(years, rows, label="real terms", params=PARAMS):
    """rows: [{label, level, values}] in £bn (real). Flags unusual YoY moves vs own history."""
    flags = []
    for r in rows:
        v = r["values"]
        g = []
        for i in range(1, len(v)):
            if v[i] is None or v[i - 1] in (None, 0):
                g.append(None)
            else:
                g.append((v[i] - v[i - 1]) / abs(v[i - 1]))
        ok = [x for x in g if x is not None]
        if len(ok) < 8:
            continue
        med, mad = robust_center_spread(ok)
        mad = max(mad, 0.01)
        for i, x in enumerate(g):
            if x is None:
                continue
            z = 0.6745 * (x - med) / mad
            chg = v[i + 1] - v[i]
            if abs(z) >= params["function_z"] and abs(chg) >= params["function_min_change_bn"]:
                sev = 3 if abs(z) >= 8 and abs(chg) >= 20 else 2 if abs(z) >= 5 and abs(chg) >= 5 else 1
                flags.append({"label": r["label"], "level": r["level"], "year": years[i + 1],
                              "type": "function_jump", "sev": sev, "z": round(z, 1),
                              "value": v[i + 1], "prev": v[i],
                              "detail": f"{r['label']} changed by {'+' if chg >= 0 else ''}£{chg:,.1f}bn "
                                        f"({x*100:+.1f}%) in {label} between {years[i]} and {years[i+1]}; its typical year is "
                                        f"{med*100:+.1f}% (score {abs(z):.1f})."})
    flags.sort(key=lambda f: (-f["sev"], -abs(f["z"])))
    return flags


# ---------------------------------------------------- integrity checks
def _check(cid, title, rows, tol, note=""):
    """rows: [(year, expected, actual)] -> check dict."""
    worst = max((abs(a - e) for _, e, a in rows), default=0)
    bad = [(y, e, a) for y, e, a in rows if abs(a - e) > tol]
    return {"id": cid, "title": title, "status": "pass" if not bad else "warn",
            "tolerance": tol, "worst_gap": round(worst, 3), "note": note,
            "rows": [{"year": y, "expected": round(e, 3), "actual": round(a, 3), "gap": round(a - e, 3)}
                     for y, e, a in rows]}


def integrity_checks(t11, t41, f42, f43, region, db_pivot, params=PARAMS):
    checks = []
    yrs, lines = t11
    def line(label, section=None):
        for l in lines:
            if l["label"].lower() == label.lower() and (section is None or l["section"].lower() == section.lower()):
                return l["values"]
        raise KeyError(label)

    rdel = line("Total resource DEL"); ramE = line("Total resource AME"); cur = line("Public sector current expenditure")
    checks.append(_check("t11_current", "Table 1.1: resource DEL + resource AME = public sector current expenditure (£m)",
                         [(y, c, a + b) for y, a, b, c in zip(yrs, rdel, ramE, cur)], 3))
    gi = line("Public sector gross investment (4)".replace(" (4)", ""))
    tme = line("TOTAL MANAGED EXPENDITURE")
    checks.append(_check("t11_tme", "Table 1.1: current expenditure + gross investment = Total Managed Expenditure (£m)",
                         [(y, t, c + g) for y, c, g, t in zip(yrs, cur, gi, tme)], 3))
    dl, da, oa = line("Total DEL"), line("Departmental AME"), line("Other AME")
    checks.append(_check("t11_split", "Table 1.1: DEL + departmental AME + other AME = Total Managed Expenditure (£m)",
                         [(y, t, a + b + c) for y, a, b, c, t in zip(yrs, dl, da, oa, tme)], 3))
    # table 4.1 vs 1.1
    agg = {a["year"]: a for a in t41}
    checks.append(_check("t41_vs_t11", "Table 4.1 TME agrees with Table 1.1 TME (£bn; 4.1 rounded to £0.1bn)",
                         [(y, t / 1000, agg[y]["tme"]) for y, t in zip(yrs, tme) if y in agg], 0.06))
    # table 4.2: functions sum
    for tag, (fy, frows), unit in (("4.2 nominal", f42, "nominal"), ("4.3 real", f43, "real terms")):
        idx = {r["label"]: r for r in frows}
        top = [r for r in frows if r["level"] == 0 and r["label"][:2].strip(". ").rstrip(".").isdigit()]
        eu = idx.get("EU transactions")
        svc = idx["Public sector expenditure on services"]
        tmerow = idx["Total Managed Expenditure"]
        adj = idx["Accounting adjustments"]
        tol = params["check_tolerance_per_item"] * (len(top) + 1)
        sums = []
        for i, y in enumerate(fy):
            s = sum(r["values"][i] or 0 for r in top) + ((eu["values"][i] or 0) if eu else 0)
            sums.append((y, svc["values"][i], s))
        checks.append(_check(f"t{tag[:3].replace('.','')}_sum", f"Table {tag}: ten functions + EU transactions = expenditure on services (£bn, {unit})", sums, tol))
        checks.append(_check(f"t{tag[:3].replace('.','')}_tme", f"Table {tag}: services + accounting adjustments = Total Managed Expenditure (£bn, {unit})",
                             [(y, tmerow["values"][i], svc["values"][i] + adj["values"][i]) for i, y in enumerate(fy)], 0.15))
        for parent in ("1. General public services", "4. Economic affairs"):
            kids = [r for r in frows if r["parent"] == parent and r["level"] == 1]
            prow = idx[parent]
            checks.append(_check(f"t{tag[:3].replace('.','')}_{parent[0]}", f"Table {tag}: sub-items of '{parent[3:]}' sum to the function (£bn, {unit})",
                                 [(y, prow["values"][i], sum(k["values"][i] or 0 for k in kids)) for i, y in enumerate(fy)],
                                 params["check_tolerance_per_item"] * (len(kids) + 1) + 0.05,
                                 "Sub-items listed under 'of which' are not always exhaustive, so a gap can be legitimate."))
    # real/nominal deflator consistency
    fy, n_rows = f42; _, r_rows = f43
    nmap = {r["label"]: r for r in n_rows}
    ratio_rows = []
    for i, y in enumerate(fy):
        ratios = []
        for r in r_rows:
            n = nmap.get(r["label"])
            if n and (n["values"][i] or 0) >= 30 and r["values"][i]:
                ratios.append(r["values"][i] / n["values"][i])
        if len(ratios) >= 3:
            med = statistics.median(ratios)
            ratio_rows.append((y, med, max(ratios, key=lambda x: abs(x - med))))
    checks.append(_check("deflator", "Real ÷ nominal ratio is the same price adjustment for every large function (largest outlier vs median)",
                         ratio_rows, 0.004, "Both tables should apply one GDP deflator per year; a gap means a row was adjusted differently."))
    # regional
    ry, rrows = region["abs"]
    lab = {r["label"]: r["values"] for r in rrows}
    eng = [r for r in rrows if r["label"] in (
        "North East", "North West", "Yorkshire and The Humber", "East Midlands", "West Midlands", "East", "London", "South East", "South West")]
    checks.append(_check("reg_eng", "Table 9.1a: nine English regions sum to England (£m)",
                         [(y, lab["Total England"][i], sum(r["values"][i] for r in eng)) for i, y in enumerate(ry)], 12))
    checks.append(_check("reg_uk", "Table 9.1a: England + Scotland + Wales + Northern Ireland = UK identifiable (£m)",
                         [(y, lab["UK identifiable expenditure"][i],
                           lab["Total England"][i] + lab["Scotland"][i] + lab["Wales"][i] + lab["Northern Ireland"][i]) for i, y in enumerate(ry)], 12))
    checks.append(_check("reg_ident", "Table 9.1a: UK identifiable + outside UK = total identifiable (£m)",
                         [(y, lab["Total identifiable expenditure"][i], lab["UK identifiable expenditure"][i] + lab["Outside UK"][i]) for i, y in enumerate(ry)], 12))
    # cross-chapter
    t9 = region.get("tme")
    if t9:
        tmeby = dict(zip(yrs, tme))
        rows = [(y, tmeby[y], v) for y, v in zip(t9["years"], t9["values"]) if y in tmeby]
        checks.append(_check("reg_vs_t11", "Chapter 9 TME agrees with Table 1.1 TME (£m) - different tables, same total",
                             rows, 20, "Small gaps arise because Chapter 9 is compiled from a slightly different data cut."))
    # database coverage vs Table 1.1
    if db_pivot:
        dbr = db_pivot["dbtotals"]
        rows = []
        for y in yrs:
            if y in dbr:
                rows.append((y, rdel[yrs.index(y)] + line("Total capital DEL")[yrs.index(y)], dbr[y]["DEL"] / 1000))
        checks.append(_check("db_cov", "Database DEL total vs Table 1.1 total DEL (£m)",
                             rows, 1e12, "Documented gap: the database omits the Security and Intelligence Agencies and the cost of military operations, "
                                          "so it is expected to be lower than Table 1.1. Shown for transparency; it is not a failure."))
        checks[-1]["status"] = "info"
    return checks
