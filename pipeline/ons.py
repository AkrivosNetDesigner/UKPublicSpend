"""ONS Public Sector Finances (dataset PUSF): monthly series, not seasonally adjusted, current prices.

Source: ONS "Public sector finances" dataset CSV. Series are selected by CDID and their official
titles are kept so the site can show exactly what each one is.
"""
import csv
import re

import analysis as A
import hmrc as H

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
START = "1997-04"          # first month for which the flow series exist

# (cdid, short label, group, sign). sign=-1 flips ONS's convention so that borrowing is positive.
SERIES = [
    ("KX5Q", "Total managed expenditure", "Public sector (excluding banks)", 1),
    ("JW2O", "Current receipts", "Public sector (excluding banks)", 1),
    ("JW2Q", "Current expenditure", "Public sector (excluding banks)", 1),
    ("JW2Z", "Net investment", "Public sector (excluding banks)", 1),
    ("J5II", "Net borrowing", "Public sector (excluding banks)", -1),
    ("KSE6", "Net debt (end of month)", "Public sector (excluding banks)", 1),
    ("MF6U", "Central government: total expenditure", "Central government", 1),
    ("MF6S", "Central government: current expenditure", "Central government", 1),
    ("MF6T", "Central government: capital expenditure", "Central government", 1),
    ("NMBJ", "Goods and services bought", "Central government spending", 1),
    ("NMBG", "of which staff costs", "Central government spending", 1),
    ("GZSJ", "Net social benefits", "Central government spending", 1),
    ("NMFX", "Net interest payable", "Central government spending", 1),
    ("NMCD", "Subsidies", "Central government spending", 1),
    ("NMFC", "Other current grants", "Central government spending", 1),
    ("MF6R", "Central government: total revenue", "Central government receipts", 1),
    ("MF73", "Taxes (total)", "Central government receipts", 1),
    ("KSS8", "Income tax and National Insurance", "Central government receipts", 1),
    ("NZGF", "VAT", "Central government receipts", 1),
    ("CUDG", "Fuel duty", "Central government receipts", 1),
    ("LIBP", "Corporation tax and other taxes on income", "Central government receipts", 1),
    ("ANLQ", "Local government: current expenditure", "Local government", 1),
]
STOCKS = {"KSE6"}          # levels, not flows: never summed over a year


def parse_pusf(path):
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    titles, cdids = rows[0], rows[1]
    idx = {c: j for j, c in enumerate(cdids)}
    release = rows[4][1] if len(rows) > 4 else ""
    monthly = [r for r in rows[7:] if re.match(r"^\d{4} [A-Z]{3}$", r[0])]
    months = [f"{r[0][:4]}-{MONTHS.index(r[0][5:]) + 1:02d}" for r in monthly]
    keep = [i for i, m in enumerate(months) if m >= START]
    out = {"months": [months[i] for i in keep], "release": release, "series": {}}
    for cdid, label, group, sign in SERIES:
        j = idx[cdid]
        vals = []
        for i in keep:
            v = monthly[i][j].strip()
            vals.append(None if v == "" else sign * float(v))
        out["series"][cdid] = {"label": label, "group": group, "title": titles[j], "sign": sign, "stock": cdid in STOCKS, "values": vals}
    return out


def fy_sums(months, values):
    """financial year -> sum, for complete years only."""
    tot, n = {}, {}
    for m, v in zip(months, values):
        if v is None:
            continue
        f = H.fy_of(m)
        tot[f] = tot.get(f, 0.0) + v
        n[f] = n.get(f, 0) + 1
    return {f: v for f, v in tot.items() if n[f] == 12}


NEAR_ZERO = {"JW2Z", "J5II"}        # swing around zero, so a percentage change is meaningless
FLAG_FROM = "2015-01"               # earlier history informs the scoring but is not reported


def ons_flags(ons):
    """Same year-on-year screening as HMRC receipts, on the flow series that describe what is spent."""
    cols = {s["label"]: s["values"] for c, s in ons["series"].items() if not s["stock"] and c not in NEAR_ZERO}
    fl = H.monthly_flags(ons["months"], cols, noun="series", ftype="ons_monthly_jump")
    return [f for f in fl if f["month"] >= FLAG_FROM]


ONS_FLAG_TEXT = {
    "ons_monthly_jump": ("Unusual change in monthly public finances (ONS)",
                         "Spending, receipts or borrowing in this month differs from the same month a year earlier far more than that series' normal movement. "
                         "Policy changes, one-off payments (such as energy support) and timing are common innocent causes."),
}


def ons_checks(ons, agg):
    months, S = ons["months"], ons["series"]
    g = lambda c: S[c]["values"]
    checks = []
    # 1. borrowing = expenditure - receipts (ONS reports borrowing with the opposite sign; we flipped it)
    rows = [(m, g("KX5Q")[i] - g("JW2O")[i], g("J5II")[i]) for i, m in enumerate(months)
            if None not in (g("KX5Q")[i], g("JW2O")[i], g("J5II")[i])]
    checks.append(A._check("ons_borrow", "ONS: total managed expenditure − current receipts = net borrowing (£m, monthly)", rows, 3,
                           "ONS publishes borrowing as a negative number; the site shows it as a positive number."))
    # 2. central government total = current + capital
    rows = [(m, g("MF6U")[i], g("MF6S")[i] + g("MF6T")[i]) for i, m in enumerate(months)
            if None not in (g("MF6U")[i], g("MF6S")[i], g("MF6T")[i])]
    checks.append(A._check("ons_cg", "ONS: central government current + capital expenditure = total expenditure (£m, monthly)", rows, 3))
    # 3. ONS monthly TME vs Treasury annual TME (Table 4.1)
    tme = fy_sums(months, g("KX5Q"))
    pesa = {a["year"]: a["tme"] for a in agg}
    rows = [(f, pesa[f], tme[f] / 1000) for f in sorted(tme) if f in pesa]
    c = A._check("ons_vs_pesa", "ONS monthly total managed expenditure, summed over each financial year, agrees with Treasury Table 4.1 (£bn)", rows, 7,
                 "The Treasury's tables are built on ONS data, so exact agreement in older years is expected and is not an independent test. "
                 "Since 2011-12 small gaps (up to about 0.4%) appear, because ONS has since revised its figures.")
    A_ = c
    A_["rows"] = [r for r in A_["rows"] if r["year"] >= "2010-11"]
    checks.append(A_)
    for c in checks:
        c["source"] = "ONS"
        H._display(c)
    return checks
