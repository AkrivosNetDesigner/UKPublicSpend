"""What it buys: council spending paired with measured results.

Each pairing joins a spending line (MHCLG revenue outturn, plus capital outturn for roads) to an outcome
published by another department, council by council through the ONS area code, and asks whether councils that
spend more on a service get better results, before and after allowing for deprivation (English Indices of
Deprivation 2025). This is descriptive: councils differ in many ways the data cannot see, so a relationship is a
prompt for questions, never proof that money does or does not work.
"""
import csv
import math
import re
from collections import defaultdict

import ods
import councils as C

WASTE_COLS = ["RO5_envcll_net_cur_exp", "RO5_envdsp_net_cur_exp", "RO5_envrcy_net_cur_exp", "RO5_envmin_net_cur_exp", "RS_levywaste_net_exp"]
ROAD_COLS = ["RO2_transrdsmnt_prn_rds_net_cur_exp", "RO2_transrdsmnt_oth_rds_net_cur_exp", "RO2_transrdsmnt_brd_net_cur_exp",
             "RO2_transrdsenv_prn_rds_net_cur_exp", "RO2_transrdsenv_oth_rds_net_cur_exp"]
CAP_ROAD = "EandR1_transrds_exptotfa"
ROAD_YEARS = ["2022-23", "2023-24", "2024-25"]
OUTCOME_YEAR_WASTE = "2024-25"
MIN_POP = 20000                     # per-resident figures are meaningless for the City of London and the Isles of Scilly


def eligible(info, group):
    """Councils of this kind that exist now: those with a return in the last two years (abolished councils drop out)."""
    return sum(1 for i in info.values() if i["group"] == group and i.get("current", True))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- readers
def read_cols(path, cols, year_col="year_ending", code_col="ONS_code", status_col="status"):
    """{(fy, code): {col: value}} for submitted rows of a MHCLG wide CSV."""
    out = {}
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rd = csv.reader(f)
        h = next(rd)
        ix = {c: i for i, c in enumerate(h)}
        yc = year_col if year_col in ix else "PeriodCode"
        have = [c for c in cols if c in ix]
        for r in rd:
            if r[ix[status_col]] != "submitted":
                continue
            out[(C.fy_label(r[ix[yc]]), r[ix[code_col]])] = {c: _f(r[ix[c]]) for c in have}
    return out


def read_waste(path, year=OUTCOME_YEAR_WASTE):
    sheets = ods.read_ods(path)
    t = sheets["Table_3"]
    hi = next(i for i, x in enumerate(t) if x and x[0] == "Year")
    out = {}
    for x in t[hi + 1:]:
        if x and x[0] == year and x[5] in ("Collection", "Unitary"):
            out[x[2]] = {"name": x[4], "kind": x[5], "residual_kg_hh": _f(x[6]), "recycling_rate": None if _f(x[7]) is None else _f(x[7]) * 100}
    return out


def read_road_red(path, sheets=("RDC0120_A_Roads_and_Motorways", "RDC0120_B_and_C_Roads")):
    """{code: {"A": [pct by year...], "BC": [...]}}, years as FYE integers."""
    book = ods.read_ods(path)
    out = defaultdict(dict)
    for key, sn in zip(("A", "BC"), sheets):
        rows = book[sn]
        hi = next(i for i, x in enumerate(rows) if x and x[0] == "ONS Area Code")
        years = [int(re.sub(r"\D", "", str(c))) for c in rows[hi][3:] if c and str(c).startswith("FYE")]
        for x in rows[hi + 1:]:
            if not x or not re.match(r"^E\d", str(x[0])) or str(x[0]) == "E92000001":
                continue
            out[x[0]][key] = {y: v for y, v in zip(years, x[3:3 + len(years)]) if isinstance(v, float)}
    return out


