"""More council pairings: planning decisions, homelessness and children's social care (Ofsted).

Same method as outcomes.py: spending from the MHCLG revenue outturn, a result published by another body, joined by
ONS area code, councils compared only with councils of the same kind, before and after allowing for deprivation
and (where there is one) the underlying demand.
"""
import re

import ods
import outcomes as O

GRADES = {"outstanding": 4, "good": 3, "requires improvement to be good": 2, "inadequate": 1}
GRADE_LABEL = {4: "Outstanding", 3: "Good", 2: "Requires improvement", 1: "Inadequate"}
PLAN_COLS = ["RO5_plandvl_net_cur_exp", "RO5_planplc_cns_lst_bld_net_cur_exp", "RO5_planplc_oth_net_cur_exp"]
HOMELESS_COL = "RO4_housgfcfhml_hml_tot_net_cur_exp"
CSC_COL = "RS_csc_net_exp"
CODE_RE = re.compile(r"^E0[6-9]\d{6}$|^E10\d{6}$")


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- planning
def read_planning_speed(path, fy_end, sheet=None):
    """Share of decisions made on time (within 13 weeks / 8 weeks, or in the agreed time) over the four quarters of the
    financial year ending March `fy_end` (e.g. 2026). Returns {code: (pct, decisions)}."""
    book = ods.read_ods(path)
    name = sheet or next(k for k in book if k.startswith("Table_P15") and not k.endswith("b"))
    rows = book[name]
    hi = next(i for i, r in enumerate(rows) if r and str(r[0]).lower().startswith("local planning authority"))
    labels = rows[hi - 1]
    want = [f"April to June {fy_end - 1}", f"July to September {fy_end - 1}", f"October to December {fy_end - 1}", f"January to March {fy_end}"]
    starts = []
    for lab in want:
        j = next((i for i, x in enumerate(labels) if x and str(x).strip() == lab), None)
        if j is None:
            return {}
        starts.append(j)
    out = {}
    for r in rows[hi + 1:]:
        if not r or len(r) < 2 or not CODE_RE.match(str(r[1])):
            continue
        dec = ontime = 0.0
        for j in starts:
            vals = [fnum(r[j + k]) if len(r) > j + k else None for k in range(4)]
            if None in vals:
                dec = None
                break
            dec += vals[0]
            ontime += vals[1] + vals[3]
        if dec:
            out[str(r[1])] = (100.0 * ontime / dec, dec)
    return out


# ---------------------------------------------------------- homelessness
def _la_rows(rows):
    return [r for r in rows if r and CODE_RE.match(str(r[0]))]


def read_prevention_success(path):
    """Share of prevention duties that ended with accommodation secured for 6+ months (FY detailed tables, table P1)."""
    book = ods.read_ods(path)
    out = {}
    for r in _la_rows(book["P1"]):
        tot, sec = fnum(r[4]), fnum(r[6])
        if tot and tot >= 50 and sec is not None:
            out[str(r[0])] = (100.0 * sec / tot, tot)
    return out


def read_homeless_need(path):
    """Households threatened with or already homeless per 1,000 households (table A1)."""
    book = ods.read_ods(path)
    out = {}
    for r in _la_rows(book["A1"]):
        a, b = fnum(r[16]), fnum(r[17])
        if a is not None and b is not None:
            out[str(r[0])] = a + b
    return out


def read_temporary_accommodation(path):
    """Households in temporary accommodation per 1,000 households at the end of the quarter (table TA1)."""
    book = ods.read_ods(path)
    out = {}
    for r in _la_rows(book["TA1"]):
        ta, hh = fnum(r[4]), fnum(r[5])
        if ta is not None and hh:
            out[str(r[0])] = ta / hh
    return out


# ----------------------------------------------------------------- Ofsted
def read_ofsted(path):
    book = ods.read_ods(path)
    rows = book["Inspections_as_at_31_March"]
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "Web link")
    h = [str(x) for x in rows[hi]]
    oi = h.index("Overall effectiveness")
    out = {}
    for r in rows[hi + 1:]:
        if r and len(r) > oi and CODE_RE.match(str(r[1])):
            g = GRADES.get(str(r[oi]).strip().lower())
            if g:
                out[str(r[1])] = {"grade": g, "name": r[2], "date": str(r[4])[:10]}
    return out


# ------------------------------------------------------------------ build
def _fmt_points(a):
    return [{"c": p["code"], "n": p["name"], "x": round(p["x"], 2), "y": round(p["y"], 2), "d": round(p["imd"], 1)} for p in a[1]]


