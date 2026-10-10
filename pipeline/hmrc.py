"""HMRC data: monthly/annual tax receipts and the Measuring Tax Gaps tables.

Sources (both published by HMRC on GOV.UK):
  * HMRC tax receipts and National Insurance contributions for the UK (.ods)
  * Measuring tax gaps tables (.xlsx)
"""
import re
import statistics
from collections import defaultdict

import openpyxl

import analysis as A
from ods import read_ods

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}
YEAR_RE = re.compile(r"^\d{4}-\d{2}$")


# ---------------------------------------------------------------- helpers
def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s.startswith("<"):               # HMRC writes "<0.1" for tiny non-zero values
        try:
            return float(s[1:]) / 2
        except ValueError:
            return None
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return None                     # "[X]", "", "n/a"


def month_key(label):
    m, y = str(label).split()
    return f"{int(y)}-{MONTHS[m]:02d}"


def fy_key(label):
    a, b = str(label).split(" to ")
    return f"{a}-{b[2:]}"


def month_label(key):  # "2021-05" -> "May 2021"
    name = [k for k, v in MONTHS.items() if v == int(key[5:])][0]
    return f"{name} {key[:4]}"


def money_m(v):  # £m with a proper minus sign: -5266 -> "−£5,266m"
    return f"{'−' if v < 0 else ''}£{abs(v):,.0f}m"


def fy_of(month):  # "2017-04" -> "2017-18"
    y, m = int(month[:4]), int(month[5:])
    s = y if m >= 4 else y - 1
    return f"{s}-{str(s + 1)[2:]}"


# ------------------------------------------------------------ receipts ODS
def _ods_table(rows, first_col_prefix):
    hi = next(i for i, r in enumerate(rows) if r and str(r[0]).startswith(first_col_prefix) and len(r) > 2)
    hdr = rows[hi]
    data = []
    for r in rows[hi + 1:]:
        if not r or str(r[0]).startswith("End"):
            break
        data.append(r)
    return hdr, data


def parse_receipts(path):
    sheets = read_ods(path)

    def series(sheet, prefix, keyfn):
        hdr, data = _ods_table(sheets[sheet], prefix)
        keys = [keyfn(r[0]) for r in data]
        cols = {}
        for j, h in enumerate(hdr[1:], 1):
            cols[h.strip()] = [_num(r[j]) if j < len(r) else None for r in data]
        return keys, cols
    months, receipts_m = series("Receipts_Monthly", "Table 1", month_key)
    _, spend_m = series("Expenditure_Monthly", "Table 3", month_key)
    fys, receipts_a = series("Receipts_Annually", "Table 2", fy_key)
    _, spend_a = series("Expenditure_Annually", "Table 4", fy_key)
    return {"months": months, "receipts_m": receipts_m, "spend_m": {k: v for k, v in spend_m.items()},
            "fys": fys, "receipts_a": receipts_a, "spend_a": spend_a}


