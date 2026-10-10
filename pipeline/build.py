#!/usr/bin/env python3
"""Download the HM Treasury workbooks and build site/data/*.json.

    python3 pipeline/build.py            # uses ./raw as a download cache

Only files listed in pipeline/sources.json are fetched; they are all published
via the two permitted GOV.UK collections.
"""
import datetime
import json
import os
import ssl
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import analysis as A  # noqa: E402
import hmrc as H  # noqa: E402
import ons as O  # noqa: E402
import dwp as W  # noqa: E402
import procurement as PR  # noqa: E402
import borrowing as B  # noqa: E402
import councils as L  # noqa: E402
import outcomes as OC  # noqa: E402
import parse as P  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "site" / "data"


def fetch(key, meta):
    dest = RAW / (key + os.path.splitext(meta["url"])[1])
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    RAW.mkdir(exist_ok=True)
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    print("downloading", meta["url"])
    req = urllib.request.Request(meta["url"], headers={"User-Agent": "UKPublicSpend/1.0"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        dest.write_bytes(r.read())
    return dest


DMO = "https://www.dmo.gov.uk"
BOE = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom={frm}&Dateto=now&SeriesCodes={codes}"
       "&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")


def fresh(dest, url, hours=20):
    """Download unless a copy younger than `hours` exists (these sources update daily, quarterly or annually)."""
    import time
    if dest.exists() and dest.stat().st_size > 500 and time.time() - dest.stat().st_mtime < hours * 3600:
        return dest
    RAW.mkdir(exist_ok=True)
    if callable(url):                      # a link that has to be discovered: only look it up when a download is needed
        try:
            url = url()
        except Exception as e:
            if dest.exists() and dest.stat().st_size > 500:
                print(f"could not find a newer link for {dest.name} ({e}); using the copy already downloaded")
                return dest
            raise
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    print("downloading", url[:110])
    req = urllib.request.Request(url, headers={"User-Agent": "UKPublicSpend/1.0"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        dest.write_bytes(r.read())
    return dest


def discover(page, pattern):
    """The DMO re-issues its spreadsheets under new file addresses, so find the current link on the page."""
    import re
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    html = urllib.request.urlopen(urllib.request.Request(page, headers={"User-Agent": "UKPublicSpend/1.0"}), timeout=60, context=ctx).read().decode("utf-8", "ignore")
    links = [h for h in re.findall(r'href="([^"]+\.xls[x]?)"', html) if pattern in h]
    if not links:
        raise RuntimeError(f"no link containing {pattern!r} on {page}")
    return links[0] if links[0].startswith("http") else DMO + links[0]


def dump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def round_m(k):
    return round(k / 1000.0, 3)


def main():
    src = json.loads((Path(__file__).parent / "sources.json").read_text())
    paths = {k: fetch(k, m) for k, m in src["files"].items()}

    # ---- long-run aggregates (Table 4.1) and functions (4.2 / 4.3 / 4.4)
    agg = P.parse_aggregates(paths["pss2026_ch4"])
    c4 = paths["pss2026_ch4"]
    f42, f43, f44 = (P.parse_wide(c4, s) for s in ("4_2", "4_3", "4_4"))
    functions = {"years": f42[0], "nominal": f42[1], "real": f43[1], "gdp": f44[1]}

    # ---- Table 1.1
    t11 = P.parse_table_1_1(paths["pss2026_ch1"])

    # ---- regions (Chapter 9)
    c9 = paths["pss2026_ch9"]
    ry, abs_rows, hi = P.parse_region_block(c9, "9.1a")
    _, comp_rows, _ = P.parse_region_block(c9, "9.1a", hi + 1)
    comp = {r["label"]: r["values"] for r in comp_rows}
    tme9 = comp.get("Total Managed Expenditure")
    regions = {"years": ry,
               "nominal": abs_rows,
               "perhead": P.parse_region_block(c9, "9.1b")[1],
               "real": P.parse_region_block(c9, "9.2a")[1],
               "realperhead": P.parse_region_block(c9, "9.2b")[1],
               "composition": comp_rows}
    region_for_checks = {"abs": (ry, abs_rows), "tme": {"years": ry, "values": tme9} if tme9 else None}

    # ---- price adjustment factor (Table 4.1: real / nominal Total Managed Expenditure)
    real_factor = {a["year"]: a["tme_real"] / a["tme"] for a in agg if a["tme"]}

    # ---- database releases
    rel_keys = ["2024", "2025", "2026"]
    rows_by = {k: P.parse_database(paths[f"pss{k}_db"]) for k in rel_keys}
    segs_by = {k: A.build_segments(rows_by[k]) for k in rel_keys}
    latest = "2026"
    rows, segs = rows_by[latest], segs_by[latest]
    years = sorted({r["year"] for r in rows})

    # departments
    dept = defaultdict(lambda: {"cat": defaultdict(lambda: defaultdict(float)),
                                "group": defaultdict(lambda: defaultdict(float)),
                                "segs": defaultdict(float)})
    dbtotals = defaultdict(lambda: defaultdict(float))
    for r in rows:
        d = dept[r["dept"]]
        d["cat"][f'{r["ctrl"]} {r["econ"].lower()}'][r["year"]] += r["amount"]
        d["group"][r["group"]][r["year"]] += r["amount"]
        d["segs"][r["code"]] += abs(r["amount"])
        dbtotals[r["year"]][r["ctrl"]] += r["amount"]
    depts = []
    for name, d in dept.items():
        total = [round_m(sum(c[y] for c in d["cat"].values())) for y in years] if False else \
            [round_m(sum(c.get(y, 0) for c in d["cat"].values())) for y in years]
        depts.append({
            "name": name, "total": total,
            "cat": {k: [round_m(v.get(y, 0)) for y in years] for k, v in d["cat"].items()},
            "group": {k: [round_m(v.get(y, 0)) for y in years] for k, v in d["group"].items()
                      if any(v.get(y, 0) for y in years)},
            "nseg": len(d["segs"]),
        })
    depts.sort(key=lambda d: -abs(d["total"][-1]))
    dump("departments.json", {"years": years, "depts": depts})

    # segments
    seg_out = []
    for code, s in segs.items():
        seg_out.append({"c": code, "n": s["name"], "d": s["dept"].get(years[-1]) or next(iter(s["dept"].values())),
                        "g": s["group"], "t": s["ctrl"], "v": [round_m(s["vals"].get(y, 0)) for y in years]})
    seg_out.sort(key=lambda s: -max(abs(x) for x in s["v"]))
    dump("segments.json", {"years": years, "segs": seg_out})

    # ---- anomaly detection
    flags = A.segment_flags(segs, years)
    flags += A.revision_flags(rel_keys, segs_by)
    ranked = A.rank_segments(flags, segs)
    for f in flags:
        f["value"] = round_m(f["value"])
        f["prev"] = None if f["prev"] is None else round_m(f["prev"])
        if "delta" in f:
            f["delta"] = round_m(f["delta"])
    flags.sort(key=lambda f: (-f["sev"], -abs(f["value"] - (f["prev"] or 0)), f["code"]))
    fn_flags = A.function_flags(functions["years"], functions["real"])
    benford = A.benford_by_dept(rows)
    opacity = A.opacity(rows, years)
    rev = A.revision_summary(rel_keys, rows_by, latest)
    rev_out = {d: {y: {r: round_m(v) for r, v in rels.items()} for y, rels in ys.items()} for d, ys in rev.items()}

    checks = A.integrity_checks(t11, agg, f42, f43, region_for_checks, {"dbtotals": dbtotals})
    for c in checks:
        c["source"] = "HM Treasury"

    # ---- HMRC: monthly/annual receipts and tax gap
    rec = H.parse_receipts(paths["hmrc_receipts"])
    gap = H.parse_tax_gap(paths["hmrc_taxgap"])
    rev_sum = H.taxgap_revision_summary(gap["revisions"])
    hflags = H.monthly_flags(rec["months"], rec["receipts_m"]) + H.taxgap_flags(rev_sum)
    checks += H.hmrc_checks(rec, gap)
    # ---- DWP: fraud and error in the benefit system
    dwp, dflags, dchecks = W.build({"2024": paths["dwp_2024"], "2025": paths["dwp_2025"], "2026": paths["dwp_2026"]})
    checks += dchecks + [W.dwp_vs_treasury(dwp, t11, rec)]
    dump("dwp.json", {**dwp, "flags": dflags, "flag_types": {k: {"title": v[0], "text": v[1]} for k, v in W.DWP_FLAG_TEXT.items()}})

    # ---- Contracts Finder award notices (downloaded separately by fetch_contracts.py)
    cache = RAW / "cf_awards.jsonl"
    if "--skip-contracts" in sys.argv:
        print("procurement: skipped (--skip-contracts); existing site/data/procurement.json left as is")
    elif cache.exists():
        recs = [json.loads(line) for line in cache.open()]
        proc, pchecks = PR.build(recs)
        checks += pchecks
        proc["window"] = {"from": proc["summary"]["months"][0], "to": proc["summary"]["months"][-1]}
        proc["_checks"] = pchecks
        dump("procurement.json", proc)
        print(f"procurement: {proc['summary']['n']} awards, {sum(proc['flag_counts'].values())} flags")
    else:
        print("procurement: no cache (run pipeline/fetch_contracts.py); keeping existing site/data/procurement.json")
        existing = json.loads((OUT / "procurement.json").read_text()) if (OUT / "procurement.json").exists() else None
        if existing:
            checks += [dict(c, source="Contracts Finder") for c in existing.get("_checks", [])]

    # ---- ONS: monthly public sector finances
    ons = O.parse_pusf(paths["ons_pusf"])
    oflags = O.ons_flags(ons)
    checks += O.ons_checks(ons, agg)
    dump("ons.json", {"release": ons["release"], "months": ons["months"], "flags": oflags,
                      "flag_types": {k: {"title": v[0], "text": v[1]} for k, v in O.ONS_FLAG_TEXT.items()},
                      "series": [{"cdid": c, **{k: v for k, v in s.items()}} for c, s in ons["series"].items()]})
    dump("hmrc.json", {"months": rec["months"], "receipts_m": rec["receipts_m"], "spend_m": rec["spend_m"],
                       "fys": rec["fys"], "receipts_a": rec["receipts_a"], "spend_a": rec["spend_a"],
                       "taxgap": gap, "revision_summary": rev_sum, "revision_bias": H.recent_bias(rev_sum),
                       "flags": hflags, "flag_types": {k: {"title": v[0], "text": v[1]} for k, v in H.MONTHLY_FLAG_TEXT.items()}})

    counts = defaultdict(int)
    for f in flags:
        counts[f["type"]] += 1
    dump("flags.json", {"params": A.PARAMS, "types": {k: {"title": v[0], "text": v[1]} for k, v in A.TYPE_INFO.items()},
                        "counts": counts, "flags": flags, "ranked": ranked[:150], "function_flags": fn_flags,
                        "benford": benford, "opacity": opacity, "revisions": rev_out, "releases": rel_keys})
    dump("aggregates.json", {"rows": agg, "real_factor": real_factor})
    dump("functions.json", functions)
    dump("regions.json", regions)
    t11y, t11l = t11
    dump("tme.json", {"years": t11y, "lines": t11l})
    dump("meta.json", {
        "generated": datetime.date.today().isoformat(), "has_procurement": (OUT / "procurement.json").exists(), "latest_release": "Public Spending Statistics, July 2026",
        "collections": src["collections"], "pending": src.get("pending", []), "release_page": src["release_page"],
        "files": [{"key": k, **m} for k, m in src["files"].items()] + [{"key": k, "api": True, **m} for k, m in src.get("apis", {}).items()],
        "db_years": years})

    print(f"segments: {len(segs)}  flags: {len(flags)}  by type: {dict(counts)}")
    print("checks:", {c['id']: c['status'] for c in checks})
    # ---- borrowing and debt: ONS annual series + DMO gilt holdings and issuance yields + Bank of England yields
    annual = B.parse_ons_annual(paths["ons_pusf"])
    holdings = B.parse_holdings(fresh(RAW / "dmo_holdings.xls", lambda: discover(DMO + "/data/gilt-market/", "gilt-holdings-data"), 24 * 7))
    issuance = B.parse_issuance(fresh(RAW / "dmo_issuance.xls", lambda: discover(DMO + "/data/gilt-market/average-gilt-issuance-yields/", "average-gilt-issuance-yields"), 24 * 7))
    yields = B.parse_yields([fresh(RAW / "boe_yields_nominal.csv", BOE.format(frm="01/Jan/1997", codes="IUDSNPY,IUDMNPY,IUDLNPY")),
                             fresh(RAW / "boe_yields_inflation.csv", BOE.format(frm="01/Jan/2010", codes="IUDSIZC"))])
    bor, bchecks = B.build(ons, annual, holdings, issuance, yields)
    checks += bchecks
    dump("borrowing.json", bor)
    # ---- local councils (England): MHCLG revenue outturn + ONS mid-year population
    lsrc = src["apis"]
    ro = L.read_outturn(fresh(RAW / "revenue_outturn.csv", lsrc["mhclg_outturn"]["url"], 24 * 30))[0]
    lpop = L.read_population(fresh(RAW / "mye_population.xlsx", lsrc["ons_population"]["url"], 24 * 30))
    lc, lyears, lpy, lmetrics, lstats, lflags = L.build(ro, lpop)
    checks += L.checks(ro, lc, lpop)
    eng = {r["year"]: L._year_vec(r["v"]) for r in ro if r["code"] == "E92000001"}
    dump("councils.json", L.export(lc, lyears, lpy, lmetrics, lstats, lflags, lpop, england=eng))
    # ---- what it buys: council spending paired with results (waste, roads), allowing for deprivation
    oc = OC.build(RAW / "revenue_outturn.csv", fresh(RAW / "capital_outturn.csv", lsrc["mhclg_capital"]["url"], 24 * 30), lpop,
                  fresh(RAW / "waste_la.ods", lsrc["defra_waste"]["url"], 24 * 30), fresh(RAW / "rdc0120.ods", lsrc["dft_road_condition"]["url"], 24 * 30),
                  fresh(RAW / "rdl0202.ods", lsrc["dft_road_length"]["url"], 24 * 30), fresh(RAW / "imd_lower.xlsx", lsrc["imd_lower"]["url"], 24 * 90),
                  fresh(RAW / "imd_upper.xlsx", lsrc["imd_upper"]["url"], 24 * 90), {k: {"name": v["name"], "group": v["group"], "cls": v["cls"]} for k, v in lc.items()})
    dump("outcomes.json", oc)
    dump("checks.json", {"checks": checks})      # written last, once every source has contributed its checks

    print("function flags:", len(fn_flags), " hmrc flags:", len(hflags), " ons flags:", len(oflags), " dwp flags:", len(dflags))


if __name__ == "__main__":
    main()
