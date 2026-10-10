"""DWP "Fraud and error in the benefit system" statistics (Great Britain).

Source: the data-table workbooks DWP publishes on GOV.UK each May/June. We read three releases (FYE 2024,
2025, 2026) so we can see how earlier estimates were later restated. Each year has three columns:
central estimate, lower and upper bound of the confidence interval. Amounts are in £, percentages in %.
"""
import re
import statistics

import openpyxl

import analysis as A

NOTE_RE = re.compile(r"\s+note\s+[\d, ]+$")
FYE_RE = re.compile(r"\s*FYE\s+(\d{4})(.*)", re.S)
MEAS_RE = re.compile(r"Last measured:\s*(.+)", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december"])}


def _rows(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        ws.reset_dimensions()
        return [tuple(r) + (None,) * 8 for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None            # 'x' (not available), 'w' (suppressed), 'z' (not applicable)


def fy_label(end_year):
    return f"{end_year - 1}-{str(end_year)[2:]}"


def columns(rows):
    """FYE column groups from the header row: [{'fye': 2026, 'revised': False, 'c': first_col_of_triple}]."""
    for r in rows[:8]:
        out = []
        for j, c in enumerate(r):
            m = FYE_RE.match(str(c)) if c is not None else None
            if m:
                out.append({"fye": int(m.group(1)), "revised": "revised" in m.group(2).lower(), "c": j - 1})
        if out:
            return out
    return []


def parse_table(path, sheet, scale=1.0, headline_only=False):
    """-> {'cols': [...], 'blocks': [{'benefit', 'measured', 'lines': {label: [(est, lo, hi) per col]}}]}"""
    rows = _rows(path, sheet)
    cols = columns(rows)
    blocks, cur, section = [], None, None
    for r in rows:
        c1 = str(r[1]).strip() if r[1] not in (None, "") else ""
        c2 = str(r[2]).strip() if r[2] not in (None, "") else ""
        vals = [[_num(r[c["c"] + k]) if c["c"] + k < len(r) else None for k in range(3)] for c in cols]
        has = any(v is not None for t in vals for v in t)
        if c1.lower().startswith("last measured"):
            if cur is not None:
                cur["measured"] = MEAS_RE.match(c1).group(1).strip()
            if c2 and has:
                cur["lines"][c2] = [tuple(None if v is None else v * scale for v in t) for t in vals]
            continue
        if c1 and c2:
            cur = {"benefit": NOTE_RE.sub("", c1).strip(), "measured": None, "lines": {}, "section": section}
            blocks.append(cur)
        elif c1 and not c2:
            if re.match(r"(?i)(benefits? |unreviewed)", c1) and not has:
                section = c1   # "Benefits reviewed this year", "Benefits never reviewed" ...
            elif not has:      # Table 14 style: the benefit name has its own header row, lines follow beneath
                cur = {"benefit": NOTE_RE.sub("", c1).strip(), "measured": None, "lines": {}, "section": section}
                blocks.append(cur)
            continue
        if c2 and not c1 and not has and sheet == "Table_12":
            section = c2       # "Headline" / "De minimis"
            continue
        if c2 and cur is not None and (has or c2):
            if headline_only and section not in (None, "Headline") and sheet == "Table_12":
                continue
            if has:
                cur["lines"][c2] = [tuple(None if v is None else v * scale for v in t) for t in vals]
    return {"cols": cols, "blocks": [b for b in blocks if b["lines"]]}


def parse_reasons(path, sheet="Table_3"):
    """Error reasons per benefit for the newest year (first column group of 4 x 3 columns)."""
    rows = _rows(path, sheet)
    hdr = next(r for r in rows[:8] if any(c and "Total Overpayments" in str(c) for c in r))
    groups = [(j, str(c).split("(")[0].strip()) for j, c in enumerate(hdr) if c and "(£m" in str(c)][:4]   # newest year only
    out, cur = [], None
    for r in rows:
        c1 = str(r[1]) if r[1] not in (None, "") else ""
        if "note" in c1 and c1.strip():
            cur = {"benefit": NOTE_RE.sub("", c1.strip()).strip(), "reasons": []}
            out.append(cur)
            continue
        if cur is None or not c1.strip():
            continue
        vals = {nm: tuple(None if _num(r[j + k]) is None else _num(r[j + k]) / 1e6 for k in range(3)) for j, nm in groups}
        if all(v[0] is None for v in vals.values()):
            continue
        cur["reasons"].append({"reason": c1.strip(), "level": 1 if c1.startswith("   ") else 0, "values": vals})
    return out


def block(tbl, name):
    for b in tbl["blocks"]:
        if b["benefit"].lower().startswith(name.lower()):
            return b
    raise KeyError(name)


def series(tbl, name, line, revised=True):
    """chronological [{'fye', 'est', 'lo', 'hi'}]; uses the 'revised' column where there is one."""
    b = block(tbl, name)
    vals = b["lines"][line]
    pick = {}
    for c, v in zip(tbl["cols"], vals):
        if c["fye"] in pick and not (revised and c["revised"]):
            continue
        if c["fye"] in pick and pick[c["fye"]][1] and not c["revised"]:
            continue
        pick[c["fye"]] = (c["revised"], v)
    return [{"fye": y, "est": pick[y][1][0], "lo": pick[y][1][1], "hi": pick[y][1][2]} for y in sorted(pick)]


def parse_measured_end(text):
    """'November 2024 - October 2025' -> (2025, 10); returns None if not parseable."""
    if not text:
        return None
    found = re.findall(r"([A-Za-z]+)\s+(\d{4})", text)
    if not found:
        return None
    mo, yr = found[-1]
    m = MONTHS.get(mo.lower())
    return (int(yr), m) if m else None


# ------------------------------------------------------------------ build
LATEST_END = (2026, 3)          # FYE 2026 ends March 2026
TOP_LEVEL = ["Universal Credit", "State Pension", "Personal Independence Payment", "Housing Benefit Total", "Disability Living Allowance",
             "Pension Credit", "Attendance Allowance", "Employment and Support Allowance", "Carer's Allowance", "Jobseeker's Allowance",
             "Income Support Total", "Incapacity Benefit", "Interdependencies", "Unreviewed excluding Council Tax Benefit", "Council Tax Benefit"]
REVISION_SERIES = [("All Benefits", "Total"), ("All Benefits", "Fraud"), ("Universal Credit", "Total"), ("Universal Credit", "Fraud"),
                   ("Personal Independence Payment", "Total"), ("State Pension", "Total")]

DWP_FLAG_TEXT = {
    "dwp_revision": ("Benefit fraud and error estimate later restated",
                     "DWP's later estimate for a past year differs materially from its earlier published estimate, or falls outside the earlier confidence interval."),
    "dwp_stale": ("Benefit measured long ago",
                  "The fraud and error rate for this benefit has not been measured for years, so the published figure may not reflect today's position."),
    "dwp_rate": ("High benefit overpayment rate",
                 "A large share of this benefit's spending was overpaid through fraud and error."),
}


def months_between(a, b):
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def _clip(t):
    return {"est": t[0], "lo": t[1], "hi": t[2]}


def build(paths):
    """paths: {'2024': xlsx, '2025': xlsx, '2026': xlsx} -> (dwp dict, flags, checks)"""
    latest = paths["2026"]
    t1 = parse_table(latest, "Table_1", 1e-6)
    t2 = parse_table(latest, "Table_2")
    t6 = parse_table(latest, "Table_6", 1e-6)
    t12 = parse_table(latest, "Table_12", headline_only=True)
    t14 = parse_table(latest, "Table_14", 1e-6)
    reasons = parse_reasons(latest)

    def ser(tbl, name, line, **kw):
        return [{"year": fy_label(s["fye"]), "est": s["est"], "lo": s["lo"], "hi": s["hi"]} for s in series(tbl, name, line, **kw)]

    allb = {k: ser(t1, "All Benefits", ln) for k, ln in (("fraud", "Fraud"), ("claimant", "Claimant Error"), ("official", "Official Error"),
                                                        ("total", "Total"), ("expenditure", "Expenditure"))}
    allb["pct"] = {k: ser(t2, "All Benefits", ln) for k, ln in (("fraud", "Fraud"), ("claimant", "Claimant Error"), ("official", "Official Error"), ("total", "Total"))}
    under = {"official": ser(t6, "All Benefits", "Official Error"), "expenditure": ser(t6, "All Benefits", "Expenditure")}
    b14 = block(t14, "All Benefits")
    net = {}
    for key, pref in (("gross", "Gross loss amount"), ("recoveries", "Recoveries amount"), ("net", "Net loss amount"), ("expenditure", "Expenditure"),
                      ("pct_gross", "Gross loss as a percentage"), ("pct_net", "Net loss as a percentage")):
        line = next(k for k in b14["lines"] if k.startswith(pref))
        pts = []
        for c, v in zip(t14["cols"], b14["lines"][line]):
            if v[0] is None or c["revised"] and any(p["fye"] == c["fye"] for p in pts):
                continue
            pts.append({"fye": c["fye"], "est": v[0] * (1e6 * 100 if key.startswith("pct") else 1)})   # percentages are fractions: undo the £->£m scaling
        pts = {p["fye"]: p for p in pts}
        net[key] = [{"year": fy_label(y), "est": pts[y]["est"]} for y in sorted(pts)]

    # ---- per benefit
    benefits = []
    for name in TOP_LEVEL:
        try:
            b1 = block(t1, name)
        except KeyError:
            continue
        L = b1["lines"]
        def first(line, tbl=t1, nm=name):
            try:
                return block(tbl, nm)["lines"][line][0]
            except (KeyError, IndexError):
                return (None, None, None)
        end = parse_measured_end(b1["measured"])
        total, exp = L.get("Total", [(None,) * 3])[0], L.get("Expenditure", [(None,) * 3])[0]
        pct = first("Total", t2)
        try:
            cases = _clip(block(t12, name)["lines"]["Overpayment"][0])
        except (KeyError, IndexError):
            cases = None
        benefits.append({
            "name": name, "measured": b1["measured"], "measured_end": list(end) if end else None,
            "months_since": months_between(end, LATEST_END) if end else None,
            "expenditure": exp[0], "total": _clip(total), "fraud": _clip(first("Fraud")), "claimant": _clip(first("Claimant Error")),
            "official": _clip(first("Official Error")), "pct": _clip(pct), "cases_pct": cases,
            "pct_series": ser(t2, name, "Total") if name in [b["benefit"] for b in t2["blocks"]] else [],
        })

    # ---- how recent is the measurement behind each pound of benefit spending?
    tot_exp = allb["expenditure"][-1]["est"]
    buckets = {"within 12 months": 0.0, "1 to 3 years ago": 0.0, "more than 3 years ago": 0.0, "never reviewed": 0.0}
    for b in benefits:
        if not b["expenditure"]:
            continue
        m = b["months_since"]
        key = "never reviewed" if m is None else "within 12 months" if m <= 12 else "1 to 3 years ago" if m <= 36 else "more than 3 years ago"
        buckets[key] += b["expenditure"]
    coverage = {"total_expenditure": tot_exp, "buckets": buckets}

    # ---- reasons (newest year) for the main benefits
    reasons_out = [{"benefit": r["benefit"], "reasons": [{"reason": x["reason"], "level": x["level"],
                    "total": _clip(x["values"]["Total Overpayments"]), "fraud": _clip(x["values"]["Fraud"]),
                    "claimant": _clip(x["values"]["Claimant Error"]), "official": _clip(x["values"]["Official Error"])} for x in r["reasons"]]} for r in reasons]

    # ---- revisions across releases (same FYE, successive publications)
    rel = {y: parse_table(p, "Table_1", 1e-6) for y, p in paths.items()}
    revisions = []
    for name, line in REVISION_SERIES:
        per = {}
        for y, tbl in rel.items():
            try:
                for s in series(tbl, name, line):
                    per.setdefault(s["fye"], {})[y] = {"est": s["est"], "lo": s["lo"], "hi": s["hi"]}
            except KeyError:
                pass
        revisions.append({"benefit": name, "line": line, "by_fye": {fy_label(f): v for f, v in sorted(per.items()) if len(v) > 1}})

    dwp = {"release": "Financial year ending 2026 estimates (published 19 May 2026)", "all": allb, "under": under, "net": net, "benefits": benefits,
           "coverage": coverage, "reasons": reasons_out, "revisions": revisions, "releases": sorted(paths)}
    return dwp, dwp_flags(dwp), dwp_checks(dwp, t1, t2, t14, reasons)


def dwp_flags(d):
    flags = []
    # 1. restated estimates
    order = d["releases"]
    for rv in d["revisions"]:
        for y, v in rv["by_fye"].items():
            rels = [r for r in order if r in v]
            for a, b in zip(rels, rels[1:]):
                old, new = v[a], v[b]
                if None in (old["est"], new["est"]):
                    continue
                dlt = new["est"] - old["est"]
                outside = old["lo"] is not None and not (old["lo"] <= new["est"] <= old["hi"])
                rel_ = abs(dlt) / max(abs(old["est"]), 100)
                if (abs(dlt) >= 100 and rel_ >= 0.01) or (outside and abs(dlt) >= 100):
                    sev = 3 if (outside and abs(dlt) >= 500) else 2 if (outside or abs(dlt) >= 500) else 1   # most are small: DWP rarely restates
                    flags.append({"type": "dwp_revision", "sev": sev, "benefit": rv["benefit"], "line": rv["line"], "year": y, "value": new["est"], "prev": old["est"],
                                  "detail": f"{rv['benefit']} ({rv['line'].lower()}) for {y}: £{old['est']:,.0f}m in the FYE {a} release, £{new['est']:,.0f}m in the FYE {b} release "
                                            f"({'+' if dlt >= 0 else '−'}£{abs(dlt):,.0f}m, {rel_*100:.0f}%)"
                                            f"{'; the new figure is outside the earlier confidence interval' if outside else ''}."})
    # 2. stale measurement
    for b in d["benefits"]:
        if b["expenditure"] and b["expenditure"] >= 1000 and b["months_since"] is not None and b["months_since"] > 36:
            yrs = b["months_since"] / 12
            sev = 3 if b["expenditure"] >= 7000 else 2
            flags.append({"type": "dwp_stale", "sev": sev, "benefit": b["name"], "line": "Total", "year": "2025-26", "value": b["expenditure"], "prev": None,
                          "detail": f"{b['name']}: £{b['expenditure']/1000:,.1f}bn of spending in 2025-26, but its fraud and error rate was last measured {b['measured']} "
                                    f"({yrs:.1f} years before the end of the period)."})
    unrev = next((b for b in d["benefits"] if b["name"].startswith("Unreviewed")), None)
    if unrev and unrev["expenditure"]:
        flags.append({"type": "dwp_stale", "sev": 2, "benefit": unrev["name"], "line": "Total", "year": "2025-26", "value": unrev["expenditure"], "prev": None,
                      "detail": f"£{unrev['expenditure']/1000:,.1f}bn of benefit spending in 2025-26 has never had its fraud and error rate reviewed."})
    # 3. high overpayment rates
    for b in d["benefits"]:
        p = b["pct"]["est"]
        if p is not None and b["expenditure"] and b["expenditure"] >= 1000 and p >= 3:
            flags.append({"type": "dwp_rate", "sev": 3 if p >= 8 else 2 if p >= 5 else 1, "benefit": b["name"], "line": "Total", "year": "2025-26",
                          "value": b["total"]["est"], "prev": None,
                          "detail": f"{b['name']}: {p:.1f}% of spending (£{b['total']['est']:,.0f}m of £{b['expenditure']/1000:,.1f}bn) was overpaid through fraud and error"
                                    f"{'; fraud alone was £' + format(b['fraud']['est'], ',.0f') + 'm' if b['fraud']['est'] else ''}."})
    flags.sort(key=lambda f: (-f["sev"], -(f["value"] or 0)))
    return flags


def dwp_checks(d, t1, t2, t14, reasons):
    checks = []
    al = d["all"]
    yrs = [p["year"] for p in al["total"]]
    g = lambda k: {p["year"]: p["est"] for p in al[k]}
    f, c, o, t = g("fraud"), g("claimant"), g("official"), g("total")
    rows = [(y, t[y], (f.get(y) or 0) + (c.get(y) or 0) + (o.get(y) or 0)) for y in yrs if t[y] is not None and f.get(y) is not None]
    checks.append(A._check("dwp_sum", "DWP: fraud + claimant error + official error = total overpaid, all benefits (£m)", rows, 150,
                           "Each figure is rounded to the nearest £100m, so up to about £150m of difference is rounding."))
    ex = g("expenditure")
    pt = {p["year"]: p["est"] for p in al["pct"]["total"]}
    rows = [(y, t[y], ex[y] * pt[y] / 100) for y in yrs if y in pt and pt[y] is not None and ex.get(y) and t[y] is not None and y >= "2019-20"]
    checks.append(A._check("dwp_pct", "DWP: overpaid percentage × expenditure = overpaid amount, all benefits (£m)", rows, 450,
                           "Percentages are rounded to 0.1 percentage point (about £300m on £300bn of spending), so a few hundred £m of slack is expected."))
    n = {k: {p["year"]: p["est"] for p in d["net"][k]} for k in ("gross", "recoveries", "net")}
    rows = [(y, n["net"][y], n["gross"][y] - n["recoveries"].get(y, 0)) for y in n["net"] if y in n["gross"]]
    checks.append(A._check("dwp_net", "DWP: gross loss − recoveries = net loss (£m)", rows, 150))
    rows = [(y, t[y], n["gross"][y]) for y in n["gross"] if t.get(y) is not None and y >= "2012-13"]
    checks.append(A._check("dwp_gross", "DWP: gross loss in Table 14 agrees with overpayments in Table 1 (£m)", rows, 150,
                           "The two tables restate history on slightly different bases in earlier years, so only years since 2012-13 are compared."))
    # benefits add up to the all-benefits figure
    sT = sum((b["total"]["est"] or 0) for b in d["benefits"])
    sE = sum((b["expenditure"] or 0) for b in d["benefits"])
    checks.append(A._check("dwp_benefits", "DWP: benefits sum to the all-benefits overpayment, 2025-26 (£m)", [("2025-26", t[yrs[-1]], sT)], 100,
                           "Sums the 15 top-level benefit lines (Housing Benefit and Income Support totals, not their parts)."))
    checks.append(A._check("dwp_exp", "DWP: benefit expenditure sums to all-benefits expenditure, 2025-26 (£m)", [("2025-26", ex[yrs[-1]], sE)], 100))
    # reasons add up to the total for each reviewed benefit
    rows = []
    for r in reasons:
        top = [x for x in r["reasons"] if x["level"] == 0 and x["reason"] != "Total"]
        tot = next((x for x in r["reasons"] if x["reason"] == "Total"), None)
        if tot and top and tot["values"]["Total Overpayments"][0] is not None:
            rows.append((r["benefit"], tot["values"]["Total Overpayments"][0], sum(x["values"]["Total Overpayments"][0] or 0 for x in top)))
    checks.append(A._check("dwp_reasons", "DWP: error reasons sum to the benefit's total overpayment, 2025-26 (£m)", rows, 20,
                           "Reasons are listed to the nearest £1m."))
    for ck in checks:
        ck["source"] = "DWP"
    return checks


def dwp_vs_treasury(dwp, t11, rec):
    """Informational: DWP's benefit expenditure vs the Treasury's 'Social security benefits' line less Child Benefit.

    DWP measures Great Britain and the benefits it administers; the Treasury line is UK-wide and includes Child Benefit,
    which HMRC pays. Differences are scope, not necessarily error, so this is reported but never marked as failing.
    """
    yrs, lines = t11
    ss = next(l for l in lines if l["label"].lower() == "social security benefits")["values"]
    cb = dict(zip(rec["fys"], rec["spend_a"]["Child Benefit Payments"]))
    ex = {p["year"]: p["est"] for p in dwp["all"]["expenditure"]}
    rows = [(y, v - (cb.get(y) or 0), ex[y]) for y, v in zip(yrs, ss) if y in ex and v is not None]
    c = A._check("dwp_vs_hmt", "DWP benefit expenditure vs Treasury 'Social security benefits' less HMRC-paid Child Benefit (£m)", rows, 1e12,
                 "Scope differs: the Treasury line covers the whole UK (including Northern Ireland benefits), DWP's measure covers Great Britain. "
                 "The gap was £1-6bn to 2023-24 and £10-12bn in the last two years. DWP also restated its own 2024-25 expenditure from "
                 f"£292.2bn to £{ex.get('2024-25', 0)/1000:,.1f}bn after spotting an issue with State Pension expenditure. Shown for transparency; not a failure.")
    c["status"] = "info"
    c["source"] = "DWP"
    return c
