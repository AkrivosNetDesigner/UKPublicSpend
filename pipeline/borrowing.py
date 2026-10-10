"""Government borrowing and debt: how much, who lends it, and what it costs.

Sources
  * ONS Public Sector Finances (already downloaded for the monthly page): annual series since 1946 (calendar years),
    net debt, debt interest, Bank of England gilt holdings.
  * UK Debt Management Office (DMO): quarterly gilt holdings by type of holder since 1987, and the average yield on
    gilts issued each financial year since 1998-99.
  * Bank of England: daily gilt yields (5, 10 and 20 year nominal par yields, 5 year inflation-linked).
"""
import csv
import re
import statistics
from collections import defaultdict
from datetime import datetime

import analysis as A
import hmrc as H

ANNUAL = {  # cdid -> (label, sign)
    "J5II": ("Net borrowing", -1), "KX5Q": ("Total managed expenditure", 1), "JW2O": ("Current receipts", 1),
    "NMFX": ("Central government net interest payable", 1), "HF6X": ("Net debt, % of GDP", 1), "A3PT": ("General government net borrowing, % of GDP", 1),
    "KSE6": ("Net debt", 1), "KI2L": ("Bank of England gilt holdings: effect on net debt", 1), "BKPW": ("Central government gross debt", 1),
}
YIELD_SERIES = {"IUDSNPY": "5-year", "IUDMNPY": "10-year", "IUDLNPY": "20-year", "IUDSIZC": "5-year inflation-linked"}
HOLDER_COLS = {  # DMO sheet column -> label (the ONS financial-accounts breakdown of gilts at market value, £m)
    1: "Total gilts", 2: "Local government", 3: "Public corporations", 4: "Banks and the Bank of England (together)", 5: "Insurance companies and pension funds",
    6: "Other financial institutions (funds etc.)", 7: "Private non-financial companies", 8: "Households", 9: "Charities and non-profits",
    10: "Overseas investors", 12: "UK banks and building societies", 13: "Bank of England",
}
HOLDER_GROUPS = [  # chart groups, each a list of source columns
    ("Overseas investors", [10]), ("Insurers and pension funds", [5]), ("Other financial institutions (funds etc.)", [6]),
    ("UK banks and building societies", [12]), ("Bank of England", [13]), ("Households, companies and public bodies", [2, 3, 7, 8, 9]),
]

TYPE_INFO = {"borrowing_jump": ("Unusual change in monthly borrowing",
                                "Borrowing in this month differs from the same month a year earlier by far more than is normal for that month. "
                                "Timing of tax receipts, one-off payments and policy changes are common innocent causes.")}


# ----------------------------------------------------------------- ONS annual
def parse_ons_annual(path):
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    cd = {c: j for j, c in enumerate(rows[1])}
    out = {}
    for cdid, (label, sign) in ANNUAL.items():
        j = cd[cdid]
        out[cdid] = {int(r[0]): sign * float(r[j]) for r in rows[7:] if re.match(r"^\d{4}$", r[0]) and r[j].strip()}
    return out


# ------------------------------------------------------------------------ DMO
def parse_holdings(path):
    import xlrd
    sh = xlrd.open_workbook(path).sheets()[0]
    quarters, series = [], defaultdict(list)
    for r in range(sh.nrows):
        row = sh.row_values(r)
        if not re.match(r"^\d{4} Q[1-4]$", str(row[0]).strip()):
            continue
        quarters.append(str(row[0]).strip())
        for c in HOLDER_COLS:
            v = row[c] if c < len(row) else ""
            series[c].append(float(v) if isinstance(v, float) else None)
    return {"quarters": quarters, "cols": dict(series)}


def holder_groups(h):
    out = []
    for name, cols in HOLDER_GROUPS:
        vals = []
        for i in range(len(h["quarters"])):
            parts = [h["cols"][c][i] for c in cols]
            vals.append(None if any(p is None for p in parts) else sum(parts))
        out.append({"name": name, "values": vals})
    return out