# ----------------------------------------------------------- tax gap xlsx
def _xlsx_rows(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        ws.reset_dimensions()   # these workbooks understate their own size
        return [tuple(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def parse_gap_table(path, sheet, label_cols):
    rows = _xlsx_rows(path, sheet)
    hi = next(i for i, r in enumerate(rows) if sum(1 for c in r if c is not None and YEAR_RE.match(str(c))) >= 3)
    cols = [(j, str(c)) for j, c in enumerate(rows[hi]) if c is not None and YEAR_RE.match(str(c))]
    out = []
    for r in rows[hi + 1:]:
        if not r or r[0] in (None, ""):
            if out:
                break
            continue
        out.append({"labels": [str(r[k]).strip() if r[k] is not None else "" for k in range(label_cols)],
                    "values": [_num(r[j]) for j, _ in cols]})
    return [y for _, y in cols], out


def parse_tax_gap(path):
    ys, gap_bn = parse_gap_table(path, "Table 1.2", 3)
    _, gap_pct = parse_gap_table(path, "Table 1.1", 3)
    yg, groups = parse_gap_table(path, "Table 1.3", 2)
    yb, behaviour = parse_gap_table(path, "Table 7.1", 2)
    yv, vat = parse_gap_table(path, "Table 2.1", 1)
    # Table 1.4: revisions by publication ("MTG 2026"), same year-header layout
    yr, rev = parse_gap_table(path, "Table 1.4", 1)
    return {"years": ys, "gap_bn": gap_bn, "gap_pct": gap_pct,
            "groups": {"years": yg, "rows": groups}, "behaviour": {"years": yb, "rows": behaviour},
            "vat": {"years": yv, "rows": vat}, "revisions": {"years": yr, "rows": rev}}


# ------------------------------------------------------------ analysis
MONTHLY_FLAG_TEXT = {
    "monthly_jump": ("Unusual change in monthly tax receipts",
                     "Receipts in this month differ from the same month a year earlier far more than that tax's normal year-on-year movement. "
                     "Timing (payment dates falling either side of a month end), tax rises or one-offs are common innocent causes."),
    "taxgap_revision": ("Tax gap estimate later revised",
                        "HMRC's later estimate of a past year's tax gap differs materially from its earlier estimate."),
}


def monthly_flags(months, cols, min_median=300, z_min=4.0, min_change=300, mad_floor=0.03, noun="tax", ftype="monthly_jump"):
    """Year-on-year change for each tax, scored against that tax's own history (median/MAD).

    A jump is reported once: if the same tax moved sharply the opposite way twelve months
    earlier, this month is a base effect of that earlier shock (e.g. Covid VAT deferrals
    being repaid) and is not reported again.
    """
    flags = []
    for name, vals in cols.items():
        if name in ("Total Paid Over",):
            continue
        ok = [v for v in vals if v is not None]
        if len(ok) < 30 or statistics.median([abs(v) for v in ok]) < min_median:
            continue
        yoy = []
        for i in range(12, len(vals)):
            a, b = vals[i - 12], vals[i]
            yoy.append(None if a is None or b is None or abs(a) < 50 else (b - a) / abs(a))
        good = [x for x in yoy if x is not None]
        if len(good) < 18:
            continue
        med, mad = A.robust_center_spread(good)
        mad = max(mad, mad_floor)
        hit = {}
        for k, x in enumerate(yoy):
            if x is None:
                continue
            i = k + 12
            z = 0.6745 * (x - med) / mad
            d = vals[i] - vals[i - 12]
            if abs(z) >= z_min and abs(d) >= min_change:
                hit[i] = (x, z, d)
        for i, (x, z, d) in hit.items():
            prev = hit.get(i - 12)
            if prev and prev[2] * d < 0:      # opposite-signed shock a year earlier: base effect
                continue
            sev = 3 if abs(z) >= 8 and abs(d) >= 1000 else 2 if abs(z) >= 5.5 and abs(d) >= 500 else 1
            label = "Total HMRC receipts" if name == "Total HMRC Receipts" else re.sub(r"\s*\(included within[^)]*\)", "", name)
            flags.append({"type": ftype, "sev": sev, "tax": name, "month": months[i], "value": vals[i], "prev": vals[i - 12],
                          "z": round(z, 1),
                          "detail": f"{label}: {money_m(vals[i])} in {month_label(months[i])}, {'up' if d > 0 else 'down'} {money_m(abs(d))} "
                                    f"({x*100:+.0f}%) on {month_label(months[i - 12])}. The usual year-on-year change for this {noun} is {med*100:+.0f}% "
                                    f"(score {abs(z):.1f})."})
    flags.sort(key=lambda f: (-f["sev"], -abs(f["z"])))
    return flags


def taxgap_revision_summary(rev):
    """First published estimate vs latest estimate for each year (Table 1.4: total gap as % of liabilities)."""
    years, rows = rev["years"], rev["rows"]
    pubs = [r["labels"][0] for r in rows]          # newest first: "MTG 2026", "MTG 2025", ...
    out = []
    for j, y in enumerate(years):
        seq = [(pubs[i], r["values"][j]) for i, r in enumerate(rows) if r["values"][j] is not None]
        if len(seq) < 2:
            continue
        latest, first = seq[0], seq[-1]
        out.append({"year": y, "first_pub": first[0], "first": first[1], "latest_pub": latest[0], "latest": latest[1],
                    "revision_pp": round(latest[1] - first[1], 2), "n_pubs": len(seq),
                    "path": [{"pub": p, "v": v} for p, v in reversed(seq)]})
    return out


def recent_bias(summary, last=6):
    """Direction of revisions for the most recent years that have been re-estimated."""
    recent = [s for s in summary if s["n_pubs"] >= 2][-last:]
    ups = [s for s in recent if s["revision_pp"] > 0]
    return {"years": [s["year"] for s in recent], "revisions_pp": [s["revision_pp"] for s in recent], "n_up": len(ups), "n": len(recent),
            "mean_pp": round(sum(s["revision_pp"] for s in recent) / len(recent), 2) if recent else 0}


def taxgap_flags(summary, min_pp=1.0):
    flags = []
    for s in summary:
        if abs(s["revision_pp"]) >= min_pp:
            sev = 3 if abs(s["revision_pp"]) >= 2.0 else 2 if abs(s["revision_pp"]) >= 1.5 else 1
            flags.append({"type": "taxgap_revision", "sev": sev, "year": s["year"], "value": s["latest"], "prev": s["first"],
                          "detail": f"The tax gap for {s['year']} was first estimated at {s['first']:.1f}% of liabilities ({s['first_pub']}) and is now "
                                    f"{s['latest']:.1f}% ({s['latest_pub']}): {s['revision_pp']:+.1f} percentage points across {s['n_pubs']} editions."})
    flags.sort(key=lambda f: (-f["sev"], -abs(f["value"] - f["prev"])))
    return flags


# -------------------------------------------------------------- checks
def _display(check, keep=10):
    rows = check["rows"]
    if len(rows) > keep:
        shown = sorted(rows, key=lambda r: -abs(r["gap"]))[:keep]
        shown.sort(key=lambda r: r["year"])
        check["note"] = (check["note"] + " " if check["note"] else "") + f"Showing the {keep} largest gaps of {len(rows)} periods checked."
        check["rows"] = shown
    return check


def hmrc_checks(rec, gap):
    checks = []
    parts = [h for h in rec["receipts_m"]
             if "included within" not in h and h not in ("Total Paid Over", "Total HMRC Receipts", "PAYE NIC1 (EMP'er)", "PAYE NIC1 (EMP'ee)", "SA NIC2&4")]
    n = lambda v: v or 0.0

    def sumcheck(cid, title, labels, cols, tol, note=""):
        rows = [(lab, cols["Total HMRC Receipts"][i], sum(n(cols[p][i]) for p in parts)) for i, lab in enumerate(labels)]
        c = A._check(cid, title, rows, tol, note)
        return _display(c)
    checks.append(sumcheck("hmrc_monthly_sum", "HMRC monthly: individual taxes sum to Total HMRC Receipts (£m)", rec["months"], rec["receipts_m"], 6,
                         "Each of about 38 components is rounded to the nearest £1m, so a total can legitimately differ by a few £m."))
    checks.append(sumcheck("hmrc_annual_sum", "HMRC annual: individual taxes sum to Total HMRC Receipts (£m)", rec["fys"], rec["receipts_a"], 6,
                         "Each of about 38 components is rounded to the nearest £1m, so a total can legitimately differ by a few £m."))
    # annual vs sum of months for complete financial years
    byfy = defaultdict(list)
    for i, m in enumerate(rec["months"]):
        byfy[fy_of(m)].append(i)
    rows = []
    for fy, idx in byfy.items():
        if len(idx) == 12 and fy in rec["fys"]:
            rows.append((fy, rec["receipts_a"]["Total HMRC Receipts"][rec["fys"].index(fy)],
                         sum(n(rec["receipts_m"]["Total HMRC Receipts"][i]) for i in idx)))
    c = A._check("hmrc_fy_vs_months", "HMRC: twelve monthly totals add up to the published financial-year total (£m)", rows, 12,
                 "Monthly and annual tables are separately compiled, so small gaps can arise from late adjustments.")
    checks.append(c)
    # tax gap internal consistency
    lab = {tuple(r["labels"]): r["values"] for r in gap["gap_bn"]}
    comp = lambda *k: lab[k]
    ys = gap["years"]

    def rowsum(total_key, part_keys, tol_per=0.06):
        tot = lab[total_key]
        rows = [(y, tot[i], sum(n(lab[k][i]) for k in part_keys)) for i, y in enumerate(ys) if tot[i] is not None]
        return rows, tol_per * (len(part_keys) + 1)
    specs = [
        ("gap_sa", "Tax gap (Table 1.2): Self Assessment components sum to Total Self Assessment (£bn)",
         ("Income Tax, NICs, Capital Gains Tax", "Total Self Assessment", "Total Self Assessment"),
         [k for k in lab if k[1] == "Self Assessment"]),
        ("gap_paye", "Tax gap (Table 1.2): PAYE components sum to Total PAYE (£bn)",
         ("Income Tax, NICs, Capital Gains Tax", "Total PAYE", "Total PAYE"), [k for k in lab if k[1] == "PAYE"]),
        ("gap_ct", "Tax gap (Table 1.2): Corporation Tax size bands sum to Total Corporation Tax (£bn)",
         ("Corporation Tax", "Total Corporation Tax", "Total Corporation Tax"), [k for k in lab if k[0] == "Corporation Tax" and k[1] == "Corporation Tax"]),
    ]
    for cid, title, tkey, pkeys in specs:
        rows, tol = rowsum(tkey, pkeys)
        checks.append(A._check(cid, title, rows, tol))
    totals = [k for k in lab if k[2].startswith("Total ") and k[0] != "Total tax gap" and not k[0].startswith("Total theoretical")
              and not k[0].startswith("Total percentage")]
    top_keys = [("VAT", "Total VAT", "Total VAT"), ("Excise duty", "Total excise duty", "Total excise duty"),
                ("Income Tax, NICs, Capital Gains Tax", "Total Income Tax, NICs, Capital Gains Tax", "Total Income Tax, NICs, Capital Gains Tax"),
                ("Corporation Tax", "Total Corporation Tax", "Total Corporation Tax"), ("Other taxes", "Total other taxes", "Total other taxes")]
    top_keys = [k for k in top_keys if k in lab]
    tg = ("Total tax gap", "Total tax gap", "Total tax gap")
    rows = [(y, lab[tg][i], sum(n(lab[k][i]) for k in top_keys)) for i, y in enumerate(ys) if lab[tg][i] is not None]
    checks.append(A._check("gap_total", "Tax gap (Table 1.2): five tax groups sum to the total tax gap (£bn)", rows, 0.06 * 6))
    # theoretical liability x percentage = gap
    liab = next((v for k, v in lab.items() if k[0].startswith("Total theoretical")), None)
    pct = next((v for k, v in lab.items() if k[0].startswith("Total percentage")), None)
    if liab and pct:
        rows = [(y, lab[tg][i], liab[i] * pct[i] / 100) for i, y in enumerate(ys) if None not in (liab[i], pct[i], lab[tg][i])]
        checks.append(A._check("gap_pct", "Tax gap: total liabilities × stated percentage = total tax gap (£bn)", rows, 0.5,
                               "Both the percentage and the £bn figures are rounded, so about £0.5bn of slack is expected."))
    # Table 1.3 and 7.1 totals against 1.2
    g13 = {tuple(r["labels"]): r["values"] for r in gap["groups"]["rows"]}
    t13 = g13.get(("Total", "Tax gap in £bn"))
    if t13:
        rows = [(y, lab[tg][ys.index(y)], t13[i]) for i, y in enumerate(gap["groups"]["years"]) if y in ys and t13[i] is not None]
        checks.append(A._check("gap_groups", "Tax gap by customer group (Table 1.3) total agrees with Table 1.2 (£bn)", rows, 0.15))
    b71 = {tuple(r["labels"]): r["values"] for r in gap["behaviour"]["rows"]}
    tb = b71.get(("Total", "Tax gap in £bn"))
    if tb:
        bys = gap["behaviour"]["years"]
        parts = [v for k, v in b71.items() if k[1] == "Tax gap in £bn" and k[0] != "Total"]
        rows = [(y, tb[i], sum(n(p[i]) for p in parts)) for i, y in enumerate(bys) if tb[i] is not None]
        checks.append(A._check("gap_behaviour", "Tax gap by behaviour (Table 7.1): behaviours sum to the total (£bn)", rows, 0.06 * 9))
        rows = [(y, lab[tg][ys.index(y)], tb[i]) for i, y in enumerate(bys) if y in ys and tb[i] is not None]
        checks.append(A._check("gap_behaviour_vs_total", "Tax gap by behaviour (Table 7.1) total agrees with Table 1.2 (£bn)", rows, 0.15))
    for c in checks:
        c["source"] = "HMRC"
    return checks