def build(ro_path, pop, councils_info, real, imd_lo, imd_up, spend_year, plan_p151, plan_p153, plan_fy_end, hom_fy_path, hom_ta_path, hom_year, ofsted_path):
    ro = O.read_cols(ro_path, PLAN_COLS + [HOMELESS_COL, CSC_COL])
    elig = lambda g: O.eligible(councils_info, g)
    pairings = []

    # ---- planning: net spending on development control and planning policy vs decisions made on time
    groups = []
    maj, non = read_planning_speed(plan_p151, plan_fy_end), read_planning_speed(plan_p153, plan_fy_end)
    for out_name, data, label in (("major", maj, "Major developments decided on time (13 weeks or agreed time)"), ("nonmajor", non, "Other applications decided on time (8 weeks or agreed time)")):
        pts = []
        for code, (pct, n) in data.items():
            i, v, p = councils_info.get(code), ro.get((spend_year, code)), pop.get(code)
            if not i or i["group"] not in ("allpurpose", "district") or not v or not p or p["pop"] < O.MIN_POP or n < 10:
                continue
            spend = sum(v.get(c) or 0 for c in PLAN_COLS) * 1000 / p["pop"]
            pts.append({"code": code, "name": i["name"], "x": spend, "y": pct, "imd": imd_lo.get(code), "ctl": [n / p["pop"] * 1000]})
        a = O.analyse(pts, +1, ["number of decisions per 1,000 residents"])
        if a:
            groups.append({"group": "planning", "eligible": elig("allpurpose") + elig("district"), "label": "Planning authorities (district, unitary, metropolitan and London councils)", "outcome": out_name, "outcome_label": label,
                           "better": +1, "unit": "%", "y": {"suffix": "%", "dp": 1}, "stats": a[0], "points": _fmt_points(a)})
    pairings.append({"id": "planning", "title": "Planning decisions", "service": "Planning and development", "year": f"{spend_year} (decisions April {plan_fy_end - 1} to March {plan_fy_end})",
                     "spend_label": f"Net spending on development control and planning policy, £ per resident, {spend_year}",
                     "x": {"prefix": "£", "dp": 0, "label": "Net spending on development control and planning policy, £ per resident", "per": "resident"}, "groups": groups,
                     "sources": [{"title": "Planning applications in England: live tables P151 and P153", "publisher": "MHCLG"}, {"title": "Revenue outturn (time series)", "publisher": "MHCLG"}, {"title": "English indices of deprivation 2025", "publisher": "MHCLG"}, {"title": "Mid-2024 population estimates", "publisher": "ONS"}],
                     "notes": ["Spending is what the council pays after fees: planning application fees cover much of the cost of development control, so net spending is small, can be negative, and mostly shows how much of the service the council subsidises.",
                               "The result is the share of decisions made inside the statutory time (13 weeks for major developments, 8 weeks for others) or an agreed extension. Extensions of time are common and count as on time, so the measure can be met without a quick decision.",
                               "Speed is not quality: a fast decision is not necessarily a good or a lawful one. Applications per resident, a measure of workload, is allowed for alongside deprivation."]})

    # ---- homelessness: spending vs prevention success and temporary accommodation
    prev = read_prevention_success(hom_fy_path)
    need = read_homeless_need(hom_fy_path)
    ta = read_temporary_accommodation(hom_ta_path)
    groups = []
    for key, data, label, better, y in (("prevention", prev, "Prevention duties that secured a home for 6+ months", +1, {"suffix": "%", "dp": 1}),
                                        ("ta", None, "Households in temporary accommodation per 1,000 households", -1, {"suffix": "", "dp": 1})):
        for g, glabel in (("allpurpose", "Unitary, metropolitan and London councils"), ("district", "District councils")):
            pts = []
            for code, i in councils_info.items():
                if i["group"] != g:
                    continue
                v, p = ro.get((hom_year, code)), pop.get(code)
                yv = data.get(code, (None,))[0] if data is not None else ta.get(code)
                if not v or not p or p["pop"] < O.MIN_POP or yv is None or code not in need:
                    continue
                s = (v.get(HOMELESS_COL) or 0) * 1000 / p["pop"]
                pts.append({"code": code, "name": i["name"], "x": s, "y": yv, "imd": imd_lo.get(code), "ctl": [need[code]]})
            a = O.analyse(pts, better, ["households threatened with or experiencing homelessness per 1,000"])
            if a:
                groups.append({"group": g, "eligible": elig(g), "label": glabel, "outcome": key, "outcome_label": label, "better": better, "unit": y["suffix"] or "households",
                               "y": y, "stats": a[0], "points": _fmt_points(a)})
    pairings.append({"id": "homelessness", "title": "Homelessness", "service": "Housing services", "year": hom_year,
                     "spend_label": f"Net spending on homelessness services, £ per resident, {hom_year}",
                     "x": {"prefix": "£", "dp": 0, "label": "Net spending on homelessness, £ per resident", "per": "resident"}, "groups": groups,
                     "sources": [{"title": "Statutory homelessness detailed local authority tables (A1, P1, TA1)", "publisher": "MHCLG"}, {"title": "Revenue outturn (time series)", "publisher": "MHCLG"}, {"title": "English indices of deprivation 2025", "publisher": "MHCLG"}, {"title": "Mid-2024 population estimates", "publisher": "ONS"}],
                     "notes": ["Spending drives results and results drive spending: a council with many households in temporary accommodation spends more on it, so a positive link between spending and temporary accommodation is expected and is not evidence that spending makes homelessness worse.",
                               "Allowing for the number of households who ask for help (threatened with or already homeless, per 1,000 households) helps, but cannot remove this feedback.",
                               "Prevention success is the share of households owed a prevention duty whose duty ended with accommodation secured for 6 months or more. Councils differ in how they record duties, and housing supply and rents in the area matter at least as much as council spending.",
                               "Temporary accommodation is counted at 31 March; some of it is paid for by councils beyond the line shown here, and costs differ greatly between London and elsewhere."]})

    # ---- children's social care: spending per child vs Ofsted overall judgement
    of = read_ofsted(ofsted_path)
    years = [y for y in ("2022-23", "2023-24", "2024-25") if y in real]
    groups = []
    for g, glabel in (("allpurpose", "Unitary, metropolitan and London councils"), ("county", "County councils")):
        pts = []
        for code, i in councils_info.items():
            if i["group"] != g or code not in of or code not in pop:
                continue
            vals = [(ro.get((y, code)) or {}).get(CSC_COL) for y in years]
            if any(x is None for x in vals) or pop[code]["age0_17"] < 5000:
                continue
            spend = sum(v * real[y] for v, y in zip(vals, years)) / len(years) * 1000 / pop[code]["age0_17"] / 1.0
            pts.append({"code": code, "name": i["name"], "x": spend, "y": float(of[code]["grade"]), "imd": (imd_up).get(code)})
        a = O.analyse(pts, +1)
        if a:
            summary = []
            for gr in (4, 3, 2, 1):
                xs = sorted(p["x"] for p in a[1] if p["y"] == gr)
                if xs:
                    summary.append({"grade": GRADE_LABEL[gr], "n": len(xs), "median": round(xs[len(xs) // 2], 0), "p25": round(xs[len(xs) // 4], 0), "p75": round(xs[(3 * len(xs)) // 4], 0)})
            groups.append({"group": g, "eligible": elig(g), "label": glabel, "outcome": "ofsted", "outcome_label": "Ofsted overall effectiveness of children's services", "better": +1, "unit": "grade",
                           "y": {"grades": {str(k): v for k, v in GRADE_LABEL.items()}}, "stats": a[0], "points": _fmt_points(a), "by_grade": summary})
    pairings.append({"id": "csc", "title": "Children's social care", "service": "Children's social care", "year": "2022-23 to 2024-25 spending; latest Ofsted inspections",
                     "spend_label": "Net spending on children's social care, £ per child aged 0-17 a year, average of 2022-23 to 2024-25 (2025-26 prices)",
                     "x": {"prefix": "£", "dp": 0, "label": "Children's social care, £ per child aged 0-17 a year (real, 3-year average)", "per": "child"}, "groups": groups,
                     "sources": [{"title": "Local authority inspection outcomes (underlying data)", "publisher": "Ofsted"}, {"title": "Revenue outturn (time series)", "publisher": "MHCLG"}, {"title": "English indices of deprivation 2025", "publisher": "MHCLG"}, {"title": "Mid-2024 population estimates", "publisher": "ONS"}],
                     "notes": ["The result is Ofsted's overall effectiveness judgement from each council's most recent full or short inspection (dates range from 2022 to 2026). It describes how well children are helped, protected and cared for, judged by inspectors.",
                               "A bad inspection can raise spending afterwards (an improvement plan, more social workers), so councils graded Inadequate sometimes spend more than those graded Good; the order of events matters and is not shown here.",
                               "Spending is the average of the three years to 2024-25 so that one year's costs (a single expensive placement) do not dominate. Deprivation is the only need adjustment: the number of children in care is not allowed for."]})
    return pairings
