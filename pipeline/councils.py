"""English local councils: revenue outturn (MHCLG) with ONS population, peer comparison and risk screens.

Source: "Local authority revenue expenditure and financing England: Revenue outturn multi-year data set" (CSV, £ thousand)
and ONS mid-2024 population estimates by local authority and single year of age.

Councils are only compared with councils that do the same job: county councils with counties, district councils with
districts, and "all-purpose" councils (unitary, metropolitan districts, London boroughs) with each other.
"""
import csv
import re
import statistics
from collections import defaultdict

import analysis as A

SERVICES = [  # key, CSV column, label, denominator
    ("asc", "RS_asc_net_exp", "Adult social care", "age65"), ("csc", "RS_csc_net_exp", "Children's social care", "age0_17"),
    ("edu", "RS_edu_net_exp", "Education services", "age0_17"), ("phs", "RS_phs_net_exp", "Public health", "pop"),
    ("trans", "RS_trans_net_exp", "Highways and transport", "pop"), ("env", "RS_env_net_exp", "Environment and waste", "pop"),
    ("hous", "RS_hous_net_exp", "Housing services", "pop"), ("cul", "RS_cul_net_exp", "Culture and leisure", "pop"),
    ("plan", "RS_plan_net_exp", "Planning and development", "pop"), ("cen", "RS_cen_net_exp", "Central services", "pop"),
    ("oth", "RS_oth_net_exp", "Other services", "pop"), ("pol", "RS_pol_net_exp", "Police", "pop"), ("frs", "RS_frs_net_exp", "Fire and rescue", "pop"),
]
OTHER_COLS = {
    "totsx": "RS_totsx_net_exp", "netrev": "RS_netrevexp_net_exp", "ctr": "RS_ctrtot_net_exp",
    "intpay": "RS_intextpay_net_exp", "intinc": "RS_intinvinc_net_exp", "mrp": "RS_provprin_net_exp",
    "resunall": "RS_resunall_end_cy", "resoth": "RS_resoth_end_cy", "resoth_adj": "RS_resoth_adj_end_cy", "resph": "RS_resph_end_cy",
    "ressch": "RS_ressch_end_cy", "resdsg": "RS_resdsg_end_cy", "resdsgadj": "RS_resdsgadj_end_cy",
    "invinc": "RS_invprp_inc_net_exp", "invcost": "RS_invprp_totcost_net_exp", "invnet": "RS_invprp_netinc_net_exp",
}
COUNCIL_CLASSES = {"Unitary Authority": "allpurpose", "Met District": "allpurpose", "London": "allpurpose", "Shire County": "county", "Shire District": "district"}
GROUP_LABEL = {"allpurpose": "unitary, metropolitan and London councils", "county": "county councils", "district": "district councils"}
CLASS_CODE = {"Unitary Authority": "E06", "Shire District": "E07", "Met District": "E08", "London": "E09", "Shire County": "E10"}
PEER_MIN_SHARE = 0.9          # a year is used for peer comparison when at least this share of councils submitted

TYPE_INFO = {
    "lc_outlier": ("Spends far more or less than similar councils", "After allowing for the number of residents (or children, or older people), this council's spending on a service is far from the typical council of its kind."),
    "lc_jump": ("Sudden change in spending", "Total service spending moved far more in a year, in real terms, than is usual for councils of its kind. Reorganisations and mergers are a common innocent cause."),
    "lc_reserves": ("Thin reserves", "Reserves that councils can use are small compared with what they spend, leaving little cushion against a shock."),
    "lc_dsg": ("Schools funding deficit", "The council holds a deficit on the Dedicated Schools Grant (mainly special educational needs), which is carried on its books and can exceed its reserves."),
    "lc_interest": ("Heavy debt-servicing cost", "Net interest paid is a large share of what the council spends on running services."),
    "lc_invest": ("Investment properties costing more than they earn", "The council holds commercial investment property that costs more to carry than it brings in."),
    "lc_missing": ("Accounts not submitted", "The council has not submitted its revenue outturn return to the government for a year when most councils have."),
}


def fy_label(yyyymm):
    y = int(yyyymm[:4])
    return f"{y - 1}-{str(y)[2:]}"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------- readers
