/* UK Public Spend Explorer - application logic. No frameworks, no network calls except ./data/*.json */
(function () {
  const { html, lineChart, stackedBars, barChart, spark, SERIES, OTHER } = Charts;
  const D = {};
  const main = document.getElementById("main");
  const ROUTES = [
    ["overview", "Overview"], ["functions", "By function"], ["departments", "By department"],
    ["regions", "By region"], ["compare", "Compare years"], ["flags", "Unusual figures"],
    ["checks", "Data checks"], ["method", "Method & sources"],
  ];
  let draws = [], live = false;

  /* --------------------------------------------------------- formatting */
  const nf0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const sgn = v => (v > 0 ? "+" : v < 0 ? "−" : "");
  const bn = v => (v < 0 ? "−" : "") + "£" + nf1.format(Math.abs(v)) + "bn";          // v in £bn
  const mm = v => {                                                                      // v in £m
    const a = Math.abs(v), s = v < 0 ? "−" : "";
    return a >= 1000 ? `${s}£${nf2.format(a / 1000)}bn` : `${s}£${nf0.format(a)}m`;
  };
  const pc = v => nf1.format(v) + "%";
  const dpc = v => sgn(v) + nf1.format(Math.abs(v)) + "%";
  const yshort = y => y;
  const rf = y => D.agg.real_factor[y];

  /* ------------------------------------------------------------- helpers */
  const el = html;
  const select = (id, label, opts, value, onchange) => {
    const s = el("select", { id, onchange: e => onchange(e.target.value) },
      opts.map(([v, t]) => el("option", { value: v, ...(v === value ? { selected: "" } : {}) }, t)));
    return el("label", {}, label, s);
  };
  const card = (title, sub, ...kids) => el("section", { class: "card" }, title ? el("h3", {}, title) : null, sub ? el("p", { class: "sub" }, sub) : null, ...kids);
  const chartBox = () => el("div", { class: "chartbox" });
  const draw = fn => { draws.push(fn); if (live) fn(); };
  const num = v => (v == null ? "–" : nf0.format(v));

  function colorFor(order) {
    const map = new Map();
    order.slice(0, 7).forEach((k, i) => map.set(k, SERIES[i]));
    return k => map.get(k) || OTHER;
  }
  function topPlusOther(rows, n, years) { /* rows: [{name, values}] -> n series + Other */
    const sorted = rows.slice().sort((a, b) => Math.abs(b.values[b.values.length - 1] || 0) - Math.abs(a.values[a.values.length - 1] || 0));
    const top = sorted.slice(0, n), rest = sorted.slice(n);
    const out = top.map(r => ({ ...r }));
    if (rest.length) out.push({ name: "Other", values: years.map((_, i) => rest.reduce((a, r) => a + (r.values[i] || 0), 0)) });
    return out;
  }
  const byCode = () => (D._byCode ||= new Map(D.segments.segs.map(s => [s.c, s])));
  const flagsByCode = () => {
    if (!D._fbc) { D._fbc = new Map(); D.flags.flags.forEach(f => { (D._fbc.get(f.code) || D._fbc.set(f.code, []).get(f.code)).push(f); }); }
    return D._fbc;
  };

  /* ---------------------------------------------------------------- shell */
  function renderNav(active) {
    const nav = document.getElementById("nav");
    nav.replaceChildren(...ROUTES.map(([id, t]) => el("a", { href: `#/${id}`, ...(id === active ? { "aria-current": "page" } : {}) }, t)));
  }
  function route() {
    const id = (location.hash.replace(/^#\//, "") || "overview").split("?")[0];
    const r = ROUTES.find(r => r[0] === id) ? id : "overview";
    renderNav(r);
    draws = [];
    live = false;
    Charts.hideTip();
    main.replaceChildren(VIEWS[r]());
    draws.forEach(f => f());
    live = true;
    if (!route.first) { main.focus({ preventScroll: true }); window.scrollTo(0, 0); }
    route.first = false;
  }
  route.first = true;
  let rz;
  addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => draws.forEach(f => f()), 150); });
  addEventListener("hashchange", route);

  /* --------------------------------------------------------------- views */
  const VIEWS = {};

  /* ---------- Overview */
  VIEWS.overview = () => {
    const rows = D.agg.rows, last = rows[rows.length - 1], prev = rows[rows.length - 2];
    const y19 = rows.find(r => r.year === "2019-20");
    const realCh = (last.tme_real / prev.tme_real - 1) * 100, real19 = (last.tme_real / y19.tme_real - 1) * 100;
    const high = D.flags.flags.filter(f => f.sev === 3).length;
    const root = el("div", {},
      el("h2", {}, "Where UK public money goes"),
      el("p", { class: "lede" }, `Total Managed Expenditure (TME) is the Treasury's headline measure of all public spending. Latest outturn: ${last.year}. Figures are annual; real terms means adjusted to ${last.year} prices using the GDP deflator in Table 4.1.`),
      el("div", { class: "kpis" },
        kpi("Total public spending", bn(last.tme), `${last.year} · ${pc(last.tme_gdp)} of GDP`),
        kpi("Change in real terms", dpc(realCh), `vs ${prev.year} (price-adjusted)`),
        kpi("Since pre-pandemic", dpc(real19), `real-terms change vs 2019-20`),
        kpi("Net investment", bn(last.netinv), `of the total, ${pc(last.netinv / last.tme * 100)} of TME`),
        kpi("High-priority flags", String(high), "unusual figures to look at first"),
      ),
      el("div", { class: "notice info" }, el("b", {}, "About monthly figures: "), "the two GOV.UK collections this site is limited to publish annual outturn, not monthly spending. (Month-by-month public finance data is published by the ONS and HMRC, which are outside the permitted sources, so it is deliberately not included.)"),
    );
    const g = el("div", { class: "grid g2" });
    const c1 = chartBox(), c2 = chartBox(), c3 = chartBox(), c4 = chartBox();
    g.append(
      card("Total public spending since 1985-86", "£ billion, nominal and in real terms (today's prices)", c1),
      card("Public spending as a share of the economy", "Total Managed Expenditure, % of GDP", c2),
      card(`What it was spent on, ${D.fn.years[D.fn.years.length - 1]}`, "Ten functions, £ billion (Table 4.2, COFOG classification)", c3),
      card("How the mix has changed", "Real-terms £ billion by function", c4));
    root.append(g);
    draw(() => lineChart(c1, { x: rows.map(r => r.year), fmt: bn, axisFmt: v => "£" + nf0.format(v) + "bn", title: "Total managed expenditure",
      series: [{ name: "Real terms", values: rows.map(r => r.tme_real) }, { name: "Nominal (cash)", values: rows.map(r => r.tme), color: "var(--s2)" }] }));
    draw(() => lineChart(c2, { x: rows.map(r => r.year), fmt: pc, title: "TME as percent of GDP", series: [{ name: "% of GDP", values: rows.map(r => r.tme_gdp) }] }));
    const fns = topFunctions(D.fn.nominal);
    draw(() => barChart(c3, { items: fns.map(f => ({ label: f.label.replace(/^\d+\.\s*/, ""), value: f.values[f.values.length - 1] })).sort((a, b) => b.value - a.value), fmt: bn, valueFmt: i => bn(i.value) }));
    const real = topFunctions(D.fn.real).map(f => ({ name: f.label.replace(/^\d+\.\s*/, ""), values: f.values }));
    const sers = topPlusOther(real, 7, D.fn.years);
    draw(() => stackedBars(c4, { x: D.fn.years, series: sers, fmt: bn, axisFmt: v => "£" + nf0.format(v) + "bn", title: "Real terms spending by function" }));

    // highlights
    const hl = card("Where to look first", "The lines scoring highest on the automatic checks (see “Unusual figures” for all of them and how scoring works). Unusual is not the same as wrong: many of these are real one-off events.");
    const t = el("table", {}, el("thead", {}, el("tr", {}, ["Spending line", "Department", "Largest amount", "Why it ranks"].map((h, i) => el("th", { class: i === 2 ? "n" : "" }, h)))),
      el("tbody", {}, D.flags.ranked.slice(0, 8).map(r => el("tr", { class: "click", onclick: () => { location.hash = "#/flags"; }, title: "Open the full list" },
        el("td", {}, r.name), el("td", {}, r.dept), el("td", { class: "n" }, mm(r.max_m)), el("td", {}, r.types.map(t => D.flags.types[t].title).join(" · "))))));
    hl.append(el("div", { class: "tablewrap" }, t));
    root.append(hl);
    const bad = D.checks.checks.filter(c => c.status === "warn");
    root.append(card("Do the published tables agree with each other?", `${D.checks.checks.filter(c => c.status === "pass").length} cross-checks pass; ${bad.length} found a discrepancy.`,
      el("ul", { class: "tight" }, bad.map(c => el("li", {}, c.title, " – largest gap ", el("b", {}, num(Math.abs(c.worst_gap))), c.rows[0] && c.title.includes("£m") ? " £m" : ""))),
      el("a", { href: "#/checks" }, "See every check")));
    return root;
  };
  function kpi(label, value, sub) { return el("div", { class: "kpi" }, el("div", { class: "l" }, label), el("div", { class: "v" }, value), el("div", { class: "d" }, sub)); }
  function topFunctions(rows) { return rows.filter(r => r.level === 0 && /^\d+\./.test(r.label)); }

  /* ---------- Functions */
  const fnState = { measure: "real", sel: null };
  VIEWS.functions = () => {
    const root = el("div", {}, el("h2", {}, "Spending by function"),
      el("p", { class: "lede" }, "The Treasury groups all public spending into ten functions (health, education, defence…) using the international COFOG classification. Choose a measure, then click a row to see its history."));
    const body = el("div", {});
    const controls = el("div", { class: "controls" }, select("m", "Measure", [["real", "Real terms (today's prices, £bn)"], ["nominal", "Cash (nominal, £bn)"], ["gdp", "Share of GDP (%)"]], fnState.measure, v => { fnState.measure = v; build(); }));
    root.append(controls, body);
    build();
    return root;

    function build() {
      body.replaceChildren();
      const m = fnState.measure, rows = D.fn[m], years = D.fn.years, unit = m === "gdp" ? pc : bn;
      const tops = topFunctions(D.fn.nominal).map(f => f.label);
      const order = tops.slice().sort((a, b) => lastVal(D.fn.nominal, b) - lastVal(D.fn.nominal, a));
      const color = colorFor(order);
      const stack = topFunctions(rows).map(f => ({ name: f.label.replace(/^\d+\.\s*/, ""), values: f.values, color: color(f.label) }));
      const top7 = stack.slice().sort((a, b) => Math.abs(b.values.at(-1)) - Math.abs(a.values.at(-1)));
      const rest = top7.slice(7);
      const shown = top7.slice(0, 7);
      if (rest.length) shown.push({ name: "Other", values: years.map((_, i) => rest.reduce((a, r) => a + (r.values[i] || 0), 0)) });
      const c1 = chartBox(), c2 = chartBox();
      body.append(card(`Spending by function (${m === "real" ? "real terms" : m === "gdp" ? "% of GDP" : "cash"})`, m === "real" ? `Prices adjusted to ${years.at(-1)}.` : "", c1));
      draw(() => stackedBars(c1, { x: years, series: shown, fmt: unit, axisFmt: m === "gdp" ? v => v + "%" : v => "£" + nf0.format(v) + "bn", title: "Spending by function" }));
      // table
      const sel = fnState.sel && rows.find(r => r.label === fnState.sel) ? fnState.sel : rows.find(r => r.label.startsWith("7. Health")).label;
      fnState.sel = sel;
      const trs = rows.filter(r => !/^Total Managed|^Accounting|^Public sector expenditure/.test(r.label) || true).map(r => {
        const v = r.values, a = v[0], b = v.at(-1), n = v.length - 1;
        const ch = a ? (b / a - 1) * 100 : null;
        const last5 = v.at(-6) ? (b / v.at(-6) - 1) * 100 : null;
        return el("tr", { class: "click", onclick: () => { fnState.sel = r.label; build(); }, ...(r.label === sel ? { style: "background:var(--accent-bg)" } : {}) },
          el("td", { style: r.level ? "padding-left:24px;color:var(--ink2)" : "font-weight:" + (/^\d+\./.test(r.label) || /^Total/.test(r.label) ? 600 : 400) }, r.label),
          el("td", { class: "n" }, unit(b)), el("td", { class: "n" }, last5 == null ? "–" : dpc(last5)), el("td", { class: "n" }, ch == null ? "–" : dpc(ch)),
          el("td", {}, spark(v)));
      });
      const th = ["Function", years.at(-1), "Change over 5 yrs", `Since ${years[0]}`, "Trend"];
      body.append(card("All functions", m === "gdp" ? "Percentage changes are relative changes in the share." : "", el("div", { class: "tablewrap" },
        el("table", {}, el("thead", {}, el("tr", {}, th.map((h, i) => el("th", { class: i > 0 && i < 4 ? "n" : "" }, h)))), el("tbody", {}, trs)))));
      const sr = rows.find(r => r.label === sel);
      body.append(card(`${sel}`, "Click another row above to change.", c2));
      const fl = D.flags.function_flags.filter(f => f.label === sel);
      draw(() => lineChart(c2, { x: years, fmt: unit, axisFmt: m === "gdp" ? v => v + "%" : v => "£" + nf0.format(v) + "bn", title: sel, series: [{ name: sel, values: sr.values }], bands: m === "real" ? fl.map(f => ({ x: f.year })) : [] }));
      if (m === "real" && fl.length) body.append(el("div", { class: "notice info" }, el("b", {}, "Unusual year(s): "), fl.map(f => f.detail).join(" "), " (Shaded on the chart.) 2020-21 was the Covid-19 pandemic year, which explains many of the largest swings."));
    }
    function lastVal(rows, label) { return rows.find(r => r.label === label).values.at(-1); }
  };

  /* ---------- Departments */
  const deptState = { name: null, basis: "nominal", seg: null, q: "" };
  VIEWS.departments = () => {
    const root = el("div", {}, el("h2", {}, "Spending by department"),
      el("p", { class: "lede" }, "The Public Spending Statistics database breaks departmental budgets (DEL: day-to-day and capital limits, and departmental AME: demand-led spending such as benefits) into about 1,600 individual spending lines. It excludes the Security and Intelligence Agencies and the cost of military operations, and non-departmental AME such as debt interest. Amounts are accruals-based."));
    const body = el("div", {});
    deptState.name ||= D.dept.depts[0].name;
    const names = D.dept.depts.map(d => [d.name, d.name]);
    root.append(el("div", { class: "controls" },
      select("dsel", "Department", names, deptState.name, v => { deptState.name = v; deptState.seg = null; build(); }),
      select("dbasis", "Basis", [["nominal", "Cash (nominal)"], ["real", "Real terms (2025-26 prices)"]], deptState.basis, v => { deptState.basis = v; build(); }),
      el("label", {}, "Find any spending line", el("input", { type: "search", id: "dq", placeholder: "e.g. Energy Bills, Academies…", value: deptState.q, oninput: e => { deptState.q = e.target.value; searchBox(); } }))),
      body);
    const results = el("div", {});
    root.insertBefore(results, body);
    build();
    searchBox();
    return root;

    function adj(vals) { return deptState.basis === "real" ? vals.map((v, i) => v * rf(D.dept.years[i])) : vals; }
    function searchBox() {
      results.replaceChildren();
      const q = deptState.q.trim().toLowerCase();
      if (q.length < 2) return;
      const hits = D.segments.segs.filter(s => s.n.toLowerCase().includes(q) || s.c.toLowerCase() === q).slice(0, 12);
      results.append(card(`${hits.length ? hits.length + (hits.length === 12 ? "+" : "") : "No"} matching lines`, null,
        el("div", { class: "chips" }, hits.map(s => el("button", { class: "chip", onclick: () => { deptState.name = s.d; deptState.seg = s.c; document.getElementById("dsel").value = s.d; build(); document.getElementById("segcard")?.scrollIntoView({ behavior: "smooth" }); } }, `${s.n} · ${s.d}`)))));
    }
    function build() {
      body.replaceChildren();
      const d = D.dept.depts.find(x => x.name === deptState.name), years = D.dept.years;
      const fmt = mm;
      const c1 = chartBox(), c2 = chartBox();
      const catNames = { "DEL resource": "Day-to-day (DEL resource)", "DEL capital": "Capital investment (DEL)", "AME resource": "Demand-led (AME resource)", "AME capital": "Demand-led capital (AME)" };
      const cat = Object.keys(d.cat).sort().map(k => ({ name: catNames[k] || k, values: adj(d.cat[k]) }));
      const total = adj(d.total);
      body.append(el("div", { class: "kpis" }, kpi(d.name, mm(total.at(-1)), `${years.at(-1)} · ${deptState.basis === "real" ? "real terms" : "cash"} · ${d.nseg} spending lines`),
        kpi(`Change since ${years[0]}`, dpc((total.at(-1) / total[0] - 1) * 100), `from ${mm(total[0])}`)));
      body.append(card("Budget type", "Stacked: positive amounts above the line, negative (income, repayments) below.", c1));
      draw(() => stackedBars(c1, { x: years, series: cat, fmt, axisFmt: mm, title: d.name + " by budget type" }));
      const groups = Object.entries(d.group).map(([k, v]) => ({ name: titleCase(k), values: adj(v) }))
        .sort((a, b) => Math.max(...b.values.map(Math.abs)) - Math.max(...a.values.map(Math.abs))).slice(0, 6);
      body.append(card("What the money is spent on", "Largest economic categories (Treasury PESA economic groups). Lines can be negative where income exceeds spending.", c2));
      draw(() => lineChart(c2, { x: years, series: groups, fmt, axisFmt: mm, zero: true, title: "Economic categories" }));

      // segments table
      const segs = D.segments.segs.filter(s => s.d === d.name).slice(0, 25);
      const trs = segs.map(s => el("tr", { class: "click", onclick: () => { deptState.seg = s.c; build(); document.getElementById("segcard")?.scrollIntoView({ behavior: "smooth" }); },
        ...(deptState.seg === s.c ? { style: "background:var(--accent-bg)" } : {}) },
        el("td", {}, s.n, (flagsByCode().get(s.c) || []).some(f => f.sev >= 2) ? el("span", { class: "pill", style: "margin-left:6px" }, "flagged") : null),
        el("td", { class: "n" }, mm(adj(s.v).at(-1))), el("td", { class: "n" }, s.v[0] ? dpc((s.v.at(-1) / s.v[0] - 1) * 100) : "–"), el("td", {}, spark(s.v))));
      body.append(card("Largest spending lines", "By peak size. Click a line for its history and any automatic flags.", el("div", { class: "tablewrap" },
        el("table", {}, el("thead", {}, el("tr", {}, ["Line", years.at(-1), `Since ${years[0]}`, "Trend"].map((h, i) => el("th", { class: i === 1 || i === 2 ? "n" : "" }, h)))), el("tbody", {}, trs)))));
      if (deptState.seg) body.append(segmentCard(deptState.seg, adj));
      body.append(revisionCard(d.name));
    }
  };
  const titleCase = s => s.toLowerCase().replace(/(^|\s|\()(\w)/g, (m, a, b) => a + b.toUpperCase());

  function segmentCard(code, adjFn) {
    const s = byCode().get(code), years = D.segments.years;
    const c = chartBox();
    const real = deptState.basis === "real";
    const vals = real ? s.v.map((v, i) => v * rf(years[i])) : s.v;
    const fl = (flagsByCode().get(code) || []).slice().sort((a, b) => b.sev - a.sev);
    const out = el("section", { class: "card", id: "segcard" }, el("h3", {}, s.n), el("p", { class: "sub" }, `${s.d} · segment ${s.c} · ${titleCase(s.g)} · ${s.t}`), c);
    draw(() => lineChart(c, { x: years, series: [{ name: s.n, values: vals }], fmt: mm, axisFmt: mm, zero: true, height: 240, bands: fl.filter(f => f.type !== "revision").map(f => ({ x: f.year })) }));
    out.append(fl.length ? el("div", {}, el("h3", { style: "margin-top:10px" }, `${fl.length} automatic flag${fl.length > 1 ? "s" : ""}`),
      el("ul", { class: "tight" }, fl.map(f => el("li", {}, sevBadge(f.sev), " ", el("b", {}, D.flags.types[f.type].title), " · ", f.year, " – ", f.detail))))
      : el("p", { class: "small" }, "No automatic flags for this line."));
    return out;
  }
  function sevBadge(s) { return el("span", { class: `sev s${s}` }, el("i"), ["", "Low", "Medium", "High"][s]); }

  function revisionCard(dept) {
    const rv = D.flags.revisions[dept] || D.flags.revisions["All departments"];
    const rels = D.flags.releases;
    const rows = Object.keys(rv).sort().map(y => {
      const r = rv[y], ks = rels.filter(k => r[k] != null);
      const first = r[ks[0]], last = r[ks.at(-1)];
      return el("tr", {}, el("td", {}, y), rels.map(k => el("td", { class: "n" }, r[k] == null ? "–" : mm(r[k]))),
        el("td", { class: "n" }, mm(last - first)), el("td", { class: "n" }, first ? dpc((last / first - 1) * 100) : "–"));
    });
    return card(`How ${dept}'s published figures were revised`, "The same year's total as published in each July release, regrouped like-for-like by today's department structure so reorganisations don't show as revisions. Big changes to old years deserve an explanation.",
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Year", ...rels.map(k => "July " + k), "Revision", "Revision %"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))), el("tbody", {}, rows))));
  }

  /* ---------- Regions */
  const regState = { measure: "perhead", year: null, pick: ["London", "North East", "Scotland", "Wales", "Northern Ireland"] };
  const NATIONS = ["North East", "North West", "Yorkshire and The Humber", "East Midlands", "West Midlands", "East", "London", "South East", "South West", "Scotland", "Wales", "Northern Ireland"];
  VIEWS.regions = () => {
    const root = el("div", {}, el("h2", {}, "Spending by country and region"),
      el("p", { class: "lede" }, "Identifiable spending (the part that can be attributed to where it benefits people) across the UK's nine English regions and three other nations (Chapter 9). Per-head figures help compare places of very different size. Latest year available lags the other tables by one year."));
    const body = el("div", {});
    const years = D.reg.years; regState.year ||= years.at(-1);
    root.append(el("div", { class: "controls" },
      select("rm", "Measure", [["perhead", "Per head, cash (£)"], ["realperhead", "Per head, real terms (£)"], ["nominal", "Total, cash (£m)"], ["real", "Total, real terms (£m)"]], regState.measure, v => { regState.measure = v; build(); }),
      select("ry", "Year", years.map(y => [y, y]), regState.year, v => { regState.year = v; build(); })), body);
    build();
    return root;
    function build() {
      body.replaceChildren();
      const rows = D.reg[regState.measure], perhead = regState.measure.includes("perhead");
      const fmt = perhead ? v => "£" + nf0.format(v) : mm;
      const yi = years.indexOf(regState.year);
      const find = l => rows.find(r => r.label === l);
      const uk = rows.find(r => /^UK identifiable/.test(r.label));
      const items = NATIONS.map(l => ({ label: l, value: find(l).values[yi] })).sort((a, b) => b.value - a.value);
      if (perhead && uk) items.push({ label: "UK average", value: uk.values[yi], color: "var(--s4)" });
      items.sort((a, b) => b.value - a.value);
      const c1 = chartBox(), c2 = chartBox();
      body.append(card(`${perhead ? "Spending per head" : "Total identifiable spending"}, ${regState.year}`, perhead && uk ? `UK average ${fmt(uk.values[yi])} per head.` : "", c1));
      draw(() => barChart(c1, { items, fmt, tipFmt: it => perhead && uk ? `${fmt(it.value)} (${dpc((it.value / uk.values[yi] - 1) * 100)} vs UK average)` : fmt(it.value) }));
      const chips = el("div", { class: "chips", role: "group", "aria-label": "Regions to plot" }, NATIONS.map(l => {
        const on = regState.pick.includes(l);
        return el("button", { class: "chip", "aria-pressed": String(on), onclick: () => { regState.pick = on ? regState.pick.filter(x => x !== l) : [...regState.pick, l].slice(-6); build(); } }, l);
      }));
      body.append(card("History", "Choose up to six places to compare.", chips, c2));
      const series = regState.pick.map(l => ({ name: l, values: find(l).values }));
      if (perhead && uk) series.push({ name: "UK average", values: uk.values, dash: true });
      draw(() => lineChart(c2, { x: years, series: series.slice(0, 7), fmt, axisFmt: perhead ? fmt : mm, zero: false, title: "Regional history" }));
      if (regState.measure === "nominal" || regState.measure === "real") {
        const out = rows.find(r => r.label === "Outside UK");
        if (out) body.append(el("p", { class: "small" }, `Not shown: ${mm(out.values[yi])} of identifiable spending is outside the UK (for example overseas aid and embassies).`));
      }
    }
  };

  /* ---------- Compare */
  const cmpState = { ds: "fn", basis: "real", a: null, b: null };
  VIEWS.compare = () => {
    const root = el("div", {}, el("h2", {}, "Compare any two years"),
      el("p", { class: "lede" }, "Pick a breakdown and two years to see exactly what grew, what shrank, and by how much. Use real terms to strip out inflation."));
    const body = el("div", {});
    const yearsOf = () => cmpState.ds === "fn" ? D.fn.years : cmpState.ds === "dept" ? D.dept.years : D.reg.years;
    const ctl = el("div", { class: "controls" });
    root.append(ctl, body);
    function controls() {
      const ys = yearsOf();
      if (!ys.includes(cmpState.a)) cmpState.a = ys.at(-6) || ys[0];
      if (!ys.includes(cmpState.b)) cmpState.b = ys.at(-1);
      const bases = cmpState.ds === "fn" ? [["real", "Real terms (£bn)"], ["nominal", "Cash (£bn)"], ["gdp", "Share of GDP (pp)"]] : [["real", "Real terms (£m)"], ["nominal", "Cash (£m)"]];
      if (!bases.some(b => b[0] === cmpState.basis)) cmpState.basis = "real";
      ctl.replaceChildren(
        select("cds", "Breakdown", [["fn", "Functions (health, defence…)"], ["dept", "Departments"], ["reg", "Regions & nations"]], cmpState.ds, v => { cmpState.ds = v; controls(); build(); }),
        select("cb", "Measure", bases, cmpState.basis, v => { cmpState.basis = v; build(); }),
        select("ca", "From", ys.map(y => [y, y]), cmpState.a, v => { cmpState.a = v; build(); }),
        select("cc", "To", ys.map(y => [y, y]), cmpState.b, v => { cmpState.b = v; build(); }));
    }
    function items() {
      const ys = yearsOf(), ia = ys.indexOf(cmpState.a), ib = ys.indexOf(cmpState.b), real = cmpState.basis === "real";
      if (cmpState.ds === "fn") {
        return topFunctions(D.fn[cmpState.basis]).map(f => ({ label: f.label.replace(/^\d+\.\s*/, ""), a: f.values[ia], b: f.values[ib] }));
      }
      if (cmpState.ds === "dept") {
        return D.dept.depts.map(d => ({ label: d.name, a: d.total[ia] * (real ? rf(ys[ia]) : 1), b: d.total[ib] * (real ? rf(ys[ib]) : 1) }));
      }
      const rows = D.reg[real ? "real" : "nominal"];
      return NATIONS.map(l => { const r = rows.find(x => x.label === l); return { label: l, a: r.values[ia], b: r.values[ib] }; });
    }
    function build() {
      body.replaceChildren();
      const its = items().map(i => ({ ...i, value: i.b - i.a, pct: i.a ? (i.b / i.a - 1) * 100 : null })).sort((x, y) => y.value - x.value);
      const gdp = cmpState.basis === "gdp";
      const unit = cmpState.ds === "fn" ? (gdp ? v => nf2.format(v) + "pp" : bn) : mm;
      const sunit = v => sgn(v) + unit(Math.abs(v)).replace(/^−/, "");
      const c = chartBox();
      const totA = its.reduce((a, i) => a + i.a, 0), totB = its.reduce((a, i) => a + i.b, 0);
      body.append(card(`Change from ${cmpState.a} to ${cmpState.b}`, `Sum of the items shown: ${unit(totA)} → ${unit(totB)} (${dpc((totB / totA - 1) * 100)}).`, c));
      draw(() => barChart(c, { items: its, diverging: true, fmt: sunit, valueFmt: i => sunit(i.value), axisFmt: v => unit(v),
        tipFmt: i => `${unit(i.a)} → ${unit(i.b)} (${sunit(i.value)}${i.pct == null ? "" : ", " + dpc(i.pct)})` }));
      body.append(card("In detail", null, el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["", cmpState.a, cmpState.b, "Change", "Change %"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))),
        el("tbody", {}, its.map(i => el("tr", {}, el("td", {}, i.label), el("td", { class: "n" }, unit(i.a)), el("td", { class: "n" }, unit(i.b)), el("td", { class: "n" }, sunit(i.value)), el("td", { class: "n" }, i.pct == null ? "–" : dpc(i.pct)))))))));
      if (cmpState.ds === "dept") body.append(el("p", { class: "small" }, "Department totals cover budgeted spending only (DEL and departmental AME). Departments created or reorganised between the two years will show large changes that are structural, not real growth."));
    }
    controls(); build();
    return root;
  };

  /* ---------- Flags */
  const fState = { type: "", sev: 2, dept: "", q: "", limit: 40, bdept: "All departments", open: null };
  VIEWS.flags = () => {
    const F = D.flags;
    const root = el("div", {}, el("h2", {}, "Unusual figures"),
      el("p", { class: "lede" }, "A set of automatic screening tests looks for patterns that auditors and investigative journalists commonly treat as red flags: very large jumps, figures later restated, lines appearing or vanishing, repeated or suspiciously round amounts, and opaque catch-all spending."),
      el("div", { class: "notice" }, el("b", {}, "Read this first. "), "These tests find numbers that are unusual, not wrongdoing. Almost every flag has an innocent explanation: a new scheme (the Energy Bills Support Scheme), a one-off settlement (Infected Blood Compensation), accounting valuation changes (student loans), or a reorganisation of departments. The data here are annual departmental totals, so they cannot show individual fraudulent payments or error rates. Their value is in telling you where to ask questions. Each test is explained on the “Method” page and all thresholds are published."));
    // type tiles
    const tiles = el("div", { class: "kpis" }, Object.entries(F.types).map(([k, t]) => {
      const n = F.counts[k] || 0;
      return el("button", { class: "kpi", style: "text-align:left;cursor:pointer", "aria-pressed": String(fState.type === k), onclick: () => { fState.type = fState.type === k ? "" : k; fState.limit = 40; rebuild(); } },
        el("div", { class: "l" }, t.title), el("div", { class: "v" }, k === "function_jump" ? String(F.function_flags.length) : String(n)), el("div", { class: "d" }, k === "function_jump" ? "in the function tables" : "in departmental lines"));
    }));
    root.append(tiles);
    const listWrap = el("div", {});
    root.append(listWrap);
    rebuild();
    // priority list
    const pr = card("Priority review list", "Lines with several kinds of flag at once, weighted by severity. This is where a reader with limited time should start.",
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["#", "Line", "Department", "Largest amount", "Score", "Flags"].map((h, i) => el("th", { class: i === 3 || i === 4 ? "n" : "" }, h)))),
        el("tbody", {}, F.ranked.slice(0, 25).map((r, i) => el("tr", { class: "click", onclick: () => { fState.q = r.name; fState.type = ""; fState.sev = 1; fState.dept = ""; rebuild(); listWrap.scrollIntoView({ behavior: "smooth" }); } },
          el("td", {}, i + 1), el("td", {}, r.name), el("td", {}, r.dept), el("td", { class: "n" }, mm(r.max_m)), el("td", { class: "n" }, r.score), el("td", {}, r.types.map(t => F.types[t].title).join(", "))))))));
    root.append(pr);
    // function-level
    const fl = card("Unusual moves in whole functions", "Real-terms year-on-year changes that are extreme against that function's own history (Table 4.3). Many cluster in 2020-21 (Covid-19 response) and 2021-23 (debt interest on inflation-linked gilts).",
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Year", "What happened"].map(h => el("th", {}, h)))),
        el("tbody", {}, F.function_flags.slice(0, 15).map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, f.year), el("td", {}, f.detail)))))));
    root.append(fl);
    root.append(benfordCard(), opacityCard());
    return root;

    function rebuild() {
      listWrap.replaceChildren();
      const depts = [...new Set(F.flags.map(f => f.dept))].sort();
      const filtered = F.flags.filter(f => (!fState.type || f.type === fState.type) && f.sev >= fState.sev && (!fState.dept || f.dept === fState.dept) &&
        (!fState.q || (f.name + " " + f.dept + " " + f.code).toLowerCase().includes(fState.q.toLowerCase())));
      if (fState.type === "function_jump") { filtered.length = 0; }
      const ctl = el("div", { class: "controls" },
        select("fs", "Minimum severity", [["3", "High only"], ["2", "Medium and above"], ["1", "Everything"]], String(fState.sev), v => { fState.sev = +v; fState.limit = 40; rebuild(); }),
        select("fd", "Department", [["", "All departments"], ...depts.map(d => [d, d])], fState.dept, v => { fState.dept = v; fState.limit = 40; rebuild(); }),
        select("ft", "Type", [["", "All types"], ...Object.entries(F.types).filter(([k]) => k !== "function_jump").map(([k, t]) => [k, t.title])], fState.type === "function_jump" ? "" : fState.type, v => { fState.type = v; fState.limit = 40; rebuild(); }),
        el("label", {}, "Search", el("input", { type: "search", value: fState.q, placeholder: "line, department, code", oninput: e => { fState.q = e.target.value; fState.limit = 40; clearTimeout(rebuild.t); rebuild.t = setTimeout(rebuild, 250); } })));
      const info = fState.type && F.types[fState.type] ? el("p", { class: "small" }, el("b", {}, F.types[fState.type].title + ": "), F.types[fState.type].text) : null;
      const rows = filtered.slice(0, fState.limit).flatMap((f, i) => {
        const id = f.code + f.type + f.year + (f.to_release || "");
        const open = fState.open === id;
        const tr = el("tr", { class: "click", onclick: () => { fState.open = open ? null : id; rebuild(); } },
          el("td", {}, sevBadge(f.sev)), el("td", {}, D.flags.types[f.type].title), el("td", {}, f.dept), el("td", {}, f.name), el("td", {}, f.year), el("td", { class: "n" }, mm(f.value)));
        const out = [tr];
        if (open) {
          const c = chartBox();
          out.push(el("tr", { class: "detail" }, el("td", { colspan: 6 }, el("p", {}, f.detail), el("p", { class: "small" }, D.flags.types[f.type].text), c)));
          const s = byCode().get(f.code);
          if (s) draw(() => lineChart(c, { x: D.segments.years, series: [{ name: f.name, values: s.v }], fmt: mm, axisFmt: mm, zero: true, height: 200, bands: [{ x: f.year }] }));
        }
        return out;
      });
      listWrap.append(card(`${filtered.length.toLocaleString("en-GB")} flagged items`, "Click a row for the explanation and the line's history.", ctl, info,
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Test", "Department", "Spending line", "Year", "Amount"].map((h, i) => el("th", { class: i === 5 ? "n" : "" }, h)))), el("tbody", {}, rows))),
        filtered.length > fState.limit ? el("p", {}, el("button", { onclick: () => { fState.limit += 60; rebuild(); } }, `Show more (${filtered.length - fState.limit} left)`)) : null));
    }
  };

  function benfordCard() {
    const B = D.flags.benford;
    const sel = el("select", { id: "bsel", onchange: e => paint(e.target.value) }, B.depts.map(d => el("option", { value: d.dept }, d.dept)));
    const c = chartBox(), note = el("p", { class: "small" });
    const out = card("First-digit pattern (Benford's law)", "In many naturally occurring sets of financial figures, about 30% start with the digit 1 and under 5% with 9. Manipulated or invented numbers often miss that pattern. It is a weak, indirect test: budget lines set by policy are not naturally Benford-like, so treat results as a prompt to look, not a verdict.",
      el("div", { class: "controls" }, el("label", {}, "Department", sel)), c, note,
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Department", "Amounts tested", "Deviation (MAD)", "Conformity", "Reliability"].map((h, i) => el("th", { class: i === 1 || i === 2 ? "n" : "" }, h)))),
        el("tbody", {}, B.depts.map(d => el("tr", {}, el("td", {}, d.dept), el("td", { class: "n" }, num(d.n)), el("td", { class: "n" }, nf2.format(d.mad * 100) + "pp"), el("td", {}, d.label), el("td", {}, d.reliable ? "Adequate sample" : "Small sample: indicative only")))))));
    function paint(name) {
      const d = B.depts.find(x => x.dept === name);
      note.textContent = `${d.n.toLocaleString("en-GB")} amounts. Mean absolute deviation ${nf2.format(d.mad * 100)} percentage points: “${d.label}” on Nigrini's scale (close ≤0.6, acceptable ≤1.2, marginal ≤1.5, non-conforming above).${d.reliable ? "" : " Fewer than 1,000 amounts, so random variation alone can look non-conforming."}`;
      lineChart(c, { x: [1, 2, 3, 4, 5, 6, 7, 8, 9].map(String), xlabel: "First digit", fmt: v => nf1.format(v * 100) + "%", axisFmt: v => Math.round(v * 100) + "%", height: 220, title: "Benford comparison",
        series: [{ name: "Expected", values: B.expected, dash: true, color: "var(--other)" }, { name: "Observed", values: d.freq, color: "var(--s1)" }] });
    }
    draw(() => paint(sel.value));
    return out;
  }
  function opacityCard() {
    const O = D.flags.opacity, years = D.dept.years;
    const rows = O.map(o => el("tr", {}, el("td", {}, o.dept, o.flag ? el("span", { class: "pill", style: "margin-left:6px" }, "rising") : null),
      el("td", { class: "n" }, o.share.at(-1) == null ? "–" : pc(o.share.at(-1) * 100)),
      el("td", { class: "n" }, (o.rise_pp >= 0 ? "+" : "−") + nf1.format(Math.abs(o.rise_pp)) + "pp"), el("td", {}, spark(o.share.map(s => s == null ? null : s * 100))), el("td", { class: "n" }, mm(o.gross_m.at(-1)))));
    return card("Share of spending in catch-all categories", `How much of each department's gross spending sits in categories that say little about what was bought: “other” resource/capital, unallocated funds, and provisions. A high or rising share makes scrutiny harder. Change is ${years[0]} → ${years.at(-1)}.`,
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Department", `Share ${years.at(-1)}`, "Change", "Trend", "Gross spend"].map((h, i) => el("th", { class: i === 1 || i === 2 || i === 4 ? "n" : "" }, h)))), el("tbody", {}, rows))));
  }

  /* ---------- Checks */
  VIEWS.checks = () => {
    const C = D.checks.checks;
    const root = el("div", {}, el("h2", {}, "Do the official tables add up?"),
      el("p", { class: "lede" }, "The Treasury publishes the same totals in several tables. These checks recompute sums and compare tables against each other. A gap is not proof of error (rounding, timing and revisions all matter) but it is exactly what a careful reader would want pointed out."));
    root.append(el("div", { class: "kpis" }, kpi("Pass", String(C.filter(c => c.status === "pass").length), "agree within rounding"), kpi("Discrepancy", String(C.filter(c => c.status === "warn").length), "outside rounding tolerance"), kpi("Documented gap", String(C.filter(c => c.status === "info").length), "explained in the source notes")));
    C.forEach(c => {
      const unit = /£bn/.test(c.title) ? "£bn" : /£m/.test(c.title) ? "£m" : "";
      const tol = c.tolerance > 1e9 ? 0 : c.tolerance;
      const head = el("tr", {}, ["Year", "Expected", "Table shows", "Gap"].map((h, i) => el("th", { class: i ? "n" : "" }, h)));
      const body = c.rows.map(r => el("tr", {},
        el("td", {}, r.year), el("td", { class: "n" }, nf2.format(r.expected)), el("td", { class: "n" }, nf2.format(r.actual)),
        el("td", { class: "n", style: Math.abs(r.gap) > tol ? "font-weight:700" : "" }, sgn(r.gap) + nf2.format(Math.abs(r.gap)))));
      const working = el("details", { class: "tbl", ...(c.status !== "pass" ? { open: "" } : {}) },
        el("summary", {}, `Show working (tolerance ±${nf2.format(tol)} ${unit})`),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, head), el("tbody", {}, body))));
      const label = { pass: "✓ Agrees", warn: "⚠ Discrepancy", info: "ℹ Known gap" }[c.status];
      root.append(el("section", { class: "card" },
        el("h3", {}, el("span", { class: `status ${c.status}` }, label), " ", c.title),
        c.note ? el("p", { class: "sub" }, c.note) : null, working));
    });
    return root;
  };

  /* ---------- Method */
  VIEWS.method = () => {
    const P = D.flags.params, T = D.flags.types;
    const root = el("div", {}, el("h2", {}, "Method & sources"));
    root.append(card("Sources (and only these)", "Every number comes from a file published by HM Treasury on GOV.UK in one of two collections.",
      el("ul", { class: "tight" }, D.meta.collections.map(u => el("li", {}, el("a", { href: u, rel: "noopener" }, u)))),
      el("p", { class: "small" }, "Files used (all downloaded and processed by pipeline/build.py in the project, so anyone can reproduce the data):"),
      el("div", { class: "tablewrap" }, el("table", {}, el("tbody", {}, D.meta.files.map(f => el("tr", {}, el("td", {}, f.release), el("td", {}, f.title), el("td", {}, el("a", { href: f.url, rel: "noopener" }, "download .xlsx")))))))));
    root.append(card("What the site can and cannot tell you", null, el("ul", { class: "tight" },
      el("li", {}, el("b", {}, "Annual only. "), "These collections publish financial-year outturn. There is no monthly spending series in them."),
      el("li", {}, el("b", {}, "Aggregate, not transactions. "), "The most detailed level is about 1,600 departmental spending lines per year. Individual payments, contracts and benefit claims are not in these sources, so the site cannot detect an individual fraud, nor measure fraud and error rates (those are published elsewhere)."),
      el("li", {}, el("b", {}, "Coverage. "), "The line-by-line database covers departmental budgets only (DEL and departmental AME) and, by the Treasury's own note, excludes the Security and Intelligence Agencies and military operations costs. Long-run totals and function splits (Chapter 4) cover everything."),
      el("li", {}, el("b", {}, "Latest numbers can change. "), "Recent years are provisional and get restated; the revision tests show how much they have moved in the past."),
      el("li", {}, el("b", {}, "Real terms "), "uses the ratio of real to nominal Total Managed Expenditure in Table 4.1, i.e. the Treasury's own GDP-deflator adjustment."))));
    root.append(card("The screening tests", "Each test produces a flag with a severity (Low, Medium, High) so you can sort by importance. None implies wrongdoing.",
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Test", "How it works", "Key thresholds"].map(h => el("th", {}, h)))), el("tbody", {},
        trow(T.jump.title, `For every line and year-pair, relative change = (this year − last year) ÷ max(last year, £${P.materiality_floor_m}m). It is compared with every comparable line (same budget type and economic category) using a robust z-score based on the median and MAD, which is not distorted by the outliers themselves.`, `score ≥ ${P.jump_z}; change ≥ £${P.jump_min_change_m}m`),
        trow(T.revision.title, "Each July release restates earlier years. The same line and year is compared across the July 2024, 2025 and 2026 databases. Revisions that are exactly cancelled by an opposite revision elsewhere in the same department are re-allocations and are marked Low; line codes that appear or vanish are probably re-codings and also Low.", `≥ £${P.revision_min_change_m}m and ≥ ${P.revision_min_rel * 100}%`),
        trow(T.new_line.title + " / " + T.closed_line.title, "A line with no spend in one year and a large amount in the next (or the reverse).", `≥ £${P.newline_min_m}m`),
        trow(T.sign_flip.title, "A net figure that flips between expenditure and income.", `both ≥ £${P.signflip_min_m}m`),
        trow(T.identical.title, "Outturn that is identical to the £thousand in consecutive years. Genuine accounts almost never repeat exactly; a repeated figure may be a budget carried forward.", `≥ £${P.identical_min_m}m`),
        trow(T.round.title, "An outturn that is an exact whole number of £ millions (e.g. 250,000 in £ thousand).", `≥ £${P.round_min_m}m`),
        trow(T.trend.title, "A line that rose in every one of the five years at a high compound rate.", `≥ ${P.trend_min_cagr * 100}% a year; latest ≥ £${P.trend_min_latest_m}m`),
        trow(T.function_jump.title, "Same robust method applied to year-on-year real-terms change in each function and sub-function, relative to its own history 2003-04 → 2025-26.", `score ≥ ${P.function_z}; change ≥ £${P.function_min_change_bn}bn`),
        trow("Benford first-digit test", "Compares the distribution of leading digits of all amounts in a department with Benford's law, using Nigrini's mean absolute deviation scale.", `needs ≥ ${P.benford_min_n} amounts; ≥ 1,000 for reliable`),
        trow("Catch-all spending share", "Share of positive spending in “other”, “unallocated” and “provision” categories, which carry little information about what was bought.", `flag if ≥ ${P.opaque_share_flag * 100}% and rising ≥ ${P.opaque_rise_pp}pp`),
        trow("Table cross-checks", "Recomputes totals (functions → services → TME, regions → nations → UK) and compares the same total across tables and real-vs-cash deflators.", "1-decimal rounding tolerance"),
      )))));
    root.append(card("Priority score", null, el("p", { class: "small" }, "Per spending line: Low = 1 point, Medium = 3, High = 6, summed over all its flags, plus 2 for each additional kind of flag. Lines are ranked by score, then size. It is deliberately simple so anyone can reproduce it.")));
    root.append(card("Reproduce it", null, el("p", { class: "small" }, "Run "), el("pre", { style: "overflow:auto" }, "python3 pipeline/build.py\npython3 -m unittest discover -s pipeline/tests")));
    return root;
    function trow(a, b, c) { return el("tr", {}, el("td", { style: "min-width:150px;font-weight:600" }, a), el("td", {}, b), el("td", { style: "min-width:150px" }, c)); }
  };

  /* --------------------------------------------------------------- boot */
  async function boot() {
    const names = ["meta", "aggregates", "functions", "regions", "departments", "segments", "flags", "checks"];
    try {
      const res = await Promise.all(names.map(n => fetch(`data/${n}.json`).then(r => { if (!r.ok) throw new Error(n); return r.json(); })));
      [D.meta, D.agg, D.fn, D.reg, D.dept, D.segments, D.flags, D.checks] = res;
    } catch (e) {
      main.replaceChildren(el("div", { class: "notice" }, "Could not load the data files. If you opened index.html directly from disk, serve the folder instead (for example: python3 -m http.server -d site)."));
      return;
    }
    document.getElementById("foot-meta").textContent = `Data: ${D.meta.latest_release}, plus earlier PESA/PSS releases back to July 2024. Processed ${D.meta.generated}.`;
    route();
  }
  boot();
})();
