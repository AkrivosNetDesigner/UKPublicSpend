"""National pairings: school spending against school results over time (England results, UK spending).

Results come from the Department for Education's explore-education-statistics API (key stage 2 and key stage 4,
and the January school census for pupil numbers). Spending is the Treasury's Education function from Public Spending
Statistics Table 4.3, in real terms. With about ten annual points, exam systems that changed, and pandemic years graded
differently, no correlation is calculated: the series are shown side by side with what changed.
"""
import csv
import gzip
import io

TOTALS = ("sex", "disadvantage_status", "fsm_status", "ethnicity_major", "ethnicity_minor", "first_language", "month_of_birth", "sen_provision", "sen_primary_need")


def ay(code):
    """'201617' -> '2016-17'"""
    return f"{code[:4]}-{code[4:]}"


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None          # DfE suppression markers: x, z, c, u, low


def rows_from_csv_bytes(raw):
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def ks2_series(rows):
    """% of pupils meeting the expected standard in reading, writing and maths, England, all state-funded."""
    out = {}
    for r in rows:
        if (r["geographic_level"] == "National" and r["establishment_type_group"] == "All state funded" and r["subject"] == "Reading, writing and maths"
                and all(r.get(c) == "Total" for c in TOTALS if c in r)):
            v = num(r["expected_standard_pupil_percent"])
            if v is not None:
                out[ay(r["time_period"])] = v
    return out


def ks4_series(rows):
    """Attainment 8 average and % achieving grade 5 or above in English and maths, England, all state-funded."""
    a8, em = {}, {}
    for r in rows:
        if (r["geographic_level"] == "National" and r["establishment_type_group"] == "All state-funded" and r["breakdown_topic"] == "Total"
                and all(r.get(c) == "Total" for c in ("sex", "ethnicity_major", "fsm_status", "sen_provision", "sen_status", "disadvantage_status", "first_language", "prior_attainment", "school_admission_type"))):
            y = ay(r["time_period"])
            if num(r["attainment8_average"]) is not None:
                a8[y] = num(r["attainment8_average"])
            if num(r["engmath_95_percent"]) is not None:
                em[y] = num(r["engmath_95_percent"])
    return a8, em


def pupil_series(rows):
    """State-funded school pupils in England (January census) and the share eligible for free school meals."""
    tot, fsm = {}, {}
    for r in rows:
        if r["geographic_level"] == "National" and r["phase_type_grouping"] == "Total" and r["fsm_breakdown"] == "All pupils" and r["fsm_eligibility"] == "Total":
            tot[ay(r["time_period"])] = num(r["pupil_count"])
        if r["geographic_level"] == "National" and r["phase_type_grouping"] == "Total" and r["fsm_breakdown"].startswith("FSM eligible - taking free school meal on census date"):
            fsm[ay(r["time_period"])] = num(r["pupil_percent"])
    return tot, fsm


def build(ks2_rows, ks4_rows, pupil_rows, fn_years, fn_real):
    """fn_years/fn_real: Treasury function years and real £bn for 'Education' (UK, all levels)."""
    ks2 = ks2_series(ks2_rows)
    a8, em = ks4_series(ks4_rows)
    pupils, fsm = pupil_series(pupil_rows)
    spend = dict(zip(fn_years, fn_real))
    years = sorted(y for y in pupils if y in spend and y >= "2016-17")
    per_pupil = {y: spend[y] * 1e9 / pupils[y] for y in years}
    return {
        "years": years,
        "spend_real_bn": {y: round(spend[y], 2) for y in years},
        "pupils": {y: round(pupils[y]) for y in years},
        "fsm_pct": {y: fsm.get(y) for y in years},
        "per_pupil": {y: round(per_pupil[y]) for y in years},
        "ks2_rwm": {y: ks2.get(y) for y in years},
        "ks4_a8": {y: a8.get(y) for y in years},
        "ks4_em95": {y: em.get(y) for y in years},
        "teacher_graded": ["2019-20", "2020-21"],
        "generous_grading": ["2021-22"],
        "notes": [
            "Spending is the Treasury's Education function for the whole UK at every level (early years to universities, including student support), in 2025-26 prices, divided by state-funded school pupils in England: a trend indicator, not what a school receives per pupil.",
            "Key stage 2 tests were not held in 2019-20 and 2020-21. GCSE and A level grades in 2019-20 and 2020-21 were set by teachers, and 2021-22 grading was deliberately generous as results moved back towards normal, so those years are not comparable.",
            "Attainment 8 and the 9 to 1 GCSE grades were phased in from 2016-17; earlier years are not comparable and are omitted.",
            "School results depend on far more than spending: pupil intake, teacher supply, curriculum and exam changes, and the pandemic.",
        ],
    }