def read_road_length(path):
    book = ods.read_ods(path)
    rows = book["RDL0202a"]
    hi = next(i for i, x in enumerate(rows) if x and str(x[0]).startswith("ONS"))
    h = rows[hi]
    ix = {c: i for i, c in enumerate(h) if c}
    out = {}
    for x in rows[hi + 1:]:
        if not x or not re.match(r"^E\d", str(x[0])):
            continue
        loc = _f(x[ix["Major locally managed roads"]]) or 0.0
        minor = _f(x[ix["All minor roads"]]) or 0.0
        out[x[0]] = loc + minor
    return out


def read_imd(lower_path, upper_path):
    import openpyxl

    def sheet(path):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb["IMD"]
        ws.reset_dimensions()
        rows = list(ws.iter_rows(values_only=True))
        h = [str(c) for c in rows[0]]
        j = next(i for i, c in enumerate(h) if "Average score" in c)
        return {r[0]: float(r[j]) for r in rows[1:] if r and r[0] and r[j] is not None}
    return sheet(lower_path), sheet(upper_path)


# --------------------------------------------------------------- statistics
def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else 0.0


def spearman(a, b):
    return pearson(rank(a), rank(b))


def residuals(y, x):
    n = len(y)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    slope = sum((v - mx) * (w - my) for v, w in zip(x, y)) / sxx if sxx else 0.0
    return [w - (my + slope * (v - mx)) for v, w in zip(x, y)]


def residuals_multi(y, controls):
    """Residuals of y after a least-squares fit on the control columns (plus a constant)."""
    n, k = len(y), len(controls) + 1
    X = [[1.0] + [c[i] for c in controls] for i in range(n)]
    A = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] + [sum(X[r][i] * y[r] for r in range(n))] for i in range(k)]
    for i in range(k):                                  # Gauss-Jordan with partial pivoting
        p = max(range(i, k), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]
        if abs(A[i][i]) < 1e-12:
            continue
        A[i] = [v / A[i][i] for v in A[i]]
        for r in range(k):
            if r != i:
                f = A[r][i]
                A[r] = [a - f * b for a, b in zip(A[r], A[i])]
    beta = [A[i][k] for i in range(k)]
    return [y[r] - sum(b * v for b, v in zip(beta, X[r])) for r in range(n)]


def partial_spearman(a, b, controls):
    """Spearman correlation of a and b after removing the linear effect of the controls on their ranks."""
    rc = [rank(c) for c in controls]
    return pearson(residuals_multi(rank(a), rc), residuals_multi(rank(b), rc))


def ci95(r, n):
    if n < 8 or abs(r) >= 0.999:
        return None
    z, se = math.atanh(r), 1 / math.sqrt(n - 3)
    return [round(math.tanh(z - 1.96 * se), 2), round(math.tanh(z + 1.96 * se), 2)]


def zs(xs):
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)) or 1
    return [(x - m) / sd for x in xs]