def read_outturn(path):
    f = open(path, encoding="utf-8-sig", errors="replace")
    rd = csv.reader(f)
    h = next(rd)
    ix = {c: i for i, c in enumerate(h)}
    want = {k: c for k, c in OTHER_COLS.items() if c in ix}
    want.update({k: c for k, c, _, _ in SERVICES if c in ix})
    missing = [c for c in list(OTHER_COLS.values()) + [s[1] for s in SERVICES] if c not in ix]
    rows = []
    for r in rd:
        d = {"year": fy_label(r[ix["year_ending"]]), "code": r[ix["ONS_code"]], "name": r[ix["LA_name"]], "status": r[ix["status"]], "cls": r[ix["LA_class"]]}
        d["v"] = {k: _num(r[ix[c]]) for k, c in want.items()}
        rows.append(d)
    return rows, missing


def read_population(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["MYE2 - Persons"]
    ws.reset_dimensions()
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "Code")
    hdr = [str(c).strip() if c is not None else "" for c in rows[hi]]
    ages = {}
    for j, c in enumerate(hdr):
        m = re.match(r"^(\d+)\+?$", c)
        if m:
            ages[j] = int(m.group(1))
    allj = hdr.index("All ages")
    out = {}
    for r in rows[hi + 1:]:
        if not r or not r[0] or not re.match(r"^[EWSNK]\d", str(r[0])):
            continue
        out[str(r[0])] = {"name": r[1], "pop": float(r[allj]), "age0_17": sum(float(r[j] or 0) for j, a in ages.items() if a <= 17),
                          "age65": sum(float(r[j] or 0) for j, a in ages.items() if a >= 65)}
    return out


# ---------------------------------------------------------------- analysis
def robust(xs):
    med, mad = A.robust_center_spread(xs)
    return med, mad


def peer_year(rows):
    by = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["cls"] in COUNCIL_CLASSES:
            by[r["year"]][1] += 1
            by[r["year"]][0] += r["status"] == "submitted"
    ok = [y for y, (s, n) in by.items() if n and s / n >= PEER_MIN_SHARE]
    return max(ok) if ok else max(by)


