"""Northern Ireland's 11 district councils: estimated net expenditure on services, from the Department for Communities (DfC).

DfC publishes no council spending by service, and no outturn. Its annual rate-statistics circular (Table 3, "comparison of
estimated net expenditure on services") gives each council's estimated net expenditure for the previous and the coming
rate year, which are the budgets councils submit when setting district rates. That is all the official data allows, and it
is shown as exactly that: planned (estimated) spending, with no service split. Read by pdftotext from the circular's text layer
and checked against the circular's own printed total.
"""
import re
import subprocess

COUNCILS = {  # name as printed in the DfC circular (normalised) -> ONS area code
    "antrimandnewtownabbey": "N09000001", "armaghbanbridgeandcraigavon": "N09000002", "belfast": "N09000003",
    "causewaycoastandglens": "N09000004", "derryandstrabane": "N09000005", "fermanaghandomagh": "N09000006",
    "lisburnandcastlereagh": "N09000007", "midandeastantrim": "N09000008", "midulster": "N09000009",
    "newrymourneanddown": "N09000010", "ardsandnorthdown": "N09000011",
}
NUM = r"(\d{1,3}(?:,\d{3})+)"
ROW = re.compile(NUM + r"\s+" + NUM + r"\s+(-?\d{1,3}(?:,\d{3})*)\s+(-?[\d.]+)%")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def discover(get_text, today=None, limit=20):
    """Newest rate-statistics circular PDF, found by trying DfC's landing pages (circular-lg-NNYYYY-rate-statistics)."""
    import datetime
    y0 = (today or datetime.date.today()).year
    for y in (y0, y0 - 1):
        for n in range(1, limit + 1):
            try:
                html = get_text(f"https://www.communities-ni.gov.uk/publications/circular-lg-{n:02d}{y}-rate-statistics")
            except Exception:
                continue
            for m in re.finditer(r'href="([^"]+\.pdf)"', html):
                if "rate-statistics" in m.group(1) and "covering-letter" not in m.group(1):
                    return m.group(1) if m.group(1).startswith("http") else "https://www.communities-ni.gov.uk" + m.group(1)
    raise RuntimeError("no DfC rate statistics circular found")


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout


def parse_table3(text):
    """-> (prior_label, current_label, {code: (prior, current)}, (total_prior, total_current))"""
    i = text.upper().find("COMPARISION OF ESTIMATED NET EXPENDITURE")
    if i < 0:
        i = text.upper().find("COMPARISON OF ESTIMATED NET EXPENDITURE")
    j = text.upper().find("TABLE 4", i)
    block = text[i:j]
    years = re.findall(r"(20\d\d/20\d\d)", block[:600])
    if len(years) < 2:
        raise RuntimeError("cannot read the two rate years from Table 3")
    out, total = {}, None
    # the label is whatever precedes the numbers on the row, possibly wrapped onto the line above
    lines = [ln.rstrip() for ln in block.split("\n")]
    pending = ""
    for ln in lines:
        m = ROW.search(ln)
        if not m:
            s = ln.strip()
            if s and not re.search(r"Net Expenditure|District Council|TABLE|COMPARI", s, re.I):
                pending = (pending + " " + s).strip()
            continue
        label = (pending + " " + ln[:m.start()].strip()).strip()
        pending = ""
        a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
        if "TOTAL" in label.upper():
            total = (a, b)
            continue
        code = COUNCILS.get(norm(label))
        if code is None:
            raise RuntimeError(f"unrecognised council {label!r} in Table 3")
        out[code] = (a, b)
    return years[0], years[1], out, total


def build(text, pop):
    import analysis as A
    prior_y, cur_y, rows, total = parse_table3(text)
    if len(rows) != 11 or total is None:
        raise RuntimeError(f"expected 11 councils and a total, found {len(rows)} and {total}")
    councils = []
    for code, (a, b) in sorted(rows.items(), key=lambda kv: pop[kv[0]]["name"]):
        p = pop[code]
        councils.append({"code": code, "name": p["name"], "pop": {"pop": round(p["pop"]), "age0_17": round(p["age0_17"]), "age65": round(p["age65"])},
                         "v": {"net": b / 1000}, "prev": {"net": a / 1000}})
    checks = [
        A._check("dev_ni_count", "Northern Ireland: all 11 councils found in the DfC table (count)", [("councils", 11, len(rows))], 0),
        A._check("dev_ni_total_cur", f"Northern Ireland: the 11 councils' estimated net expenditure for {cur_y} add up to the circular's printed total (£)", [(cur_y, total[1], sum(b for _, b in rows.values()))], 0),
        A._check("dev_ni_total_prior", f"Northern Ireland: the 11 councils' estimated net expenditure for {prior_y} add up to the circular's printed total (£)", [(prior_y, total[0], sum(a for a, _ in rows.values()))], 0),
    ]
    s = sum(p["pop"] for k, p in pop.items() if k.startswith("N09"))
    checks.append(A._check("dev_pop_n09", "Northern Ireland: council area populations add up to the ONS Northern Ireland total (people)", [("mid-2024", pop["N92000002"]["pop"], s)], 1))
    for c in checks:
        c["source"] = "Local councils (Scotland, Wales, Northern Ireland)"
    vals = sorted(c["v"]["net"] * 1000 / c["pop"]["pop"] for c in councils)
    import statistics
    return {
        "id": "northern_ireland", "label": "Northern Ireland", "year": cur_y, "prior_year": prior_y, "years": [cur_y], "unit": "£ thousand", "single_year": True, "estimates": True,
        "services": [{"key": "net", "label": "Estimated net expenditure on services", "denom": "pop"}],
        "councils": councils,
        "stats": [{"key": "net", "n": 11, "median": round(statistics.median(vals), 2), "p10": round(vals[1], 2), "p90": round(vals[-2], 2)}],
        "peer_note": "All 11 councils are compared with each other. Belfast is by far the largest council and the only city with the services of a capital.",
        "notes": [
            "Northern Ireland's councils are much smaller than councils in the rest of the UK in what they do: they do not run education, social care, housing or roads (these are run by Northern Ireland departments). Their services are mainly waste, leisure and recreation, economic development, planning, building control, cemeteries and community services.",
            "The Department for Communities publishes no council spending by service, and no actual outturn. These figures are each council's estimated net expenditure on services for the rate year, set when district rates are fixed (Table 3 of the annual rate statistics circular). They are plans, not what was actually spent.",
            "For actual spending by service, each council's own audited accounts are the official source; the Local Government Auditor's annual report (NI Audit Office) gives Northern Ireland totals by service category.",
        ],
    }, checks