def analyse(points, better, ctl_names=()):
    """points: [{code,name,x(spend),y(outcome),imd}]; better: +1 if higher outcome is better, -1 if lower is better."""
    pts = [p for p in points if None not in (p["x"], p["y"], p["imd"]) and None not in p.get("ctl", [])]
    n = len(pts)
    if n < 12:
        return None
    x, y, d = [p["x"] for p in pts], [p["y"] for p in pts], [p["imd"] for p in pts]
    ctls = [d] + [[p["ctl"][k] for p in pts] for k in range(len(pts[0].get("ctl", [])))]
    rho = spearman(x, y)
    adj = partial_spearman(x, y, ctls)
    res = {"n": n, "rho": round(rho, 2), "rho_ci": ci95(rho, n), "rho_adj": round(adj, 2), "rho_adj_ci": ci95(adj, n - len(ctls)),
           "spend_vs_imd": round(spearman(x, d), 2), "outcome_vs_imd": round(spearman(y, d), 2), "controls": ["deprivation"] + list(ctl_names),
           "median_x": sorted(x)[n // 2], "median_y": sorted(y)[n // 2]}
    # after allowing for deprivation: who spends much more/less than their need would suggest, and how are results
    rc = [rank(c) for c in ctls]
    rx, ry = zs(residuals_multi(rank(x), rc)), zs(residuals_multi(rank(y), rc))
    for p, a, b in zip(pts, rx, ry):
        p["sx"], p["sy"] = round(a, 2), round(b * better, 2)       # sy > 0 means better than expected
    hi_poor = sorted(pts, key=lambda p: -(p["sx"] - p["sy"]))
    lo_good = sorted(pts, key=lambda p: -(p["sy"] - p["sx"]))
    hp = [p for p in hi_poor if p["sx"] > 0.5 and p["sy"] < -0.5][:8]
    lg = [p for p in lo_good if p["sx"] < -0.5 and p["sy"] > 0.5][:8]
    fmt = lambda lst: [{"code": p["code"], "name": p["name"], "x": round(p["x"], 1), "y": round(p["y"], 1), "imd": round(p["imd"], 1), "sx": p["sx"], "sy": p["sy"]} for p in lst]
    res["high_spend_poor"], res["low_spend_good"] = fmt(hp), fmt(lg)
    return res, pts


# ------------------------------------------------------------------- build
def build(ro_path, cap_path, pop, waste_path, road_red_path, road_len_path, imd_lower_path, imd_upper_path, councils_info):
    """councils_info: {code: {"name", "group", "cls"}} from councils.build."""
    imd_lo, imd_up = read_imd(imd_lower_path, imd_upper_path)
    ro = read_cols(ro_path, WASTE_COLS + ROAD_COLS)
    cap = read_cols(cap_path, [CAP_ROAD], year_col="PeriodCode", code_col="ONS_Code", status_col="Status")
    waste = read_waste(waste_path)
    red = read_road_red(road_red_path)
    length = read_road_length(road_len_path)
    out = {"pairings": [], "sources": []}

    # ---- waste: spend per resident on collecting, recycling and disposing of waste vs recycling rate / residual waste
    def waste_spend(code):
        v = ro.get((OUTCOME_YEAR_WASTE, code))
        if not v:
            return None
        return sum(v.get(c) or 0 for c in WASTE_COLS) * 1000

    groups = []
    for g, label, filt in (("allpurpose", "Councils that collect and dispose of waste (unitary, metropolitan, London)", lambda i, w: i["group"] == "allpurpose"),
                           ("district", "District councils (collect waste; the county disposes)", lambda i, w: i["group"] == "district")):
        for outc, olab, better, unit in (("recycling_rate", "Household waste recycled, composted or reused", +1, "%"),
                                         ("residual_kg_hh", "Rubbish left over per household (not recycled)", -1, "kg")):
            pts = []
            for code, w in waste.items():
                i = councils_info.get(code)
                if not i or not filt(i, w) or code not in pop or pop[code]["pop"] < MIN_POP:
                    continue
                s = waste_spend(code)
                imd = (imd_lo if g == "district" else imd_up).get(code, imd_lo.get(code))
                pts.append({"code": code, "name": i["name"], "x": None if s is None else s / pop[code]["pop"], "y": w[outc], "imd": imd})
            a = analyse(pts, better)
            if a:
                groups.append({"group": g, "eligible": eligible(councils_info, g), "label": label, "outcome": outc, "outcome_label": olab, "better": better, "unit": unit, "y": {"suffix": unit if unit == "%" else " " + unit, "dp": 1 if unit == "%" else 0}, "stats": a[0],
                               "points": [{"c": p["code"], "n": p["name"], "x": round(p["x"], 2), "y": round(p["y"], 2), "d": round(p["imd"], 1)} for p in a[1]]})
    out["pairings"].append({"id": "waste", "title": "Waste and recycling", "service": "Environment and waste", "spend_label": "Spending on waste collection, recycling and disposal, £ per resident, " + OUTCOME_YEAR_WASTE,
                            "year": OUTCOME_YEAR_WASTE, "groups": groups, "x": {"prefix": "£", "dp": 0, "label": "Spending, £ per resident", "per": "resident"},
                            "notes": ["Spending is net revenue spending on waste collection, disposal, recycling and waste minimisation, plus the waste levy paid to joint disposal authorities. Trade (business) waste and street cleaning are excluded.",
                                      "Recycling rates are driven by what a council collects (separate food waste, garden waste charges, how bins are collected) as much as by how much it spends.",
                                      "District councils only collect; the county council disposes of what is collected, so their spending and results describe collection only."]})

    # ---- roads: maintenance spending (revenue plus capital) per km of locally managed road vs share of roads in poor condition
    groups = []
    for g, label in (("allpurpose", "Unitary, metropolitan and London councils"), ("county", "County councils")):
        for rk, rlab in (("A", "A roads and motorways needing maintenance"), ("BC", "B and C roads needing maintenance")):
            pts = []
            for code, i in councils_info.items():
                if i["group"] != g or code not in length or code not in red or rk not in red[code]:
                    continue
                tot, ok = 0.0, 0
                for y in ROAD_YEARS:
                    r, c = ro.get((y, code)), cap.get((y, code))
                    if r is None:
                        continue
                    tot += sum(r.get(k) or 0 for k in ROAD_COLS) * 1000 + ((c or {}).get(CAP_ROAD) or 0) * 1000
                    ok += 1
                if ok < 3 or length[code] < 50:
                    continue
                yrs = [y for y in (2023, 2024, 2025) if y in red[code][rk]]
                if len(yrs) < 3:
                    continue
                pts.append({"code": code, "name": i["name"], "x": tot / ok / length[code] / 1000, "y": sum(red[code][rk][y] for y in yrs) / 3,
                            "imd": (imd_up if g != "district" else imd_lo).get(code),
                            "ctl": [(pop[code]["pop"] / length[code]) if code in pop and pop[code]["pop"] >= MIN_POP else None]})
            a = analyse(pts, -1, ["people per km of road"])
            if a:
                groups.append({"group": g, "eligible": eligible(councils_info, g), "label": label, "outcome": "red_" + rk, "outcome_label": rlab + " (3-year average)", "better": -1, "unit": "%", "y": {"suffix": "%", "dp": 1}, "stats": a[0],
                               "points": [{"c": p["code"], "n": p["name"], "x": round(p["x"], 2), "y": round(p["y"], 2), "d": round(p["imd"], 1)} for p in a[1]]})
    out["pairings"].append({"id": "roads", "title": "Roads", "service": "Highways and transport", "spend_label": "Road maintenance spending (revenue plus capital), £ thousand per km of locally managed road a year, average 2022-23 to 2024-25",
                            "year": "2022-23 to 2024-25", "groups": groups, "x": {"prefix": "£", "suffix": "k", "dp": 1, "label": "Road maintenance, £ thousand per km a year", "per": "km of road"},
                            "notes": ["Spending adds revenue spending on structural and routine maintenance of roads and bridges to capital spending on roads, street lighting and road safety, averaged over three years, per kilometre of road the council manages (DfT road length statistics).",
                                      "Capital spending includes new roads, street lighting and safety schemes as well as resurfacing, and councils are also paid for roads by central government: the match is rough.",
                                      "Condition comes from machine surveys (SCANNER) reported to the nearest whole per cent, averaged over the last three years. Heavy-traffic and urban roads wear faster than quiet rural ones."]})
    out["sources"] = [
        {"title": "MHCLG revenue outturn (time series) and capital outturn (time series)", "publisher": "Ministry of Housing, Communities and Local Government"},
        {"title": "Local authority collected waste management: annual results 2024-25 (Table 3)", "publisher": "Defra"},
        {"title": "Road condition statistics RDC0120 and road length statistics RDL0202", "publisher": "Department for Transport"},
        {"title": "English indices of deprivation 2025: local authority district summaries (average score)", "publisher": "MHCLG"}]
    return out