def parse_issuance(path):
    import xlrd
    sh = xlrd.open_workbook(path).sheets()[0]
    years, gross, yld = [], [], []
    for r in range(sh.nrows):
        row = sh.row_values(r)
        if re.match(r"^\d{4}-\d{2}$", str(row[0]).strip()):
            years.append(str(row[0]).strip())
            gross.append(float(row[1]) if isinstance(row[1], float) else None)
            yld.append(float(row[2]) if isinstance(row[2], float) else None)
    return {"years": years, "gross_bn": gross, "avg_yield": yld}


# --------------------------------------------------------------------- Bank of England
def parse_yields(paths):
    """One or more Bank of England CSVs (the inflation-linked series only exists from about 2009, so it is fetched separately)."""
    paths = [paths] if isinstance(paths, (str, bytes)) or hasattr(paths, "__fspath__") else list(paths)
    merged, cols = defaultdict(dict), set()
    for path in paths:
        rows = list(csv.reader(open(path, encoding="utf-8-sig")))
        hdr = rows[0]
        keep = {s: hdr.index(s) for s in YIELD_SERIES if s in hdr}
        cols |= set(keep)
        for r in rows[1:]:
            if not r:
                continue
            try:
                d = datetime.strptime(r[0].strip(), "%d %b %Y").date()
            except ValueError:
                continue
            for s, j in keep.items():
                if j < len(r) and r[j].strip():
                    merged[d][s] = float(r[j])
    days = sorted(merged.items())
    cols = [s for s in YIELD_SERIES if s in cols]
    by_month = defaultdict(lambda: defaultdict(list))
    for d, v in days:
        for s, x in v.items():
            by_month[d.strftime("%Y-%m")][s].append(x)
    months = sorted(by_month)
    monthly = {s: [round(statistics.mean(by_month[m][s]), 3) if by_month[m].get(s) else None for m in months] for s in cols}
    recent = days[-400:]
    daily = {"dates": [d.isoformat() for d, _ in recent], **{s: [v.get(s) for _, v in recent] for s in cols}}
    return {"series": {s: YIELD_SERIES[s] for s in cols}, "months": months, "monthly": monthly, "daily": daily,
            "latest": {"date": days[-1][0].isoformat(), **{s: days[-1][1].get(s) for s in cols}}}


# ------------------------------------------------------------------------ flags
def borrowing_flags(months, borrowing, from_month="2015-01", z_min=4.0, min_bn=3.0):
    """Year-on-year change in monthly borrowing (£m, positive = borrowing), scored against its own history."""
    d = [None if i < 12 or borrowing[i] is None or borrowing[i - 12] is None else borrowing[i] - borrowing[i - 12] for i in range(len(months))]
    good = [x for x in d if x is not None]
    med, mad = A.robust_center_spread(good)
    mad = max(mad, 500.0)
    hit = {}
    for i, x in enumerate(d):
        if x is None:
            continue
        z = 0.6745 * (x - med) / mad
        if abs(z) >= z_min and abs(x) >= min_bn * 1000:
            hit[i] = (x, z)
    flags = []
    for i, (x, z) in hit.items():
        prev = hit.get(i - 12)
        if months[i] < from_month or (prev and prev[0] * x < 0):    # base effect of last year's shock
            continue
        sev = 3 if abs(z) >= 8 and abs(x) >= 10000 else 2 if abs(z) >= 5.5 and abs(x) >= 5000 else 1
        flags.append({"type": "borrowing_jump", "sev": sev, "month": months[i], "value": borrowing[i], "prev": borrowing[i - 12], "z": round(z, 1),
                      "detail": f"Borrowing was {H.money_m(borrowing[i])} in {H.month_label(months[i])}, {H.money_m(abs(x))} {'more' if x > 0 else 'less'} than in "
                                f"{H.month_label(months[i - 12])} ({H.money_m(borrowing[i - 12])}). The usual year-on-year change is {H.money_m(med)} (score {abs(z):.1f})."})
    flags.sort(key=lambda f: (-f["sev"], -abs(f["z"])))
    return flags