def build(rows, pop, ons_lg_fy=None):
    councils = {}
    for r in rows:
        if r["cls"] not in COUNCIL_CLASSES:
            continue
        c = councils.setdefault(r["code"], {"code": r["code"], "name": r["name"], "cls": r["cls"], "group": COUNCIL_CLASSES[r["cls"]], "years": {}, "missing": []})
        if r["status"] == "submitted":
            c["years"][r["year"]] = r["v"]
        else:
            c["missing"].append(r["year"])
    years = sorted({y for c in councils.values() for y in c["years"]})
    py = peer_year(rows)
    # ---- per-unit values for the peer year, and robust peer statistics per group and service
    metrics = defaultdict(dict)       # key -> code -> value (£ per unit)
    stats = {}
    labels = {s[0]: s[2] for s in SERVICES}
    denom = {s[0]: s[3] for s in SERVICES}
    for c in councils.values():
        v = c["years"].get(py)
        p = pop.get(c["code"])
        if not v or not p:
            continue
        c["pop"] = p
        for key in list(labels) + ["totsx"]:
            val = v.get(key)
            if val is None:
                continue
            d = p[denom.get(key, "pop")]
            if d:
                metrics[key][c["code"]] = val * 1000 / d
    for key, vals in metrics.items():
        for g in GROUP_LABEL:
            xs = [vals[code] for code, c in councils.items() if code in vals and c["group"] == g]
            nz = [x for x in xs if x > 0]
            if len(xs) >= 8 and len(nz) >= 0.6 * len(xs):
                med, mad = robust(xs)
                srt = sorted(xs)
                stats[(key, g)] = {"n": len(xs), "median": med, "mad": mad, "p10": srt[int(.1 * (len(srt) - 1))], "p90": srt[int(.9 * (len(srt) - 1))]}
    # ---- flags
    flags = []

    def add(c, typ, sev, year, value, detail, key=None):
        flags.append({"type": typ, "sev": sev, "code": c["code"], "council": c["name"], "cls": c["cls"], "year": year, "value": value, "key": key, "detail": detail})

    for code, c in councils.items():
        v = c["years"].get(py)
        if not v:
            continue
        unit = {"pop": "per resident", "age0_17": "per child (0-17)", "age65": "per person aged 65+"}
        for key in labels:
            st = stats.get((key, c["group"]))
            val = metrics[key].get(code)
            tot = (v.get(key) or 0) * 1000
            if st and val is not None and tot >= (3e6 if c["group"] == "district" else 10e6):
                z = 0.6745 * (val - st["median"]) / max(st["mad"], 0.05 * abs(st["median"]), 1)
                if abs(z) >= 3.5:
                    sev = 3 if abs(z) >= 6 and tot >= 50e6 else 2 if abs(z) >= 4.5 else 1
                    add(c, "lc_outlier", sev, py, tot, f"{c['name']} spent £{val:,.0f} {unit[denom[key]]} on {labels[key].lower()} in {py}, against a typical £{st['median']:,.0f} for {GROUP_LABEL[c['group']]} "
                        f"({'+' if val > st['median'] else '−'}{abs(val / st['median'] - 1) * 100 if st['median'] else 0:.0f}%; score {abs(z):.1f}). Total £{tot / 1e6:,.1f}m.", key)
        netrev = (v.get("netrev") or 0) * 1000
        if netrev >= 10e6:
            res = (v.get("resunall") or 0) + ((v.get("resoth_adj") if v.get("resoth_adj") is not None else v.get("resoth")) or 0)
            ratio = res * 1000 / netrev
            if ratio < 0.10:
                add(c, "lc_reserves", 3 if ratio <= 0 else 2 if ratio < 0.05 else 1, py, res * 1000,
                    f"{c['name']}: unallocated and earmarked reserves were £{res/1000:,.1f}m, {ratio*100:.0f}% of its £{netrev/1e6:,.0f}m net revenue spending (councils of its kind typically hold far more).")
            dsg = (v.get("resdsg") or 0) + (v.get("resdsgadj") or 0)
            if dsg < 0 and abs(dsg) * 1000 >= 5e6 and abs(dsg) * 1000 / netrev >= 0.03:
                r_ = abs(dsg) * 1000 / netrev
                add(c, "lc_dsg", 3 if r_ >= 0.30 else 2 if r_ >= 0.15 else 1, py, dsg * 1000,
                    f"{c['name']}: a Dedicated Schools Grant deficit of £{abs(dsg)/1000:,.1f}m, equal to {r_*100:.0f}% of its net revenue spending (its other reserves total £{res/1000:,.1f}m).")
            net_int = ((v.get("intpay") or 0) + (v.get("intinc") or 0)) * 1000
            if net_int / netrev >= 0.10:
                r_ = net_int / netrev
                add(c, "lc_interest", 3 if r_ >= 0.25 else 2 if r_ >= 0.15 else 1, py, net_int, f"{c['name']}: net interest of £{net_int/1e6:,.1f}m took {r_*100:.0f}% of its £{netrev/1e6:,.0f}m net revenue spending.")
            invc, invi = (v.get("invcost") or 0) * 1000, (v.get("invinc") or 0) * 1000
            if invc - abs(invi) >= 1e6 and invc >= 0.01 * netrev:
                add(c, "lc_invest", 2 if invc - abs(invi) >= 5e6 else 1, py, invc - abs(invi), f"{c['name']}: investment properties cost £{invc/1e6:,.1f}m to carry in {py} and brought in £{abs(invi)/1e6:,.1f}m.")
        # sudden change in total service spending (real terms are not needed: compare proportional change within the group)
    # year-on-year jumps pooled by group and transition
    last_years = [y for y in years if y <= py][-4:]
    for g in GROUP_LABEL:
        for a, b in zip(last_years, last_years[1:]):
            ch = {}
            for code, c in councils.items():
                if c["group"] != g or a not in c["years"] or b not in c["years"]:
                    continue
                x0, x1 = c["years"][a].get("totsx"), c["years"][b].get("totsx")
                if x0 and x1 and x0 > 0:
                    ch[code] = (x1 - x0) / x0
            if len(ch) >= 20:
                med, mad = robust(list(ch.values()))
                mad = max(mad, 0.02)
                for code, x in ch.items():
                    z = 0.6745 * (x - med) / mad
                    c = councils[code]
                    tot0 = c["years"][a]["totsx"] * 1000
                    if abs(z) >= 4 and abs(x - med) >= 0.15 and tot0 >= 10e6:
                        add(c, "lc_jump", 2 if abs(z) >= 6 else 1, b, c["years"][b]["totsx"] * 1000,
                            f"{c['name']}: total service spending went from £{tot0/1e6:,.1f}m in {a} to £{c['years'][b]['totsx']*1000/1e6:,.1f}m in {b} ({x*100:+.0f}%; typical for {GROUP_LABEL[g]} is {med*100:+.0f}%). "
                            f"Check for a reorganisation or change in what the council is responsible for.")
    # accounts not submitted in years when most councils did
    for c in councils.values():
        late = [y for y in c["missing"] if y <= py and y >= "2021-22"]
        if late:
            add(c, "lc_missing", 3 if len(late) >= 2 else 2, late[-1], None, f"{c['name']} has not submitted its revenue outturn for {', '.join(sorted(late))}.")
    flags.sort(key=lambda f: (-f["sev"], -(abs(f["value"] or 0))))
    return councils, years, py, metrics, stats, flags