# ----------------------------------------------------------------------- checks
def borrowing_checks(annual, ons, holdings):
    checks = []
    months, S = ons["months"], ons["series"]
    b = S["J5II"]["values"]
    # calendar-year annual rows equal the sum of the twelve months
    rows = []
    for y, v in sorted(annual["J5II"].items()):
        if y < 1998:
            continue
        idx = [i for i, m in enumerate(months) if m.startswith(str(y))]
        if len(idx) == 12 and all(b[i] is not None for i in idx):
            rows.append((str(y), v, sum(b[i] for i in idx)))
    checks.append(A._check("bor_cy", "ONS: calendar-year net borrowing equals the sum of its twelve months (£m)", rows, 5,
                           "The ONS 'annual' series is by calendar year, not financial year."))
    rows = [(str(y), annual["KX5Q"][y] - annual["JW2O"][y], annual["J5II"][y]) for y in sorted(annual["J5II"]) if y in annual["KX5Q"] and y in annual["JW2O"] and y >= 1946]
    checks.append(A._check("bor_identity", "ONS annual: total managed expenditure − current receipts = net borrowing (£m, calendar years)", rows, 5,
                           "Exact (within £5m) in 68 of 80 years. The gaps are all in 1986-1997, up to £1.2bn in 1996, which looks like older data compiled on a different basis; the file does not say."))
    q, c = holdings["quarters"], holdings["cols"]
    holders = [2, 3, 4, 5, 6, 7, 8, 9, 10]
    rows = [(q[i], c[1][i], sum(c[k][i] or 0 for k in holders)) for i in range(len(q)) if c[1][i] is not None]
    checks.append(A._check("gilt_holders", "DMO: holders of gilts add up to the total gilts in issue (£m at market value)", rows, 2))
    rows = [(q[i], c[4][i], (c[12][i] or 0) + (c[13][i] or 0)) for i in range(len(q)) if c[4][i] is not None and c[13][i] is not None]
    checks.append(A._check("gilt_mfi", "DMO: UK banks plus the Bank of England equal the 'monetary financial institutions' line (£m)", rows, 2))
    for ck in checks:
        ck["source"] = "Borrowing"
        H._display(ck)
    return checks


def build(ons, annual, holdings, issuance, yields):
    months = ons["months"]
    b = ons["series"]["J5II"]["values"]
    hg = holder_groups(holdings)
    q = holdings["quarters"]
    last = len(q) - 1

    def at(i, name):
        return next(g["values"][i] for g in hg if g["name"] == name)

    shares = []
    total = holdings["cols"][1]
    for g in hg:
        now, a1, a5 = g["values"][last], g["values"][last - 4], g["values"][last - 20]
        shares.append({"name": g["name"], "now": now, "share": now / total[last] * 100, "share_1y": a1 / total[last - 4] * 100,
                       "share_5y": a5 / total[last - 20] * 100, "change_1y": now - a1})
    fy_int = {}
    for m, v in zip(months, ons["series"]["NMFX"]["values"]):
        if v is not None:
            fy_int.setdefault(H.fy_of(m), []).append(v)
    fy_rec = {}
    for m, v in zip(months, ons["series"]["JW2O"]["values"]):
        if v is not None:
            fy_rec.setdefault(H.fy_of(m), []).append(v)
    interest = [{"year": y, "interest": sum(v), "receipts": sum(fy_rec[y]), "share": sum(v) / sum(fy_rec[y]) * 100}
                for y, v in sorted(fy_int.items()) if len(v) == 12 and len(fy_rec.get(y, [])) == 12]
    ann_years = sorted(annual["J5II"])
    out = {
        "annual": {"years": ann_years, "borrowing": [annual["J5II"][y] for y in ann_years],
                   "spending": [annual["KX5Q"].get(y) for y in ann_years], "receipts": [annual["JW2O"].get(y) for y in ann_years],
                   "interest": [annual["NMFX"].get(y) for y in ann_years], "net_debt": [annual["KSE6"].get(y) for y in ann_years],
                   "net_debt_gdp": [annual["HF6X"].get(y) for y in ann_years], "gg_borrowing_gdp": [annual["A3PT"].get(y) for y in ann_years],
                   "boe_apf": [annual["KI2L"].get(y) for y in ann_years], "gross_debt": [annual["BKPW"].get(y) for y in ann_years]},
        "holdings": {"quarters": q, "groups": hg, "total": total, "shares": shares},
        "issuance": issuance, "yields": yields, "interest_share": interest,
        "flags": borrowing_flags(months, b), "flag_types": {k: {"title": v[0], "text": v[1]} for k, v in TYPE_INFO.items()},
    }
    return out, borrowing_checks(annual, ons, holdings)