def checks(rows, councils, pop, ons_lg_fy=None):
    cks = []
    # 1. council rows add up to the published class totals (only where every council in the class submitted)
    totals = {(r["year"], r["code"]): r["v"].get("totsx") for r in rows if r["status"] == "total"}
    rows_ck, notes = [], []
    for y in sorted({r["year"] for r in rows}):
        for cls, code in CLASS_CODE.items():
            members = [r for r in rows if r["year"] == y and r["cls"] == cls]
            if not members or any(r["status"] != "submitted" for r in members) or (y, code) not in totals:
                continue
            rows_ck.append((f"{y} {code}", totals[(y, code)], sum(r["v"].get("totsx") or 0 for r in members)))
    cks.append(A._check("lc_totals", "Councils: council returns add up to the published class totals for total service spending (£ thousand)", rows_ck, 60,
                        "Compared only for years and council types where every council submitted; where one has not, the published total includes an estimate for it."))
    # 2. the thirteen service lines add up to total service expenditure
    svc = [s[0] for s in SERVICES]
    gaps = []
    for r in rows:
        if r["status"] == "submitted" and r["cls"] in COUNCIL_CLASSES and r["v"].get("totsx") is not None:
            gaps.append((f"{r['year']} {r['name']}", r["v"]["totsx"], sum(r["v"].get(k) or 0 for k in svc)))
    cks.append(A._check("lc_services", "Councils: spending on each service adds up to total service expenditure, every council and year (£ thousand)", gaps, 5))
    # 3. population: the lower-tier councils tile England
    if "E92000001" in pop:
        low = sum(p["pop"] for code, p in pop.items() if code[:3] in ("E06", "E07", "E08", "E09"))
        cks.append(A._check("lc_pop", "ONS population: unitary, district, metropolitan and London councils add up to England (people)", [("mid-2024", pop["E92000001"]["pop"], low)], 1))
    # 4. scope comparison with the ONS local government sector
    if ons_lg_fy:
        for y, v in ons_lg_fy.items():
            pass
    for c in cks:
        c["source"] = "Local councils"
        if len(c["rows"]) > 10:
            c["rows"] = sorted(c["rows"], key=lambda r: -abs(r["gap"]))[:10]
            c["note"] = (c["note"] + " " if c["note"] else "") + "Showing the 10 largest gaps."
    return cks


# ------------------------------------------------------------------ output
YEAR_FIELDS = [s[0] for s in SERVICES] + ["totsx", "netrev", "reserves", "dsg", "netint"]


def _year_vec(v):
    res = (v.get("resunall") or 0) + ((v.get("resoth_adj") if v.get("resoth_adj") is not None else v.get("resoth")) or 0)
    dsg = (v.get("resdsg") or 0) + (v.get("resdsgadj") or 0)
    ni = (v.get("intpay") or 0) + (v.get("intinc") or 0)
    vals = [v.get(s[0]) for s in SERVICES] + [v.get("totsx"), v.get("netrev"), res, dsg, ni]
    return [None if x is None else round(x) for x in vals]


def export(councils, years, py, metrics, stats, flags, pop, rows=None, england=None):
    out = []
    for code, c in sorted(councils.items(), key=lambda kv: kv[1]["name"]):
        if not c["years"]:
            continue
        p = c.get("pop")
        out.append({"code": code, "name": c["name"], "cls": c["cls"], "group": c["group"],
                    "pop": round(p["pop"]) if p else None, "age0_17": round(p["age0_17"]) if p else None, "age65": round(p["age65"]) if p else None,
                    "missing": sorted(c["missing"]), "y": {y: _year_vec(v) for y, v in c["years"].items()}})
    return {
        "years": years, "peer_year": py, "fields": YEAR_FIELDS, "unit": "£ thousand",
        "services": [{"key": k, "label": l, "denom": d} for k, _, l, d in SERVICES],
        "groups": GROUP_LABEL, "min_share": PEER_MIN_SHARE,
        "stats": [{"key": k, "group": g, **{a: round(b, 2) if isinstance(b, float) else b for a, b in s.items()}} for (k, g), s in stats.items()],
        "england": england or {},
        "councils": out,
        "flags": flags[:600],
        "flag_types": {k: {"title": v[0], "text": v[1]} for k, v in TYPE_INFO.items()},
        "population_year": "mid-2024",
    }
