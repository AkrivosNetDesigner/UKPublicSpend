/* UK Public Spend Explorer - application logic. No frameworks, no network calls except ./data/*.json */
(function () {
  const { html, lineChart, stackedBars, barChart, spark, SERIES, OTHER } = Charts;
  const D = {};
  const main = document.getElementById("main");
  const ROUTES = [
    ["overview", "Overview"], ["functions", "By function"], ["departments", "By department"],
    ["regions", "By region"], ["tax", "Tax & tax gap"], ["monthly", "Monthly finances"], ["borrowing", "Borrowing & debt"], ["councils", "Local councils"], ["buys", "What it buys"], ["benefits", "Benefit fraud & error"], ["procurement", "Contract awards"], ["compare", "Compare years"], ["flags", "Unusual figures"],
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
  const NAV_GROUPS = [["", ["overview"]], ["Where money goes", ["functions", "departments", "regions", "councils", "buys", "compare"]],
    ["Money in and debt", ["tax", "monthly", "borrowing"]], ["Integrity and scrutiny", ["benefits", "procurement", "flags", "checks"]], ["About", ["method"]]];
  function renderNav(active) {
    const nav = document.getElementById("nav"), label = Object.fromEntries(ROUTES);
    nav.replaceChildren(...NAV_GROUPS.map(([title, ids]) => {
      const links = ids.filter(id => label[id]).map(id => el("a", { href: `#/${id}`, ...(id === active ? { "aria-current": "page" } : {}) }, label[id]));
      return links.length ? el("div", { class: "navgroup" }, title ? el("span", { class: "navlabel" }, title) : null, ...links) : null;
    }).filter(Boolean));
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

  /* Keep the page where it is while a control rebuilds part of the view.
   * Views rebuild by emptying a container and refilling it; charts measure the page as they draw, so the page is
   * briefly short and the browser clamps the scroll position back to the top. Holding the height of <main> for
   * the duration prevents that. The control you used is also recreated, so focus (and caret) is put back. */
  function holdView() {
    const a = document.activeElement;
    const st = { id: a && a.id, s: a && a.selectionStart, e: a && a.selectionEnd };
    main.style.minHeight = main.offsetHeight + "px";
    return function release() {
      const el = st.id && document.getElementById(st.id);
      if (el && el !== document.activeElement) {
        el.focus({ preventScroll: true });
        if (st.s != null && typeof el.setSelectionRange === "function") { try { el.setSelectionRange(st.s, st.e); } catch (_) { /* not a text input */ } }
      }
      main.style.minHeight = "";
    };
  }
  ["change", "click"].forEach(type => main.addEventListener(type, ev => {
    if (ev.target.closest && ev.target.closest("a")) return;   // real navigation: route() resets the scroll itself
    setTimeout(holdView(), 0);                                   // release once the handlers (and chart drawing) are done
  }, true));
  addEventListener("hashchange", () => { main.style.minHeight = ""; });

  /* --------------------------------------------------------------- views */
  const VIEWS = {};

  /* ---------- Overview */
  VIEWS.overview = () => {
    const rows = D.agg.rows, last = rows[rows.length - 1], prev = rows[rows.length - 2];
    const y19 = rows.find(r => r.year === "2019-20");
    const realCh = (last.tme_real / prev.tme_real - 1) * 100, real19 = (last.tme_real / y19.tme_real - 1) * 100;
    const high = D.flags.flags.filter(f => f.sev === 3).length;
    const hm = hmrcHeadline();
    const root = el("div", {},
      el("h2", {}, "Where UK public money goes"),
      el("p", { class: "lede" }, `Total Managed Expenditure (TME) is the Treasury's headline measure of all public spending. Latest outturn: ${last.year}. Figures are annual; real terms means adjusted to ${last.year} prices using the GDP deflator in Table 4.1.`),
      el("div", { class: "kpis" },
        kpi("Total public spending", bn(last.tme), `${last.year} · ${pc(last.tme_gdp)} of GDP`),
        kpi("Change in real terms", dpc(realCh), `vs ${prev.year} (price-adjusted)`),
        kpi("Benefits overpaid (DWP)", mm(D.dwp.all.total.at(-1).est), `${D.dwp.all.total.at(-1).year} · ${pc(D.dwp.all.pct.total.at(-1).est)} of benefit spending`),
        kpi("Tax received (HMRC)", mm(hm.recLast), `${hm.fy} · ${dpc(hm.recYoy)} on the year before`),
        kpi("Tax not collected", bn(hm.gap), `${hm.gapYear} estimate · ${pc(hm.gapPct)} of tax due`),
        kpi("High-priority flags", String(high + hm.high + D.ons.flags.filter(f => f.sev === 3).length + D.dwp.flags.filter(f => f.sev === 3).length), "unusual figures to look at first"),
      ),
      el("div", { class: "notice info" }, el("b", {}, "Month by month: "), "the Treasury's spending tables are annual. For monthly figures see ", el("a", { href: "#/monthly" }, "Monthly finances"), " (ONS: spending, receipts, borrowing and debt interest) and ", el("a", { href: "#/tax" }, "Tax & tax gap"), " (HMRC receipts). For how borrowing builds into debt, who lends and at what price, see ", el("a", { href: "#/borrowing" }, "Borrowing & debt"), "; for benefit fraud and error, ", el("a", { href: "#/benefits" }, "Benefit fraud & error"), "."),
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
        el("div", { class: "chips" }, hits.map(s => el("button", { class: "chip", onclick: () => { deptState.name = s.d; deptState.seg = s.c; document.getElementById("dsel").value = s.d; build(); jumpTo("segcard"); } }, `${s.n} · ${s.d}`)))));
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
      const trs = segs.map(s => el("tr", { class: "click", onclick: () => { deptState.seg = s.c; build(); jumpTo("segcard"); },
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
  /* Scroll to a section and flash it so the jump is visible (the sticky header is allowed for in CSS). */
  function jumpTo(target) {
    const e = typeof target === "string" ? document.getElementById(target) : target;
    if (!e) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    e.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    e.classList.remove("flash"); void e.offsetWidth; e.classList.add("flash");
    e.addEventListener("animationend", () => e.classList.remove("flash"), { once: true });
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

  /* ---------- Tax & tax gap (HMRC) */
  function hmrcHeadline() {
    const H = D.hmrc, i = H.fys.length - 1, tot = H.receipts_a["Total HMRC Receipts"];
    const gap = H.taxgap.gap_bn.find(r => r.labels[0] === "Total tax gap"), pct = H.taxgap.gap_pct.find(r => r.labels[0] === "Total tax gap");
    return { fy: H.fys[i], recLast: tot[i], recYoy: (tot[i] / tot[i - 1] - 1) * 100, gap: gap.values.at(-1), gapPct: pct.values.at(-1),
      gapYear: H.taxgap.years.at(-1), high: H.flags.filter(f => f.sev === 3).length };
  }
  const niceDate = iso => { const d = new Date(iso + "T00:00:00Z"); return `${d.getUTCDate()} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monLabel = k => `${MON[+k.slice(5) - 1]} ${k.slice(0, 4)}`;
  const cleanTax = n => n.replace(/\s*\(included within[^)]*\)/, " (part of a larger tax)").replace("Total HMRC Receipts", "All taxes (total HMRC receipts)");
  const BEHAVIOUR_HELP = {
    "Avoidance": "Using the tax rules in ways Parliament did not intend.",
    "Criminal attacks": "Organised crime attacking the tax system, such as VAT fraud and smuggling.",
    "Error": "Honest mistakes by taxpayers.",
    "Evasion": "Deliberately hiding income or falsifying records.",
    "Failure to take reasonable care": "Careless mistakes where reasonable steps were not taken.",
    "Hidden economy": "Activity that is entirely outside the tax system.",
    "Legal interpretation": "Disagreements over what the law means, which courts may decide.",
    "Non-payment": "Tax that is owed but not paid, for example because of insolvency.",
  };
  const taxState = { tax: "Total HMRC Receipts", basis: "nominal", gapBy: "tax" };
  VIEWS.tax = () => {
    const H = D.hmrc, hm = hmrcHeadline(), bias = H.revision_bias;
    const months = H.months, tot = H.receipts_m["Total HMRC Receipts"], li = months.length - 1;
    const yoy = (tot[li] / tot[li - 12] - 1) * 100;
    // year-to-date: April of the latest financial year to the latest month
    const fyStart = months.findLastIndex(m => m.endsWith("-04") && li - months.indexOf(m) < 12);
    const n = li - fyStart + 1, ytd = tot.slice(fyStart, li + 1).reduce((a, v) => a + (v || 0), 0), ytdPrev = tot.slice(fyStart - 12, li + 1 - 12).reduce((a, v) => a + (v || 0), 0);
    const root = el("div", {}, el("h2", {}, "Tax received, and tax not collected"),
      el("p", { class: "lede" }, "HMRC collects almost all the money government spends. Its statistics show monthly receipts, and its estimate of the “tax gap”: the tax that should have been paid but was not, through evasion, criminal attacks, error, avoidance and non-payment. Cash receipts here are not the same measure as the Treasury's spending tables, so compare trends, not pennies."),
      el("div", { class: "kpis" },
        kpi(`Tax received, ${monLabel(months[li])}`, mm(tot[li]), `${dpc(yoy)} on ${monLabel(months[li - 12])}`),
        kpi(`Since April ${months[fyStart].slice(0, 4)}`, mm(ytd), `${n} months · ${dpc((ytd / ytdPrev - 1) * 100)} on the same months last year`),
        kpi(`Tax received, ${hm.fy}`, mm(hm.recLast), `${dpc(hm.recYoy)} on ${H.fys.at(-2)}`),
        kpi(`Tax gap, ${hm.gapYear}`, bn(hm.gap), `${pc(hm.gapPct)} of tax due`),
        kpi("Revisions to first estimates", `${bias.n_up} of ${bias.n} up`, `latest ${bias.n} editions, average ${dpc(bias.mean_pp).replace("%", "pp")}`)));
    const body = el("div", {});
    root.append(body);
    build();
    return root;

    function build() {
      body.replaceChildren();
      // A. where tax comes from
      const fys = H.fys, A_ = H.receipts_a, real = taxState.basis === "real";
      const adj = (v, i) => v == null ? 0 : v * (real ? rf(fys[i]) : 1);
      const parts = [["Income Tax", "Income Tax"], ["National Insurance", "National Insurance Contributions"], ["VAT", "Value Added Tax"], ["Corporation Tax", "Corporation Tax"], ["Fuel duties", "Hydrocarbon Oil (Fuel duties)"]];
      const stack = parts.map(([nm, col]) => ({ name: nm, values: A_[col].map(adj) }));
      stack.push({ name: "Other", values: fys.map((_, i) => adj(A_["Total HMRC Receipts"][i], i) - stack.reduce((a, s) => a + s.values[i], 0)) });
      const c1 = chartBox();
      body.append(card("Where the money comes from", "Tax receipts by financial year, £ million. “Other” includes Capital Gains Tax, stamp duties, alcohol and tobacco duties, and every other HMRC tax.",
        el("div", { class: "controls" }, select("tb", "Basis", [["nominal", "Cash (nominal)"], ["real", "Real terms (2025-26 prices)"]], taxState.basis, v => { taxState.basis = v; build(); })), c1));
      draw(() => stackedBars(c1, { x: fys, series: stack, fmt: mm, axisFmt: mm, title: "Tax receipts by type" }));

      // B. month by month
      const taxes = Object.keys(H.receipts_m).filter(k => H.receipts_m[k].some(v => v != null && v !== 0));
      const col = H.receipts_m[taxState.tax] || tot;
      const c2 = chartBox(), c3 = chartBox();
      const taxFlags = H.flags.filter(f => f.type === "monthly_jump" && f.tax === taxState.tax);
      body.append(card("Month by month", `Cash received by HMRC each month since April 2017. Taxes arrive in lumps (Self Assessment in January and July, Corporation Tax quarterly), so compare each month with the same month in other years.`,
        el("div", { class: "controls" }, select("tx", "Tax", taxes.map(k => [k, cleanTax(k)]), taxState.tax, v => { taxState.tax = v; build(); })), c2));
      draw(() => lineChart(c2, { x: months.map(monLabel), fmt: mm, axisFmt: mm, zero: true, title: cleanTax(taxState.tax), series: [{ name: cleanTax(taxState.tax), values: col }],
        bands: taxFlags.map(f => ({ x: monLabel(f.month) })) }));
      if (taxFlags.length) body.append(el("div", { class: "notice info" }, el("b", {}, `${taxFlags.length} unusual month${taxFlags.length > 1 ? "s" : ""} (shaded): `), taxFlags.slice(0, 3).map(f => f.detail).join(" "), taxFlags.length > 3 ? ` (+${taxFlags.length - 3} more on the Unusual figures page.)` : ""));
      // seasonality
      const fyList = [...new Set(months.map(m => { const y = +m.slice(0, 4), mo = +m.slice(5); return mo >= 4 ? y : y - 1; }))].slice(-5).reverse();
      const order = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3];
      const ser = fyList.map(fy => ({ name: `${fy}-${String(fy + 1).slice(2)}`, values: order.map(mo => { const y = mo >= 4 ? fy : fy + 1, i = months.indexOf(`${y}-${String(mo).padStart(2, "0")}`); return i < 0 ? null : col[i]; }) }));
      body.append(card("The same months across years", "Each line is one financial year, April to March. A line that departs from the others shows where timing or policy changed receipts.", c3));
      draw(() => lineChart(c3, { x: order.map(m => MON[m - 1]), fmt: mm, axisFmt: mm, zero: true, title: "Seasonal comparison", series: ser, height: 260 }));
      // table: latest month vs year ago
      const rows = ["Total HMRC Receipts", "Income Tax", "National Insurance Contributions", "Value Added Tax", "Corporation Tax", "Hydrocarbon Oil (Fuel duties)", "Capital Gains Tax", "Stamp Duty Land Tax", "Inheritance Tax", "Tobacco Duties", "Betting & Gaming", "Penalties"].filter(k => H.receipts_m[k]).map(k => {
        const v = H.receipts_m[k], a = v[li], b = v[li - 12], ytdA = v.slice(fyStart, li + 1).reduce((x, y) => x + (y || 0), 0), ytdB = v.slice(fyStart - 12, li + 1 - 12).reduce((x, y) => x + (y || 0), 0);
        return el("tr", { class: "click", onclick: () => { taxState.tax = k; build(); }, title: "Show this tax above" }, el("td", {}, cleanTax(k)), el("td", { class: "n" }, mm(a)), el("td", { class: "n" }, b ? dpc((a / b - 1) * 100) : "–"), el("td", { class: "n" }, mm(ytdA)), el("td", { class: "n" }, ytdB ? dpc((ytdA / ytdB - 1) * 100) : "–"));
      });
      body.append(card(`Latest month: ${monLabel(months[li])}`, "Click a row to chart it above. Latest months are provisional.", el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Tax", monLabel(months[li]), "vs a year ago", "Year to date", "vs same period last year"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))), el("tbody", {}, rows)))));
      // C. benefits paid by HMRC
      const c4 = chartBox(), sp = H.spend_m;
      body.append(card("Benefits that HMRC pays", "Monthly payments of tax credits (being wound down), Child Benefit and Tax-Free Childcare, £ million.", c4));
      draw(() => lineChart(c4, { x: months.map(monLabel), fmt: mm, axisFmt: mm, zero: true, height: 240, title: "HMRC-administered payments",
        series: Object.keys(sp).filter(k => sp[k].some(v => v != null)).map(k => ({ name: k, values: sp[k] })) }));

      // D. tax gap
      body.append(taxGapSection());
    }
  };

  function taxGapSection() {
    const G = D.hmrc.taxgap, wrap = el("div", {});
    const yrs = G.years;
    const total = G.gap_bn.find(r => r.labels[0] === "Total tax gap").values, pctRow = G.gap_pct.find(r => r.labels[0] === "Total tax gap").values;
    const liab = G.gap_bn.find(r => r.labels[0].startsWith("Total theoretical")).values;
    const cTop = chartBox(), cBy = chartBox();
    wrap.append(card("The tax gap: tax that should have been paid but wasn't", `HMRC's estimate of the difference between the tax due and the tax collected, as a share of total tax liabilities. It is an estimate built from sampling, models and assumptions, and recent years are revised later (see below). Latest: ${bn(total.at(-1))} in ${yrs.at(-1)}, ${pc(pctRow.at(-1))} of ${bn(liab.at(-1))} due.`, cTop));
    draw(() => lineChart(cTop, { x: yrs, fmt: v => nf1.format(v), axisFmt: v => "£" + nf0.format(v) + "bn", zero: true, height: 240, title: "Tax gap £bn and %",
      series: [{ name: "Tax gap, £bn", values: total }] }));
    const c2 = chartBox();
    wrap.append(card("Tax gap as a share of tax due", "The same estimate as a percentage, which removes the effect of tax rises and inflation.", c2));
    draw(() => lineChart(c2, { x: yrs, fmt: pc, axisFmt: v => v + "%", zero: true, height: 220, title: "Tax gap percent", series: [{ name: "% of liabilities", values: pctRow }] }));

    const sel = select("gb", "Break the gap down by", [["tax", "Which tax"], ["behaviour", "Behaviour (evasion, error…)"], ["group", "Who (customer group)"]], taxState.gapBy, v => { taxState.gapBy = v; fill(); });
    const holder = el("div", {});
    wrap.append(card("What the gap is made of", "£ billion.", el("div", { class: "controls" }, sel), cBy, holder));
    function fill() {
      holder.replaceChildren();
      let years = yrs, rows;
      if (taxState.gapBy === "tax") {
        const names = { "Total VAT": "VAT", "Total excise duty": "Excise duties", "Total Income Tax, NICs, Capital Gains Tax": "Income Tax, NICs & CGT", "Total Corporation Tax": "Corporation Tax", "Total other taxes": "Other taxes" };
        rows = G.gap_bn.filter(r => names[r.labels[2]] && r.labels[0] !== "Total tax gap").map(r => ({ name: names[r.labels[2]], values: r.values.map(v => v ?? 0) }));
      } else if (taxState.gapBy === "behaviour") {
        years = G.behaviour.years;
        rows = G.behaviour.rows.filter(r => r.labels[1] === "Tax gap in £bn" && r.labels[0] !== "Total").map(r => ({ name: r.labels[0], values: r.values.map(v => v ?? 0) }));
        holder.append(el("ul", { class: "tight small" }, rows.map(r => el("li", {}, el("b", {}, r.name + ": "), BEHAVIOUR_HELP[r.name] || ""))),
          el("p", { class: "small" }, "Plain-English summaries; HMRC's methodology annex has the precise definitions. “Illustrative” split: HMRC cautions that behaviours are estimated less precisely than the total."));
      } else {
        years = G.groups.years;
        rows = G.groups.rows.filter(r => r.labels[1] === "Tax gap in £bn" && r.labels[0] !== "Total").map(r => ({ name: r.labels[0], values: r.values.map(v => v ?? 0) }));
      }
      const colored = rows.map((r, i) => ({ ...r }));
      draw(() => stackedBars(cBy, { x: years, series: colored, fmt: v => "£" + nf1.format(v) + "bn", axisFmt: v => "£" + nf0.format(v) + "bn", title: "Tax gap breakdown", height: 300 }));
    }
    fill();
    // revisions
    const bias = D.hmrc.revision_bias, rs = D.hmrc.revision_summary;
    const c3 = chartBox();
    const recent = rs.slice(-12);
    wrap.append(card("How HMRC's tax gap estimates change after first publication", `Each bar is the change in a year's estimated tax gap (percentage points of liabilities) between the edition that first estimated it and the latest edition. In the last ${bias.n} years that could be re-estimated, the first estimate was later revised up ${bias.n_up} times (average ${dpc(bias.mean_pp).replace("%", "pp")}). A recent-year gap quoted in the press is therefore likely to be revised, and has tended to be revised upwards.`, c3,
      el("div", { class: "tablewrap", style: "margin-top:10px" }, el("table", {}, el("thead", {}, el("tr", {}, ["Year", "First estimate", "Latest", "Change", "Editions"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))),
        el("tbody", {}, recent.slice().reverse().map(r => el("tr", {}, el("td", {}, r.year), el("td", { class: "n" }, `${pc(r.first)} (${r.first_pub})`), el("td", { class: "n" }, pc(r.latest)), el("td", { class: "n" }, (r.revision_pp >= 0 ? "+" : "−") + nf1.format(Math.abs(r.revision_pp)) + "pp"), el("td", { class: "n" }, r.n_pubs))))))));
    draw(() => barChart(c3, { items: recent.map(r => ({ label: r.year, value: r.revision_pp })), diverging: true, fmt: v => (v >= 0 ? "+" : "−") + nf1.format(Math.abs(v)) + "pp", axisFmt: v => nf1.format(v) + "pp",
      tipFmt: it => { const r = recent.find(x => x.year === it.label); return `${pc(r.first)} (${r.first_pub}) → ${pc(r.latest)} (${r.latest_pub})`; } }));
    return wrap;
  }

  /* ---------- Monthly finances (ONS Public Sector Finances) */
  const fyOf = k => { const y = +k.slice(0, 4), m = +k.slice(5); const s = m >= 4 ? y : y - 1; return `${s}-${String(s + 1).slice(2)}`; };
  const monState = { range: "120", series: "KX5Q", basis: "nominal" };
  const NEAR_ZERO = new Set(["J5II", "JW2Z"]);
  VIEWS.monthly = () => {
    const O = D.ons, S = Object.fromEntries(O.series.map(s => [s.cdid, s])), months = O.months, li = months.length - 1;
    const val = (c, i) => S[c].values[i];
    const fyStart = months.findLastIndex((m, i) => m.endsWith("-04") && i <= li);
    const ytd = (c, off = 0) => S[c].values.slice(fyStart - off, li + 1 - off).reduce((a, v) => a + (v || 0), 0);
    const nM = li - fyStart + 1;
    const root = el("div", {}, el("h2", {}, "Month by month: spending, receipts and borrowing"),
      el("p", { class: "lede" }, `The Office for National Statistics publishes the public sector finances every month. Latest month: ${monLabel(months[li])}. Figures are cash-value (not inflation-adjusted) and not seasonally adjusted, so compare each month with the same month in earlier years. Public sector figures exclude the public sector banks, matching the Treasury's total managed expenditure.`),
      el("div", { class: "kpis" },
        kpi(`Public spending, ${monLabel(months[li])}`, mm(val("KX5Q", li)), `${dpc((val("KX5Q", li) / val("KX5Q", li - 12) - 1) * 100)} on ${monLabel(months[li - 12])}`),
        kpi(`Borrowing, ${monLabel(months[li])}`, mm(val("J5II", li)), `${mm(val("J5II", li - 12))} a year earlier`),
        kpi(`Spending since April ${months[fyStart].slice(0, 4)}`, mm(ytd("KX5Q")), `${nM} months · ${dpc((ytd("KX5Q") / ytd("KX5Q", 12) - 1) * 100)} on the same months last year`),
        kpi(`Borrowing since April ${months[fyStart].slice(0, 4)}`, mm(ytd("J5II")), `${mm(ytd("J5II", 12))} in the same months last year`),
        kpi(`Debt interest since April ${months[fyStart].slice(0, 4)}`, mm(ytd("NMFX")), `central government · ${dpc((ytd("NMFX") / ytd("NMFX", 12) - 1) * 100)} on the same months last year`),
        kpi("Net debt", bn(val("KSE6", li) / 1000), `end of ${monLabel(months[li])}`)));
    const body = el("div", {});
    root.append(el("div", { class: "controls" }, select("mr", "Time range", [["36", "Last 3 years"], ["120", "Last 10 years"], ["999", "Since 1997"]], monState.range, v => { monState.range = v; build(); })), body);
    build();
    return root;

    function build() {
      body.replaceChildren();
      const n = Math.min(+monState.range, months.length), from = months.length - n, xs = months.slice(from).map(monLabel);
      const sl = c => S[c].values.slice(from);
      // 1. headline
      const c1 = chartBox();
      body.append(card("Spending, receipts and borrowing", "Total public sector spending and current receipts each month, £ million. Borrowing is the gap between them; it peaks around the pandemic.", c1));
      draw(() => lineChart(c1, { x: xs, fmt: mm, axisFmt: mm, zero: true, title: "Public sector spending, receipts and borrowing",
        series: [{ name: "Total managed expenditure", values: sl("KX5Q") }, { name: "Current receipts", values: sl("JW2O") }, { name: "Net borrowing", values: sl("J5II") }] }));
      // 2. any series
      const opts = O.series.map(s => [s.cdid, `${s.group.replace(" (excluding banks)", "")}: ${s.label}`]);
      const c2 = chartBox(), c3 = chartBox();
      const lab = S[monState.series].label, fl = O.flags.filter(f => f.tax === lab && months.slice(from).includes(f.month));
      body.append(card("Explore any series", "Choose a spending, tax or borrowing series. Shaded months are unusual compared with the same month a year earlier (see Unusual figures).",
        el("div", { class: "controls" }, select("ms", "Series", opts, monState.series, v => { monState.series = v; build(); })), c2));
      draw(() => lineChart(c2, { x: xs, fmt: mm, axisFmt: mm, zero: true, title: lab, series: [{ name: lab, values: sl(monState.series) }], bands: fl.map(f => ({ x: monLabel(f.month) })) }));
      if (!S[monState.series].stock) {
        const fyList = [...new Set(months.map(fyOf))].slice(-5).reverse().map(s => +s.slice(0, 4));
        const order = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3], col = S[monState.series].values;
        const ser = fyList.map(fy => ({ name: `${fy}-${String(fy + 1).slice(2)}`, values: order.map(mo => { const y = mo >= 4 ? fy : fy + 1, i = months.indexOf(`${y}-${String(mo).padStart(2, "0")}`); return i < 0 ? null : col[i]; }) }));
        body.append(card("The same months across years", "One line per financial year, April to March.", c3));
        draw(() => lineChart(c3, { x: order.map(m => MON[m - 1]), fmt: mm, axisFmt: mm, zero: true, height: 250, title: "Seasonal comparison", series: ser }));
      }
      // 3. where central government money goes (financial-year stack)
      const real = monState.basis === "real";
      const fys = [...new Set(months.map(fyOf))].filter(f => months.filter(m => fyOf(m) === f).length === 12);
      const fsum = c => fys.map(f => months.reduce((a, m, i) => a + (fyOf(m) === f ? (val(c, i) || 0) : 0), 0) * (real ? rf(f) : 1));
      const parts = [["Goods and services", "NMBJ"], ["Social benefits", "GZSJ"], ["Interest on debt", "NMFX"], ["Subsidies", "NMCD"], ["Other grants", "NMFC"]];
      const stack = parts.map(([nm, c]) => ({ name: nm, values: fsum(c) }));
      const cur = fsum("MF6S"), cap = fsum("MF6T");
      stack.push({ name: "Capital spending", values: cap });
      stack.push({ name: "Other", values: fys.map((_, i) => cur[i] - stack.slice(0, 5).reduce((a, s) => a + s.values[i], 0)) });
      const c4 = chartBox();
      body.append(card("What central government spends money on", "Financial-year totals, £ million, adding up the monthly figures. “Other” is whatever remains of current spending after the listed items (for example public service pensions and transfers within government).",
        el("div", { class: "controls" }, select("mb", "Basis", [["nominal", "Cash (nominal)"], ["real", "Real terms (2025-26 prices)"]], monState.basis, v => { monState.basis = v; build(); })), c4));
      draw(() => stackedBars(c4, { x: fys, series: stack, fmt: mm, axisFmt: mm, title: "Central government spending by type" }));
      // 4. cost of debt and net debt
      const roll = S.NMFX.values.map((_, i) => i < 11 ? null : S.NMFX.values.slice(i - 11, i + 1).reduce((a, v) => a + v, 0));
      const c5 = chartBox(), c6 = chartBox();
      body.append(el("div", { class: "grid g2" },
        card("The cost of debt", "Central government net interest payable, rolling 12-month total, £ million. It rises with borrowing, interest rates and inflation-linked gilts.", c5),
        card("Net debt", "Public sector net debt (excluding public sector banks) at the end of each month, £ million.", c6)));
      draw(() => lineChart(c5, { x: xs, fmt: mm, axisFmt: mm, zero: true, height: 250, title: "Rolling 12-month interest", series: [{ name: "Net interest payable, 12 months", values: roll.slice(from) }] }));
      draw(() => lineChart(c6, { x: xs, fmt: mm, axisFmt: mm, zero: true, height: 250, title: "Net debt", series: [{ name: "Net debt", values: sl("KSE6") }] }));
      // 5. table
      const keys = ["KX5Q", "JW2O", "J5II", "MF6U", "NMBJ", "GZSJ", "NMFX", "NMCD", "MF73", "KSS8", "NZGF", "LIBP", "CUDG", "ANLQ"];
      const rows = keys.map(c => {
        const a = val(c, li), b = val(c, li - 12), ya = ytd(c), yb = ytd(c, 12), nz = NEAR_ZERO.has(c);
        return el("tr", { class: "click", onclick: () => { monState.series = c; build(); }, title: "Chart this series" },
          el("td", {}, S[c].label), el("td", { class: "n" }, mm(a)), el("td", { class: "n" }, nz ? mm(a - b) : dpc((a / b - 1) * 100)), el("td", { class: "n" }, mm(ya)), el("td", { class: "n" }, nz ? mm(ya - yb) : dpc((ya / yb - 1) * 100)));
      });
      body.append(card(`Latest month: ${monLabel(months[li])}`, "Click a row to chart it above. For borrowing, changes are shown in £ rather than %. The latest months are provisional and will be revised.",
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Series", monLabel(months[li]), "vs a year ago", "Year to date", "vs same period last year"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))), el("tbody", {}, rows)))));
    }
  };

  /* ---------- Benefit fraud and error (DWP) */
  const benState = { mode: "amount", measure: "total", benefit: "Universal Credit", reasonBenefit: "Universal Credit" };
  const bnM = v => (v == null ? "–" : mm(v));
  const ago = b => b.months_since == null ? "never reviewed" : b.months_since <= 12 ? "within the last year" : `${nf1.format(b.months_since / 12)} years ago`;
  const DEFS = [["Fraud", "A claimant deliberately tried to get money they were not entitled to."], ["Claimant error", "A genuine, unintentional mistake by the claimant."], ["Official error", "A mistake made by DWP, HMRC or a local authority."]];
  VIEWS.benefits = () => {
    const W = D.dwp, all = W.all, last = k => all[k].at(-1), pctL = k => all.pct[k].at(-1), prevY = all.total.at(-2);
    const uc = W.benefits.find(b => b.name === "Universal Credit"), cov = W.coverage, old = cov.buckets["more than 3 years ago"] + cov.buckets["never reviewed"];
    const net = W.net.net.at(-1);
    const root = el("div", {}, el("h2", {}, "Fraud and error in the benefit system"),
      el("p", { class: "lede" }, `Each year the Department for Work and Pensions (DWP) estimates how much benefit money was paid out wrongly, by sampling cases and checking them. Figures cover Great Britain, are estimates with a margin of error, and the latest is for ${last("total").year}. “Overpaid” means too much was paid; it is not the same as proven fraud, and the three types below are estimated separately.`),
      el("div", { class: "kpis" },
        kpi("Overpaid", mm(last("total").est), `${last("total").year} · ${pc(pctL("total").est)} of ${bn(last("expenditure").est / 1000)} · range ${bn(last("total").lo / 1000)}–${bn(last("total").hi / 1000)}`),
        kpi("Of which fraud", mm(last("fraud").est), `${pc(pctL("fraud").est)} of benefit spending`),
        kpi("Lost after recoveries", mm(net.est), `${pc(W.net.pct_net.at(-1).est)} of spending`),
        kpi("Underpaid by official error", mm(W.under.official.at(-1).est), "people owed money they did not receive"),
        kpi("Universal Credit", pc(uc.pct.est), `overpaid · ${uc.cases_pct ? nf0.format(uc.cases_pct.est) + "% of cases had an overpayment error" : ""}`)));
    root.append(el("div", { class: "notice" }, el("b", {}, "How old is the evidence? "), `${bn(old / 1000)} of benefit spending (${pc(old / cov.total_expenditure * 100)}) rests on a fraud and error rate that was last measured more than three years ago, or never. The headline figure is a mix of fresh and carried-forward estimates. See “How recently each benefit was measured” below.`));
    const body = el("div", {});
    root.append(body);
    build();
    return root;

    function build() {
      body.replaceChildren();
      // 1. over time
      const years = all.total.map(p => p.year), bySer = (k, src) => src[k].map(p => p.est);
      const byYear = (arr) => Object.fromEntries(arr.map(p => [p.year, p.est]));
      const c1 = chartBox();
      const rate = benState.mode === "rate";
      const mk = (name, color, src) => ({ name, color, values: years.map(y => (byYear(src)[y] ?? null)) });
      const series = rate
        ? [mk("Fraud", "var(--s2)", all.pct.fraud), mk("Claimant error", "var(--s4)", all.pct.claimant), mk("Official error", "var(--s1)", all.pct.official)]
        : [mk("Fraud", "var(--s2)", all.fraud), mk("Claimant error", "var(--s4)", all.claimant), mk("Official error", "var(--s1)", all.official)];
      body.append(card("How much is overpaid each year", "Central estimates. Estimates before 2016-17 for some benefits are less detailed, and from 2022-23 some underpayments were reclassified, so older and newer years are not perfectly comparable (see Method).",
        el("div", { class: "controls" }, select("bmode", "Show", [["amount", "Amount overpaid (£ million)"], ["rate", "Share of benefit spending (%)"]], benState.mode, v => { benState.mode = v; build(); })), c1));
      draw(() => stackedBars(c1, { x: years, series, fmt: rate ? v => nf1.format(v) + "%" : mm, axisFmt: rate ? v => v + "%" : mm, title: "Benefit overpayments by type" }));
      body.append(el("div", { class: "grid", style: "margin-bottom:18px;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr))" }, ...DEFS.map(([t, d]) => el("div", { class: "card", style: "margin:0" }, el("h3", {}, t), el("p", { class: "small", style: "margin:0" }, d)))));

      // 2. confidence range of the headline rate
      const c2 = chartBox();
      body.append(card("The headline rate and its margin of error", "Total overpaid as a share of all benefit spending, with the lower and upper ends of DWP's confidence range. A bigger gap means a less certain estimate.", c2));
      draw(() => lineChart(c2, { x: years, fmt: pc, axisFmt: v => v + "%", zero: true, height: 230, title: "Overpayment rate",
        series: [{ name: "Estimate", values: all.pct.total.map(p => p.est) }, { name: "Upper", values: all.pct.total.map(p => p.hi), dash: true, color: "var(--other)" }, { name: "Lower", values: all.pct.total.map(p => p.lo), dash: true, color: "var(--other)" }] }));

      // 3. by benefit
      const rows = W.benefits.filter(b => b.expenditure && b.expenditure >= 1000 && b.total.est != null);
      const m = benState.measure;
      const val = b => m === "total" ? b.total.est : m === "pct" ? b.pct.est : b.fraud.est;
      const items = rows.map(b => ({ label: b.name, value: val(b), b })).sort((a, z) => z.value - a.value);
      const c3 = chartBox();
      body.append(card("Which benefits", "Benefits with at least £1bn of spending. Click a row in the table for the reasons behind its errors.",
        el("div", { class: "controls" }, select("bmeas", "Measure", [["total", "Amount overpaid (£ million)"], ["pct", "Share of the benefit's spending (%)"], ["fraud", "Amount lost to fraud (£ million)"]], m, v => { benState.measure = v; build(); })), c3));
      const f = m === "pct" ? v => nf1.format(v) + "%" : mm;
      draw(() => barChart(c3, { items: items.map(i => ({ label: i.label, value: i.value, color: i.b.months_since > 36 ? "var(--s4)" : "var(--s1)" })), fmt: f, axisFmt: f, tipFmt: it => { const b = items.find(x => x.label === it.label).b; return `${f(it.value)} · ${pc(b.pct.est)} of ${bn(b.expenditure / 1000)} · measured ${ago(b)}`; } }));
      body.append(el("p", { class: "small" }, el("span", { class: "sw", style: "display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--s4);margin-right:6px" }), "Amber bars: the rate was last measured more than three years ago."));
      const trs = W.benefits.filter(b => b.total.est != null && (b.expenditure || b.name === "Interdependencies")).map(b => el("tr", { class: "click", onclick: () => { benState.reasonBenefit = W.reasons.find(r => r.benefit === b.name) ? b.name : benState.reasonBenefit; build(); jumpTo("reasoncard"); }, title: "Show the reasons" },
        el("td", {}, b.name), el("td", { class: "n" }, b.expenditure ? bn(b.expenditure / 1000) : "–"), el("td", { class: "n" }, mm(b.total.est)), el("td", { class: "n" }, b.pct.est == null ? "–" : pc(b.pct.est)),
        el("td", { class: "n" }, bnM(b.fraud.est)), el("td", { class: "n" }, b.total.lo == null ? "–" : `${mm(b.total.lo)} – ${mm(b.total.hi)}`),
        el("td", {}, b.months_since > 36 || b.months_since == null ? el("span", { class: "pill warn" }, ago(b)) : ago(b))));
      body.append(card("Every benefit", "Benefits that have closed (Income Support, Incapacity Benefit) have no current spending and are left out.", el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Benefit", "Spending", "Overpaid", "Rate", "Of which fraud", "Range", "Last measured"].map((h, i) => el("th", { class: i && i < 6 ? "n" : "" }, h)))), el("tbody", {}, trs)))));

      // 4. reasons
      const rb = W.reasons.find(r => r.benefit === benState.reasonBenefit) || W.reasons[0];
      const top = rb.reasons.filter(x => x.level === 0 && x.reason !== "Total" && x.total.est).sort((a, z) => z.total.est - a.total.est);
      const c4 = chartBox();
      body.append(el("section", { class: "card", id: "reasoncard" }, el("h3", {}, "What goes wrong"), el("p", { class: "sub" }, "The reason for each overpayment found by DWP's checks, 2025-26. Fraud is shown as part of each total."),
        el("div", { class: "controls" }, select("rsel", "Benefit", W.reasons.map(r => [r.benefit, r.benefit]), rb.benefit, v => { benState.reasonBenefit = v; build(); })), c4,
        el("div", { class: "tablewrap", style: "margin-top:10px" }, el("table", {}, el("thead", {}, el("tr", {}, ["Reason", "Overpaid", "Fraud", "Claimant error", "Official error"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))),
          el("tbody", {}, rb.reasons.filter(x => x.total.est != null).map(x => el("tr", {}, el("td", { style: x.level ? "padding-left:22px;color:var(--ink2)" : x.reason === "Total" ? "font-weight:700" : "" }, x.reason),
            el("td", { class: "n" }, bnM(x.total.est)), el("td", { class: "n" }, bnM(x.fraud.est)), el("td", { class: "n" }, bnM(x.claimant.est)), el("td", { class: "n" }, bnM(x.official.est)))))))));
      draw(() => barChart(c4, { items: top.slice(0, 10).map(x => ({ label: x.reason, value: x.total.est })), fmt: mm, axisFmt: mm, table: false,
        tipFmt: it => { const x = top.find(t => t.reason === it.label); return `${mm(x.total.est)} · fraud ${bnM(x.fraud.est)} · claimant error ${bnM(x.claimant.est)} · official error ${bnM(x.official.est)}`; } }));

      // 5. coverage / how old is the evidence
      const buckets = Object.entries(cov.buckets), colorB = { "within 12 months": "var(--s1)", "1 to 3 years ago": "var(--s3)", "more than 3 years ago": "var(--s4)", "never reviewed": "var(--s2)" };
      const c5 = chartBox();
      body.append(card("How recently each benefit was measured", `Benefit spending in ${all.total.at(-1).year} by when its fraud and error rate was last measured. DWP measures big benefits every year and rotates through the rest, so some published rates are carried forward from earlier years.`, c5));
      draw(() => barChart(c5, { items: buckets.map(([k, v]) => ({ label: k[0].toUpperCase() + k.slice(1), value: v / 1000, color: colorB[k] })), fmt: bn, axisFmt: bn,
        tipFmt: it => `${bn(it.value)} · ${pc(it.value * 1000 / cov.total_expenditure * 100)} of benefit spending` }));

      // 6. net loss
      const c6 = chartBox(), nv = k => Object.fromEntries(W.net[k].map(p => [p.year, p.est])), ny = W.net.gross.map(p => p.year);
      body.append(card("What is recovered", "Money overpaid, money later recovered, and the net loss to the taxpayer, £ million. Recoveries include debts from earlier years.", c6));
      draw(() => lineChart(c6, { x: ny, fmt: mm, axisFmt: mm, zero: true, height: 240, title: "Gross loss, recoveries and net loss",
        series: [{ name: "Overpaid (gross loss)", values: ny.map(y => nv("gross")[y] ?? null) }, { name: "Recovered", values: ny.map(y => nv("recoveries")[y] ?? null), color: "var(--s3)" }, { name: "Net loss", values: ny.map(y => nv("net")[y] ?? null), color: "var(--s2)" }] }));

      // 7. revisions
      const rr = []; W.revisions.forEach(rv => Object.entries(rv.by_fye).filter(([y]) => y >= "2022-23").forEach(([y, v]) => {
        const rels = W.releases.filter(r => v[r]); const first = v[rels[0]].est, lastv = v[rels.at(-1)].est;
        rr.push(el("tr", {}, el("td", {}, `${rv.benefit}: ${rv.line.toLowerCase()}`), el("td", {}, y), ...W.releases.map(r => el("td", { class: "n" }, v[r] ? mm(v[r].est) : "–")),
          el("td", { class: "n", style: lastv !== first ? "font-weight:700" : "" }, (lastv - first >= 0 ? "+" : "−") + mm(Math.abs(lastv - first)).replace("−", ""))));
      }));
      body.append(card("Are past estimates restated?", "The same year's figure as published in each DWP release. DWP rarely changes older years; the latest year is sometimes revised, here by small amounts and downwards.",
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Series", "Year", ...W.releases.map(r => `FYE ${r} release`), "Change"].map((h, i) => el("th", { class: i > 1 ? "n" : "" }, h)))), el("tbody", {}, rr)))));
    }
  };

  /* ---------- Contracts (Contracts Finder and Find a Tender award notices) */
  const procState = { view: "all", mode: "value", sort: "value", q: "", ftype: "", sev: 2, limit: 20, fq: "" };
  const CLS = [["competitive", "Competitive"], ["framework", "Framework call-off"], ["direct", "Direct award / no competition"], ["unspecified", "Procedure not stated"], ["other", "Other"]];
  const CLS_COLOR = { competitive: "var(--s1)", framework: "var(--s3)", direct: "var(--s2)", unspecified: "var(--s4)", other: "var(--other)" };
  const gbp = v => { const a = Math.abs(v), s = v < 0 ? "−" : ""; return a >= 1e9 ? `${s}£${nf2.format(a / 1e9)}bn` : a >= 1e6 ? `${s}£${nf1.format(a / 1e6)}m` : `${s}£${nf0.format(a / 1e3)}k`; };
  VIEWS.procurement = () => {
    const P0 = D.proc, P = procState.view === "all" || !P0.views[procState.view] ? P0 : { ...P0, ...P0.views[procState.view] }, S = P.summary, q = P0.summary.quality, cls = S.by_class;
    const SRC = { cf: "Contracts Finder", fts: "Find a Tender" }, srcText = Object.entries(S.by_source || { cf: { n: S.n } }).map(([k, v]) => `${nf0.format(v.n)} from ${SRC[k] || k}`).join(" and ");
    const share = k => (cls[k] ? cls[k].value / S.total_value * 100 : 0), shareN = k => (cls[k] ? cls[k].n / S.n * 100 : 0);
    const st = P0.summary.by_status, cl = P0.ceilings, noneSt = { n: 0, value: 0 };
    const root = el("div", {}, el("h2", {}, "Contract awards: what has been agreed"),
      el("p", { class: "lede" }, `Contracts that public bodies in England (and some UK-wide bodies) have awarded, as published on Contracts Finder and Find a Tender (${srcText}), ${monLabel(S.months[0])} to ${monLabel(S.months.at(-1))}. This is what has been agreed, not what has been spent: a contract's value is the buyer's estimate of its total over its whole life.`),
      card("Where these figures sit in the buying process", null, el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Stage", "What it is", "On this page?"].map(h => el("th", {}, h)))),
        el("tbody", {},
          el("tr", {}, el("td", {}, el("b", {}, "1. Tender")), el("td", {}, "The invitation to bid: the competitive process a public body runs to ask suppliers for offers. Nothing is agreed yet."), el("td", {}, "No. Tenders are not shown, and are not counted as spending.")),
          el("tr", {}, el("td", {}, el("b", {}, "2. Award")), el("td", {}, "The buyer's decision to give the work to a named supplier, at a stated value."), el("td", {}, "Yes: awards from both services. Contracts Finder records the award but not the signature.")),
          el("tr", {}, el("td", {}, el("b", {}, "3. Signed contract")), el("td", {}, "The formal, legally binding agreement with the winning supplier, signed after the award."), el("td", {}, "Yes, where the notice records a signature date (Find a Tender).")),
          el("tr", {}, el("td", {}, el("b", {}, "4. Payments")), el("td", {}, "What the buyer actually pays, over the life of the contract."), el("td", {}, "No. Not in these notices; it is published separately (spend-over-£25,000 returns).")))))),
      el("div", { class: "controls" }, select("pview", "Show", [["all", "All agreed awards"], ["signed", "Signed contracts only (Find a Tender, signature date recorded)"], ["awarded", "Awarded, signature not recorded (mostly Contracts Finder)"]], procState.view, v => { procState.view = v; route(); })),
      el("div", { class: "kpis" },
        kpi("Awards", nf0.format(S.n), `${monLabel(S.months[0])} – ${monLabel(S.months.at(-1))} · median ${gbp(S.median)}`),
        kpi("Agreed value", gbp(S.total_value), "total over the life of the contracts, not spending"),
        kpi("Signed contracts", gbp((st.signed || noneSt).value), `${nf0.format((st.signed || noneSt).n)} awards with a signature date`),
        kpi("Awarded, not shown as signed", gbp((st.awarded || noneSt).value), `${nf0.format((st.awarded || noneSt).n)} awards; signature not recorded`),
        kpi("Direct award", pc(share("direct")), `of value · ${pc(shareN("direct"))} of awards`),
        kpi("Flags raised", nf0.format(Object.values(P.flag_counts).reduce((a, b) => a + b, 0)), `${P.sev_counts["3"] || 0} high priority`)));
    root.append(el("div", { class: "notice info" }, el("b", {}, "What this cannot show: "), `the number of bidders is not published in these notices, so “only one bid” cannot be tested. ${nf0.format(q.no_supplier_registration)} of ${nf0.format(q.awards)} awards (${pc(q.no_supplier_registration / q.awards * 100)}) name a supplier without a company number. To avoid singling out private individuals, suppliers are named only when they have a company or charity registration or an organisation-style name; ${nf0.format(q.not_named_as_organisation)} awards are counted but never named. Each flag below is a prompt to look closer, not a finding of wrongdoing.`));
    if (S.by_source && S.by_source.fts) root.append(el("div", { class: "notice info" }, el("b", {}, "Two sources. "), `${Object.entries(S.by_source).map(([k, v]) => `${SRC[k] || k}: ${nf0.format(v.n)} awards, ${gbp(v.value)}`).join("; ")}. Find a Tender records the reason for each award made without a call for competition, shown in the flag text; Contracts Finder does not. Find a Tender notices carry the date they were last updated, so an old award that was amended can appear as new, and for the same reason the “published late” test is applied to Contracts Finder awards only.`));
    root.append(el("div", { class: "notice" }, el("b", {}, "Counted once, and ceilings left out. "), `${nf0.format(cl.n)} notices (${gbp(cl.value)}) are frameworks or similar agreements, where the value is the most the buyer expects to spend with a list of suppliers, not a commitment; they are set aside below and not in any total. The work bought through them appears as call-offs. ${nf0.format(q.excluded["also published on Find a Tender (counted once)"] || 0)} awards published on both services are counted once. ${nf0.format(S.future_start.n)} awards (${gbp(S.future_start.value)}) have a contract start date still in the future.`));
    const body = el("div", {});
    root.append(body);
    build();
    root.append(card("Set aside: frameworks and similar agreements", "The largest agreements whose value is a ceiling, not a commitment. They are not counted anywhere above.",
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Buyer", "Agreement", "Ceiling", "Source"].map((h, i) => el("th", { class: i === 2 ? "n" : "" }, h)))),
        el("tbody", {}, cl.items.slice(0, 15).map(c => el("tr", {}, el("td", {}, c.buyer), el("td", {}, c.url ? el("a", { href: c.url, rel: "noopener" }, c.title) : c.title), el("td", { class: "n" }, gbp(c.value)), el("td", {}, SRC[c.src] || c.src))))))));
    return root;

    function build() {
      body.replaceChildren();
      // 1. by month
      const c1 = chartBox(), val = procState.mode === "value";
      const series = CLS.map(([k, name]) => ({ name, color: CLS_COLOR[k], values: S.months.map(m => (val ? (S.by_month_value[m] || {})[k] : (S.by_month_n[m] || {})[k]) || 0) }));
      body.append(card("Awards by month and how they were bought", "“Competitive” is an open or restricted procedure or competitive quotation; “framework” is a call-off from a pre-agreed list of suppliers; “direct award” includes single tender actions and waivers.",
        el("div", { class: "controls" }, select("pmode", "Show", [["value", "Contract value"], ["count", "Number of awards"]], procState.mode, v => { procState.mode = v; build(); })), c1));
      draw(() => stackedBars(c1, { x: S.months.map(monLabel), series, fmt: val ? gbp : nf0.format, axisFmt: val ? gbp : v => nf0.format(v), title: "Awards by procedure type" }));

      // 2. sector
      const c2 = chartBox();
      body.append(card("What is being bought", "Largest sectors (the first two digits of the EU/UK Common Procurement Vocabulary code), by total contract value.", c2));
      draw(() => barChart(c2, { items: S.cpv.slice(0, 14).map(c => ({ label: c.label || c.division, value: c.value })), fmt: gbp, axisFmt: gbp, tipFmt: it => { const c = S.cpv.find(x => (x.label || x.division) === it.label); return `${gbp(it.value)} · ${nf0.format(c.n)} awards`; } }));

      // 3. buyers
      const sorts = { value: b => b.value, direct: b => b.direct_value / b.value, unspec: b => b.unspec_n / b.n, late: b => b.late_n / b.n, conc: b => b.top_share };
      const labels = { value: "Largest total value", direct: "Highest share of value awarded without competition", unspec: "Highest share not stating the procedure", late: "Most often published late", conc: "Most dependent on one supplier" };
      let bs = P.buyers.filter(b => b.n >= (procState.sort === "value" ? 1 : 10) && (!procState.q || b.buyer.toLowerCase().includes(procState.q.toLowerCase())));
      bs = bs.slice().sort((a, z) => sorts[procState.sort](z) - sorts[procState.sort](a)).slice(0, 25);
      body.append(card("Buyers", "Buyers with at least 10 awards when ranking by a share. Shares are of this buyer's awards in the period.",
        el("div", { class: "controls" }, select("psort", "Rank by", Object.entries(labels), procState.sort, v => { procState.sort = v; build(); }),
          el("label", {}, "Find a buyer", el("input", { type: "search", id: "pq", value: procState.q, placeholder: "e.g. Council, NHS", oninput: e => { procState.q = e.target.value; clearTimeout(procState.t); procState.t = setTimeout(() => { const release = holdView(); build(); release(); }, 250); } }))),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Buyer", "Awards", "Value", "No competition", "Not stated", "Published late", "Biggest supplier"].map((h, i) => el("th", { class: i && i < 6 ? "n" : "" }, h)))),
          el("tbody", {}, bs.map(b => el("tr", { class: "click", onclick: () => { procState.fq = b.buyer; procState.sev = 1; build(); jumpTo("proc-flags"); }, title: "Show this buyer's flags" },
            el("td", {}, b.buyer), el("td", { class: "n" }, nf0.format(b.n)), el("td", { class: "n" }, gbp(b.value)), el("td", { class: "n" }, pc(b.direct_value / b.value * 100)),
            el("td", { class: "n" }, pc(b.unspec_n / b.n * 100)), el("td", { class: "n" }, nf0.format(b.late_n)), el("td", {}, b.top_supplier ? `${b.top_supplier} (${nf0.format(b.top_share * 100)}%)` : "–"))))))));

      // 4. suppliers
      body.append(card("Largest suppliers", "Organisations only, by total contract value across buyers. Large totals usually reflect large framework or infrastructure contracts, not misconduct.",
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Supplier", "Awards", "Total value", "Different buyers"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))),
          el("tbody", {}, S.top_suppliers.slice(0, 20).map(s => el("tr", {}, el("td", {}, s.name), el("td", { class: "n" }, nf0.format(s.n)), el("td", { class: "n" }, gbp(s.value)), el("td", { class: "n" }, nf0.format(s.buyers)))))))));

      // 5. bunching
      const bu = P.bunching, cb = chartBox();
      const bHead = el("tr", {}, ["Value", "Just below", "Just above", "Ratio", "Score (z)", ""].map((h, i) => el("th", { class: i && i < 5 ? "n" : "" }, h)));
      const bRows = bu.slice(0, 12).map(b => el("tr", {},
        el("td", {}, gbp(b.threshold)), el("td", { class: "n" }, nf0.format(b.below)), el("td", { class: "n" }, nf0.format(b.above)),
        el("td", { class: "n" }, b.ratio == null ? "–" : nf2.format(b.ratio)), el("td", { class: "n" }, nf1.format(b.z)),
        el("td", {}, b.flag ? el("span", { class: "pill warn" }, "pile-up") : "")));
      body.append(card("Do awards pile up just below round-number limits?",
        "If buyers shape contracts to stay under a limit, there are more awards just below a round value than just above it. For each value, the chart compares awards in the 5% band just below with the 5% band just above. The score (z) measures how surprising the pile-up is; 3 or more is flagged. Round numbers are also popular for innocent reasons, so a high score is a prompt to look, not proof.",
        cb, el("div", { class: "tablewrap", style: "margin-top:10px" }, el("table", {}, el("thead", {}, bHead), el("tbody", {}, bRows)))));
      draw(() => barChart(cb, { items: bu.slice(0, 12).map(b => ({ label: gbp(b.threshold), value: b.z, color: b.flag ? "var(--s4)" : "var(--s1)" })), fmt: v => nf1.format(v), axisFmt: v => nf0.format(v), diverging: true, table: false, tipFmt: it => `score ${nf1.format(it.value)}` }));

      // 6. flags
      const types = Object.entries(P.types), fl = P.flags.filter(f => (!procState.ftype || f.type === procState.ftype) && f.sev >= procState.sev && (!procState.fq || (f.buyer || "").toLowerCase().includes(procState.fq.toLowerCase()) || (f.supplier || "").toLowerCase().includes(procState.fq.toLowerCase())));
      const tiles = el("div", { class: "kpis" }, types.map(([k, t]) => el("button", { class: "kpi", "aria-pressed": String(procState.ftype === k), style: "text-align:left;cursor:pointer", onclick: () => { procState.ftype = procState.ftype === k ? "" : k; if (procState.ftype) procState.sev = 1; procState.limit = 20; build(); jumpTo("proc-flags"); } },
        el("div", { class: "l" }, t.title), el("div", { class: "v" }, nf0.format(P.flag_counts[k] || 0)), el("div", { class: "d" }, "show list ↓"))));
      body.append(tiles);
      body.append(el("section", { class: "card", id: "proc-flags" }, el("h3", {}, `${nf0.format(fl.length)} flagged awards`),
        el("p", { class: "sub" }, procState.ftype ? P.types[procState.ftype].text : "The largest and most serious are listed first. Only the top flags are kept on this page; the full tests are described under Method."),
        el("div", { class: "controls" }, select("psev", "Minimum severity", [["3", "High only"], ["2", "Medium and above"], ["1", "Everything"]], String(procState.sev), v => { procState.sev = +v; procState.limit = 20; build(); }),
          select("ptype", "Test", [["", "All tests"], ...types.map(([k, t]) => [k, t.title])], procState.ftype, v => { procState.ftype = v; procState.limit = 20; build(); }),
          el("label", {}, "Buyer or supplier", el("input", { type: "search", id: "pfq", value: procState.fq, placeholder: "name contains…", oninput: e => { procState.fq = e.target.value; procState.limit = 20; clearTimeout(procState.t2); procState.t2 = setTimeout(() => { const release = holdView(); build(); release(); }, 250); } }))),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Test", "Buyer", "Supplier", "Value", "What the notice shows"].map((h, i) => el("th", { class: i === 4 ? "n" : "" }, h)))),
          el("tbody", {}, fl.slice(0, procState.limit).map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, P.types[f.type].title), el("td", {}, f.buyer), el("td", {}, f.supplier || "–"), el("td", { class: "n" }, f.value_fmt),
            el("td", {}, f.detail, f.url ? [" ", el("a", { href: f.url, rel: "noopener", target: "_blank" }, "Official notice")] : null)))))),
        fl.length > procState.limit ? el("p", {}, el("button", { onclick: () => { procState.limit += 30; build(); } }, `Show more (${fl.length - procState.limit} left)`)) : null));
      // 7. data limits
      body.append(card("What the data cannot tell us", null, el("ul", { class: "tight" },
        el("li", {}, `${nf0.format(q.unspecified_method)} awards (${pc(q.unspecified_method / q.awards * 100)}) do not state the procedure used, so they cannot be classed as competitive or not.`),
        el("li", {}, `${nf0.format(q.no_tender_estimate)} awards (${pc(q.no_tender_estimate / q.awards * 100)}) have no advertised estimate, so award-versus-estimate cannot be checked.`),
        el("li", {}, `${nf0.format(q.zero_or_negative_value)} awards have a zero or negative value and ${nf0.format(q.bad_dates)} have contract end dates before their start dates. These are data-entry problems in the notices, not necessarily real contracts.`),
        el("li", {}, `${Object.entries(q.excluded).map(([k, v]) => `${nf0.format(v)} notices excluded (${k})`).join("; ") || "No notices were excluded."}.`),
        el("li", {}, "Awards with no published value (" + nf0.format(q.excluded && q.excluded["no value"] || 0) + ") are left out. Notices that appear on both services are counted twice; the overlap is small (about 3% in a test)."))));
    }
  };

  /* ---------- Borrowing & debt */
  const borState = { measure: "borrowing", range: "all", hold: "share", yrange: "all", frange: "120" };
  VIEWS.borrowing = () => {
    const B = D.bor, O = D.ons, S = Object.fromEntries(O.series.map(s => [s.cdid, s])), months = O.months, li = months.length - 1;
    const fs = months.findLastIndex(m => m.endsWith("-04")), sum = (c, a, b) => S[c].values.slice(a, b).reduce((x, v) => x + (v || 0), 0);
    const ytd = sum("J5II", fs, li + 1), ytdPrev = sum("J5II", fs - 12, li + 1 - 12), lastFY = sum("J5II", fs - 12, fs), fyLabel = fyOf(months[fs - 12]);
    const lastNZ = a => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return [i, a[i]]; return [-1, null]; };
    const [gi, gdp] = lastNZ(B.annual.net_debt_gdp), gdpYear = B.annual.years[gi];
    const int = B.interest_share.at(-1), iss = B.issuance, ii = iss.years.length - 1, Y = B.yields, ym = Y.months.length - 1;
    const root = el("div", {}, el("h2", {}, "Borrowing and debt"),
      el("p", { class: "lede" }, "Government borrows when it spends more than it receives; each year's borrowing adds to the national debt, and the debt costs interest. Most of it is borrowed by selling “gilts” (government bonds) to investors, so who buys them, and the interest rate they demand, decide what borrowing costs. This page follows that chain using the ONS public finances, the Debt Management Office (DMO) and the Bank of England."),
      el("div", { class: "kpis" },
        kpi("Borrowed so far this year", bn(ytd / 1000), `since April ${months[fs].slice(0, 4)} · ${bn(ytdPrev / 1000)} in the same months last year`),
        kpi(`Borrowed in ${fyLabel}`, bn(lastFY / 1000), "the last full financial year"),
        kpi("Net debt", `£${nf2.format(S.KSE6.values[li] / 1e6)}tn`, `end of ${monLabel(months[li])} · ${nf0.format(gdp)}% of GDP in ${gdpYear}`),
        kpi(`Interest on debt, ${int.year}`, bn(int.interest / 1000), `${nf1.format(int.share)}p of every £1 of receipts`),
        kpi(`Yield on new gilts, ${iss.years[ii]}`, pc(iss.avg_yield[ii]), `average on ${bn(iss.gross_bn[ii])} issued`),
        kpi("10-year gilt yield", pc(Y.latest.IUDMNPY), `${niceDate(Y.latest.date)} · ${pc(Y.monthly.IUDMNPY[ym - 12])} a year earlier`)));
    const body = el("div", {});
    root.append(body);
    build();
    return root;

    function build() {
      body.replaceChildren();
      const A = B.annual, from = borState.range === "all" ? 0 : A.years.indexOf(1997), ys = A.years.slice(from).map(String);
      const cut = a => a.slice(from);
      // 1. history
      const m = borState.measure, c1 = chartBox();
      const spec = { borrowing: [cut(A.borrowing).map(v => v == null ? null : v / 1000), v => bn(v), "£ billion of borrowing in the calendar year (cash terms)"],
        gdp: [cut(A.gg_borrowing_gdp), v => pc(v), "general government net borrowing as a share of GDP (a slightly different measure from the headline, available from the 1990s)"],
        debt: [cut(A.net_debt_gdp), v => pc(v), "public sector net debt (excluding public sector banks) as a share of GDP"] }[m];
      body.append(card("Borrowing and debt over time", `By calendar year. Showing ${spec[2]}.`,
        el("div", { class: "controls" }, select("bm", "Measure", [["borrowing", "Borrowing (£bn)"], ["gdp", "Borrowing (% of GDP)"], ["debt", "Net debt (% of GDP)"]], m, v => { borState.measure = v; build(); }),
          select("br", "Period", [["all", "Since 1946"], ["1997", "Since 1997"]], borState.range, v => { borState.range = v; build(); })), c1));
      const vals = spec[0], lo = vals.findIndex(v => v != null);
      draw(() => lineChart(c1, { x: ys.slice(lo), fmt: spec[1], axisFmt: m === "borrowing" ? (v => "£" + nf0.format(v) + "bn") : (v => v + "%"), zero: true, title: "Borrowing history", series: [{ name: m === "debt" ? "Net debt" : "Borrowing", values: vals.slice(lo) }] }));

      // 2. spending vs receipts
      const c2 = chartBox();
      body.append(card("Spending against income", "Borrowing is the gap between what government spends and what it receives. £ billion by calendar year, cash terms.", c2));
      draw(() => lineChart(c2, { x: ys, fmt: v => bn(v), axisFmt: v => "£" + nf0.format(v) + "bn", zero: true, height: 260, title: "Spending and receipts",
        series: [{ name: "Total spending", values: cut(A.spending).map(v => v == null ? null : v / 1000) }, { name: "Receipts (taxes and other income)", values: cut(A.receipts).map(v => v == null ? null : v / 1000), color: "var(--s3)" }] }));

      // 3. who lends
      const H = B.holdings, hq = H.quarters, hcut = borState.hold === "share";
      const c3 = chartBox();
      const series = H.groups.map(g => ({ name: g.name, values: g.values.map((v, i) => v == null ? null : hcut ? v / H.total[i] * 100 : v / 1000) }));
      body.append(card("Who lends to the government", "Who holds the government's gilts, quarterly since 1987, valued at market prices. (Gilts are government bonds: lending to the government in exchange for interest.) A group can briefly hold a negative amount: UK banks were net short in some quarters from 2002, which is why the stack dips below zero and above 100% in places.",
        el("div", { class: "controls" }, select("bh", "Show", [["share", "Share of all gilts (%)"], ["amount", "Amount held (£ billion)"]], borState.hold, v => { borState.hold = v; build(); })), c3));
      const hx = hq.filter((_, i) => i % 4 === 0 || i === hq.length - 1);
      draw(() => stackedBars(c3, { x: hq, series, fmt: hcut ? v => nf1.format(v) + "%" : v => "£" + nf0.format(v) + "bn", axisFmt: hcut ? v => v + "%" : v => "£" + nf0.format(v) + "bn", noTotal: hcut, title: "Gilt holdings by type of holder" }));
      const lastQ = hq.at(-1), trs = H.shares.map(s => el("tr", {}, el("td", {}, s.name), el("td", { class: "n" }, bn(s.now / 1000)), el("td", { class: "n" }, pc(s.share)),
        el("td", { class: "n" }, pc(s.share_1y)), el("td", { class: "n" }, pc(s.share_5y)), el("td", { class: "n" }, (s.change_1y >= 0 ? "+" : "−") + bn(Math.abs(s.change_1y) / 1000).replace("−", ""))));
      body.append(card(`Holders at ${lastQ}`, "Share of all gilts now, one year ago and five years ago. The Bank of England bought gilts during the pandemic and 2008 crisis (quantitative easing) and is now selling them back; others have taken their place.",
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Holder", "Held", "Share now", "1 year ago", "5 years ago", "Change in a year"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))), el("tbody", {}, trs)))));

      // 4. what it costs
      const ycut = borState.yrange === "all" ? 0 : Y.months.length - +borState.yrange, c4 = chartBox();
      const yser = Object.entries(Y.series).map(([k, nm]) => ({ name: nm + (k === "IUDSIZC" ? "" : " gilt"), values: Y.monthly[k].slice(ycut) }));
      body.append(card("What it costs to borrow: gilt yields", "The yield is the interest rate investors demand to lend to the government for 5, 10 or 20 years (monthly averages, from the Bank of England). The inflation-linked yield is what is paid above inflation.",
        el("div", { class: "controls" }, select("by", "Period", [["all", "Since 1997"], ["120", "Last 10 years"], ["36", "Last 3 years"]], borState.yrange, v => { borState.yrange = v; build(); })), c4));
      draw(() => lineChart(c4, { x: Y.months.slice(ycut).map(monLabel), fmt: v => v == null ? "–" : pc(v), axisFmt: v => v + "%", zero: true, title: "Gilt yields", series: yser }));
      const c5 = chartBox(), c6 = chartBox();
      body.append(el("div", { class: "grid g2" },
        card("The price actually paid on new borrowing", "Average yield on gilts the DMO sold each financial year (from 1998-99). Borrowing was cheap for a decade and rose sharply from 2022.", c5),
        card("How much was borrowed through gilts", "Gilts sold each financial year, £ billion cash raised.", c6)));
      draw(() => lineChart(c5, { x: iss.years, fmt: pc, axisFmt: v => v + "%", zero: true, height: 250, title: "Average gilt issuance yield", series: [{ name: "Average yield on new gilts", values: iss.avg_yield }] }));
      draw(() => stackedBars(c6, { x: iss.years, series: [{ name: "Gilts sold", values: iss.gross_bn, color: "var(--s1)" }], fmt: v => bn(v), axisFmt: v => "£" + nf0.format(v) + "bn", noTotal: true, height: 250, title: "Gilt issuance" }));
      const c7 = chartBox(), IS = B.interest_share;
      body.append(card("What the interest takes", "Central government interest payments as a share of everything it receives, by financial year. It peaked in 2022-23 when inflation pushed up the cost of index-linked gilts.", c7));
      draw(() => lineChart(c7, { x: IS.map(r => r.year), fmt: v => nf1.format(v) + "p", axisFmt: v => v + "p", zero: true, height: 230, title: "Interest as pence per £1 of receipts", series: [{ name: "Pence of each £1 of receipts spent on interest", values: IS.map(r => r.share) }] }));

      // 5. month by month
      const fr = Math.min(+borState.frange, months.length), f0 = months.length - fr, c8 = chartBox();
      const fl = B.flags.filter(f => months.slice(f0).includes(f.month));
      body.append(card("Borrowing month by month", "Cash borrowed each month, £ million (negative = a surplus). Tax arrives in lumps, so compare with the same month in other years.",
        el("div", { class: "controls" }, select("bf", "Period", [["36", "Last 3 years"], ["120", "Last 10 years"], ["999", "Since 1997"]], borState.frange, v => { borState.frange = v; build(); })), c8));
      draw(() => lineChart(c8, { x: months.slice(f0).map(monLabel), fmt: mm, axisFmt: mm, zero: true, title: "Monthly borrowing", series: [{ name: "Net borrowing", values: S.J5II.values.slice(f0) }], bands: fl.map(f => ({ x: monLabel(f.month) })) }));
      if (fl.length) body.append(el("div", { class: "notice info" }, el("b", {}, `${fl.length} unusual month${fl.length > 1 ? "s" : ""} (shaded): `), fl.slice(0, 2).map(f => f.detail).join(" "), fl.length > 2 ? ` (+${fl.length - 2} more on the Unusual figures page.)` : ""));

      // 6. explainer
      body.append(card("Reading this page", null, el("ul", { class: "tight" },
        el("li", {}, el("b", {}, "Borrowing vs debt. "), "Borrowing is a flow: what was added in a period. Debt is the stock built up over time. The figures here exclude the public sector banks, as the Treasury's headline totals do."),
        el("li", {}, el("b", {}, "Calendar vs financial years. "), "ONS's long-run annual series is by calendar year; the financial-year figures (April to March) are added up from the monthly data."),
        el("li", {}, el("b", {}, "Gilts are only part of the debt. "), "The holdings table covers gilts at market value. Government also borrows through Treasury bills, National Savings and other routes that are not shown here."),
        el("li", {}, el("b", {}, "Holdings are by type of holder, "), "not named investors, and are published quarterly with a lag, so the latest quarter is a few months old."),
        el("li", {}, el("b", {}, "Not covered yet. "), "Individual gilt auction results (how heavily each sale was oversubscribed) and the maturity profile of the debt are published by the DMO and could be added."))));
    }
  };

  /* ---------- What it buys: council spending paired with results */
  const bState = { p: 0, g: 0, hl: "" };
  VIEWS.buys = () => {
    const root = el("div", {}, el("h2", {}, "What it buys"),
      el("p", { class: "lede" }, "Knowing what a council spends is only half the story. This page sets spending beside something measurable that the spending is meant to affect, council by council, and asks whether councils that spend more get more."),
      el("p", { class: "sub" }, "Loading…"));
    loadJSON("outcomes").then(d => { D.oc = d; if (!main.contains(root)) return; root.lastChild.remove(); root.append(...buysBody()); }, e => root.append(el("div", { class: "notice" }, "Could not load: " + e.message)));
    return root;
  };
  function buysBody() {
    const O = D.oc, out = [];
    const strength = r => { const a = Math.abs(r); return a < 0.1 ? "no real" : a < 0.3 ? "a weak" : a < 0.5 ? "a moderate" : "a strong"; };
    const dirWord = (r, better) => r > 0 ? (better > 0 ? "better" : "worse") : (better > 0 ? "worse" : "better");
    out.push(el("div", { class: "notice" }, el("b", {}, "Association is not cause. "),
      "A pattern between spending and results can reflect many things the data cannot see: how a service is organised, the type of area, past investment, how results are measured. A council that spends a lot and gets poor results is a good place to ask questions, not proof that money is wasted; a council that spends little and does well may be doing something others could learn from, or may be storing up problems. Councils are only compared with councils that do the same job."));
    const pairs = O.pairings;
    const body = el("div", { id: "buys-body" });
    out.push(card("Choose a pairing", null, el("div", { class: "controls" },
      select("bp", "Service and result", [...pairs.map((p, i) => [String(i), p.title + " · " + p.service + " (council by council)"]), ["schools", "Schools · Education (national, over time)"], ["nhs", "NHS waiting lists · Health (national, over time)"]], String(bState.p), v => { bState.p = isNaN(+v) ? v : +v; bState.g = 0; bState.hl = ""; paint(); }))));
    out.push(body);
    function paint() {
      if (bState.p === "schools") return paintSchools();
      if (bState.p === "nhs") return paintNhs();
      const P = pairs[bState.p], G = P.groups[Math.min(bState.g, P.groups.length - 1)], S = G.stats;
      const X = P.x || {}, Y = G.y || {}, grades = Y.grades;
      const dpf = (v, dp) => (dp ? nf1 : nf0).format(v);
      const fx = v => (X.prefix || "") + dpf(v, X.dp) + (X.suffix || "");
      const fy = grades ? v => grades[Math.round(v)] || "" : v => dpf(v, Y.dp) + (Y.suffix || "");
      const jit = (c, i) => grades ? (((c.split("").reduce((a, ch) => a * 31 + ch.charCodeAt(0), i) % 100) / 100) - 0.5) * 0.55 : 0;
      const dsort = G.points.map(p => p.d).sort((a, b) => a - b), t1 = dsort[Math.floor(dsort.length / 3)], t2 = dsort[Math.floor(dsort.length * 2 / 3)];
      const col = d => d <= t1 ? SERIES[0] : d <= t2 ? SERIES[1] : SERIES[4];
      const pts = G.points.map((p, i) => ({ x: p.x, y: p.y + jit(p.c, i), label: p.n, ytrue: p.y, color: col(p.d), hl: p.c === bState.hl, extra: "Deprivation score " + nf1.format(p.d) + " (higher = more deprived)" }));
      const ctl = S.controls.length > 1 ? `deprivation and ${S.controls.slice(1).join(" and ")}` : "deprivation";
      const sig = ci => ci && (ci[0] > 0 || ci[1] < 0);
      const rawLine = `Across ${S.n} councils of this kind, ${sig(S.rho_ci) ? strength(S.rho) + " pattern: councils that spend more per " + (X.per || "resident") + " tend to have " + dirWord(S.rho, G.better) + " results" : "no clear pattern between spending and results"} (rank correlation ${S.rho > 0 ? "+" : "−"}${nf2.format(Math.abs(S.rho))}${S.rho_ci ? `, 95% range ${nf2.format(S.rho_ci[0])} to ${nf2.format(S.rho_ci[1])}` : ""}).`;
      const adjLine = `After allowing for ${ctl}: ${sig(S.rho_adj_ci) ? strength(S.rho_adj) + " pattern remains" : "the pattern is no longer distinguishable from none"} (${S.rho_adj > 0 ? "+" : "−"}${nf2.format(Math.abs(S.rho_adj))}${S.rho_adj_ci ? `, 95% range ${nf2.format(S.rho_adj_ci[0])} to ${nf2.format(S.rho_adj_ci[1])}` : ""}).`;
      const needLine = `More deprived areas ${S.outcome_vs_imd * (G.better) < -0.1 ? "have worse" : S.outcome_vs_imd * (G.better) > 0.1 ? "have better" : "have about the same"} results on this measure (${S.outcome_vs_imd > 0 ? "+" : "−"}${nf2.format(Math.abs(S.outcome_vs_imd))}) and ${S.spend_vs_imd > 0.1 ? "spend more" : S.spend_vs_imd < -0.1 ? "spend less" : "spend about the same"} (${S.spend_vs_imd > 0 ? "+" : "−"}${nf2.format(Math.abs(S.spend_vs_imd))}).`;
      const c1 = chartBox();
      const hlSel = select("bhl", "Find a council", [["", "None"], ...G.points.slice().sort((a, b) => a.n.localeCompare(b.n)).map(p => [p.c, p.n])], bState.hl, v => { bState.hl = v; paint(); });
      const grp = P.groups.length > 1 ? select("bg", "Councils and result", P.groups.map((g, i) => [String(i), g.label + " · " + g.outcome_label]), String(bState.g), v => { bState.g = +v; bState.hl = ""; paint(); }) : null;
      const legend = el("p", { class: "small" }, el("span", { style: `color:${SERIES[0]}` }, "● "), "Least deprived third  ", el("span", { style: `color:${SERIES[1]}` }, "● "), "Middle third  ", el("span", { style: `color:${SERIES[4]}` }, "● "), "Most deprived third. Dashed line: straight-line fit, as a guide.");
      const hl = G.points.find(p => p.c === bState.hl);
      const list = (title, sub, rows) => el("div", {}, el("h4", {}, title), el("p", { class: "sub" }, sub), rows.length ? el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Council", "Spending", "Result"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))),
        el("tbody", {}, rows.map(r => el("tr", { class: "click", onclick: () => { lcState.code = r.code; location.hash = "#/councils"; } }, el("td", {}, r.name), el("td", { class: "n" }, fx(r.x)), el("td", { class: "n" }, fy(r.y))))))) : el("p", { class: "small" }, "None stand out clearly."));
      body.replaceChildren(card(P.title + ": " + G.outcome_label, G.label, ...(grp ? [el("div", { class: "controls" }, grp)] : []),
        ...(P.caution ? [el("div", { class: "notice" }, el("b", {}, "Careful with the direction. "), P.caution)] : []),
        el("ul", { class: "tight" }, el("li", {}, rawLine), el("li", {}, adjLine), el("li", {}, needLine)),
        el("div", { class: "controls" }, hlSel), hl ? el("p", {}, el("b", {}, hl.n), `: spending ${fx(hl.x)}, result ${fy(hl.y)}. Median for councils of this kind: spending ${fx(S.median_x)}, result ${fy(S.median_y)}.`) : null,
        legend, c1,
        el("p", { class: "small" }, `${S.n} of ${G.eligible} councils of this kind are shown; the rest lack spending, population, deprivation or result data for the period.`)),
        ...(G.by_grade ? [card("Spending by inspection grade", "Median and middle half of councils (25th to 75th percentile) in each Ofsted grade. Few councils are graded Inadequate, so that row is based on very few.", el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Ofsted grade", "Councils", "Median", "Middle half"].map((h, i) => el("th", { class: i ? "n" : "" }, h)))),
          el("tbody", {}, G.by_grade.map(r => el("tr", {}, el("td", {}, r.grade), el("td", { class: "n" }, r.n), el("td", { class: "n" }, fx(r.median)), el("td", { class: "n" }, `${fx(r.p25)} to ${fx(r.p75)}`)))))))] : []),
        card("Where spending and results part ways", `Councils whose spending and results are furthest apart once need (${ctl}) is allowed for. These are the places to ask questions; click a council to see its spending profile.`,
          el("div", { class: "grid g2" }, list("Spending more than need suggests, results poorer than expected", "Possible questions: what is the money paying for? Is the service organised differently?", S.high_spend_poor),
            list("Spending less than need suggests, results better than expected", "Possible questions: is this efficient, or are costs being pushed elsewhere (to the county, to later years)?", S.low_spend_good))),
        card("How to read this pairing", P.spend_label + ".", el("ul", { class: "tight" }, ...P.notes.map(n => el("li", {}, n)),
          el("li", {}, "Correlations here are Spearman rank correlations: 0 means no pattern, +1 or −1 means councils line up perfectly. Allowing for need uses the English Indices of Deprivation 2025 (average score for the area)" + (S.controls.length > 1 ? " and " + S.controls.slice(1).join(", ") : "") + " by removing their linear effect on the ranks first. The 95% range shows how much a pattern of this size could be down to chance with this many councils.")),
          el("p", { class: "small" }, "Sources: " + (P.sources || O.sources).map(s => s.publisher + ", " + s.title).join("; ") + ".")));
      draw(() => Charts.scatter(c1, { points: pts, xfmt: fx, yfmt: fy, xAxis: v => (X.prefix || "") + nf0.format(v) + (X.suffix || ""), yAxis: grades ? (v => grades[v] || "") : (v => nf0.format(v) + (Y.suffix || "")),
        xlabel: X.label || "Spending", ylabel: (G.short || G.outcome_label).replace(" (3-year average)", "").replace("Ofsted overall effectiveness of children's services", "Ofsted judgement") + (grades || !Y.suffix ? "" : " (" + Y.suffix.trim() + ")"), trend: !grades, title: P.title + " scatter chart" }));
    }
    function paintNhs() {
      const H = O.national.nhs, ms = H.months, i0 = ms.findIndex(m => m >= "2008-03"), mx = ms.slice(i0), L = ms.length - 1;
      const at = m => ms.indexOf(m);
      const w = H.waiting_m, pk = at(H.peak), m19 = at("2019-03");
      const ys = H.years, y0 = "2007-08", yl = ys[ys.length - 1], y19 = "2019-20";
      const sp = H.spend_real_bn, c1 = chartBox(), c2 = chartBox(), c3 = chartBox();
      const std = H.standard_18w, lastMet = ms.filter((m, i) => H.within18_pct[i] != null && H.within18_pct[i] >= std).pop();
      body.replaceChildren(
        card("NHS waiting lists and health spending", "England's hospital waiting list (referral to treatment, RTT) beside what the UK spends on health, in real terms. No correlation is calculated: the pandemic, strikes and a changing list make a single statistic misleading.",
          el("div", { class: "kpis" },
            kpi("People waiting (pathways)", nf2.format(w[L]) + "m", `${monLabel(H.latest)} · peak ${nf2.format(w[pk])}m in ${monLabel(H.peak)} · ${nf2.format(w[m19])}m in Mar 2019`),
            kpi("Seen within 18 weeks", pc(H.within18_pct[L]), `${monLabel(H.latest)} · the standard is ${std}% · ${pc(H.within18_pct[m19])} in Mar 2019`),
            kpi("Waiting over 52 weeks", nf0.format(H.over52[L]), `${monLabel(H.latest)} · peak ${nf0.format(Math.max(...H.over52.filter(v => v != null)))}`),
            kpi("Health spending (real terms)", bn(sp[yl]), `${yl} · ${dpc((sp[yl] / sp[y19] - 1) * 100)} on ${y19} · ${dpc((sp[yl] / sp[y0] - 1) * 100)} on ${y0}`))),
        card("The waiting list", "Incomplete pathways at the end of each month, millions, with NHS England's estimates for trusts that did not report.", c1),
        card("Waiting times against the standard", `Share of patients on the list who have waited 18 weeks or less. The constitutional standard is ${std}%; it was last met in ${monLabel(lastMet)}. (The first months of the series, 2007-08, were still being set up.)`, c2),
        card("Health spending", "Treasury Health function for the whole UK, £ billion in 2025-26 prices The spike in 2020-21 is Covid-19 (testing, vaccines, equipment).", c3),
        card("What the figures show", null, el("ul", { class: "tight" },
          el("li", {}, `The waiting list grew from ${nf2.format(H.waiting_year_end_m["2012-13"])}m at March 2013 to ${nf2.format(H.waiting_year_end_m[y19])}m at March 2020, then to a peak of ${nf2.format(w[pk])}m in ${monLabel(H.peak)}; it was ${nf2.format(w[L])}m in ${monLabel(H.latest)}.`),
          el("li", {}, `Real health spending is ${dpc((sp[yl] / sp[y19] - 1) * 100)} since ${y19} and ${dpc((sp[y19] / sp["2009-10"] - 1) * 100)} between 2009-10 and ${y19}; the list rose in most of those years.`),
          el("li", {}, "The data cannot say how much shorter the list would have been with more or less money: demand, staffing, bed availability, social care capacity and strikes all matter, and spending is for the whole UK while the list is for England.")),
          el("ul", { class: "tight" }, ...H.notes.map(n => el("li", {}, n))),
          el("p", { class: "small" }, "Sources: NHS England, Referral to Treatment waiting times (RTT overview time series); HM Treasury Public Spending Statistics (Table 4.3, Health).")));
      draw(() => lineChart(c1, { x: mx.map(monLabel), fmt: v => nf2.format(v) + "m", axisFmt: v => nf0.format(v) + "m", zero: true, title: "NHS waiting list", series: [{ name: "Incomplete pathways (millions)", values: H.waiting_m.slice(i0) }] }));
      draw(() => lineChart(c2, { x: mx.map(monLabel), fmt: v => nf1.format(v) + "%", axisFmt: v => nf0.format(v) + "%", zero: false, title: "Within 18 weeks",
        series: [{ name: "Seen within 18 weeks", values: H.within18_pct.slice(i0) }, { name: `Standard (${std}%)`, values: mx.map(() => std), dash: true }] }));
      draw(() => lineChart(c3, { x: ys, fmt: v => bn(v), axisFmt: v => "£" + nf0.format(v) + "bn", zero: false, title: "Health spending (real)", series: [{ name: "Health spending, £bn (2025-26 prices)", values: ys.map(y => sp[y]) }] }));
    }
    function paintSchools() {
      const S = O.national.schools, ys = S.years, last = ys[ys.length - 1], y0 = ys[0];
      const at = (ser, y) => ser[y];
      const pctCh = ser => (ser[last] / ser[y0] - 1) * 100;
      const lastWith = ser => [...ys].reverse().find(y => ser[y] != null);
      const em = S.ks4_em95, k2 = S.ks2_rwm;
      const sentence = (name, ser, y1, y2) => ser[y1] != null && ser[y2] != null ? `${name} went from ${nf1.format(ser[y1])}% in ${y1} to ${nf1.format(ser[y2])}% in ${y2}.` : "";
      const lk4 = lastWith(em), lk2 = lastWith(k2);
      const c1 = chartBox(), c2 = chartBox(), c3 = chartBox();
      const bands = S.teacher_graded.concat(S.generous_grading).map(x => ({ x }));
      body.replaceChildren(
        card("Schools: spending and results over time", "England's school results beside what the country spends on education, in real terms, since 2016-17. No correlation is calculated: with ten yearly points, exam rules that changed and pandemic years graded differently, a statistic would mislead.",
          el("div", { class: "kpis" },
            kpi("Spending per pupil", "£" + nf0.format(S.per_pupil[last]), `${last} · ${dpc(pctCh(S.per_pupil))} since ${y0} (real terms)`),
            kpi("Pupils eligible for free school meals", pc(S.fsm_pct[last]), `${last} · ${pc(S.fsm_pct[y0])} in ${y0}: more pupils with greater need`),
            kpi("Key stage 2: reading, writing, maths", pc(k2[lk2]), `expected standard, ${lk2} · ${pc(k2["2018-19"])} in 2018-19, before the pandemic`),
            kpi("GCSE English and maths grade 5+", pc(em[lk4]), `${lk4} · ${pc(em["2018-19"])} in 2018-19`))),
        card("Spending per pupil", "UK Treasury spending on education at every level, in 2025-26 prices, per state-funded school pupil in England.", c1),
        card("Results", "Shaded years: grades set by teachers (2019-20, 2020-21) or deliberately generous (2021-22). Key stage 2 tests were not held in 2019-20 or 2020-21, so those points are blank.", c2),
        card("Need", "Share of pupils taking free school meals on the January census, a common indicator of disadvantage. Eligibility rules widened in 2018 to 2023 (Universal Credit protections), so part of the rise is a change in who qualifies.", c3),
        card("What the figures show", null, el("ul", { class: "tight" },
          el("li", {}, `Real spending per pupil is ${dpc(pctCh(S.per_pupil))} between ${y0} and ${last}; the number of pupils rose until 2023-24 and is now falling.`),
          el("li", {}, sentence("Key stage 2 reading, writing and maths", k2, "2018-19", lk2)),
          el("li", {}, sentence("GCSE English and maths grade 5 or above", em, "2018-19", lk4)),
          el("li", {}, "Key stage 2 results are still below their 2018-19 level, while GCSE English and maths results are above it. They are not comparable like for like: GCSE grading in 2019-22 was set by teachers or deliberately protected pupils, and exam boards have been returning to pre-pandemic standards since. Learning lost in the pandemic, more pupils with greater need, absence and teaching changes could all play a part; the data here cannot separate them.")),
          el("ul", { class: "tight" }, ...S.notes.map(n => el("li", {}, n))),
          el("p", { class: "small" }, "Sources: HM Treasury Public Spending Statistics (Table 4.3, Education); Department for Education: Key stage 2 attainment, Key stage 4 performance, Schools, pupils and their characteristics (via the DfE explore education statistics API).")));
      draw(() => lineChart(c1, { x: ys, fmt: v => "£" + nf0.format(v), axisFmt: v => "£" + nf0.format(v), zero: false, title: "Real spending per pupil", series: [{ name: "Education spending per pupil (real)", values: ys.map(y => S.per_pupil[y]) }] }));
      draw(() => lineChart(c2, { x: ys, fmt: v => nf1.format(v) + "%", axisFmt: v => nf0.format(v) + "%", zero: false, title: "School results", bands,
        series: [{ name: "Key stage 2: reading, writing and maths at expected standard", values: ys.map(y => k2[y]) }, { name: "GCSE: English and maths grade 5 or above", values: ys.map(y => em[y]) }] }));
      draw(() => lineChart(c3, { x: ys, fmt: v => nf1.format(v) + "%", axisFmt: v => nf0.format(v) + "%", zero: true, title: "Free school meals", series: [{ name: "Pupils taking free school meals", values: ys.map(y => S.fsm_pct[y]) }] }));
    }
    paint();
    out.push(card("What is coming", null, el("p", { class: "small" }, "Planned: public health and life expectancy, and further national pairings (crime and policing, adult social care).")));
    return out;
  }

  /* ---------- Compare */
  const cmpState = { ds: "fn", basis: "real", a: null, b: null };
  /* ---------- Local councils (England) */
  const lcState = { code: "", svc: "asc", group: "allpurpose", ftype: "", fsev: 2, flimit: 15 };
  VIEWS.councils = () => {
    const root = el("div", {}, el("h2", {}, "Local councils in England"),
      el("p", { class: "lede" }, "Councils spend around a fifth of all public money on social care, children's services, roads, waste, housing and more. This page uses each council's own return to the government (revenue outturn) with ONS population estimates to compare councils that do the same job."),
      el("p", { class: "sub" }, "Loading council data…"));
    loadJSON("councils").then(d => { D.lc = d; if (!main.contains(root)) return; root.lastChild.remove(); root.append(...lcBody()); }, e => root.append(el("div", { class: "notice" }, "Could not load council data: " + e.message)));
    return root;
  };
  function lcBody() {
    const L = D.lc, F = Object.fromEntries(L.fields.map((f, i) => [f, i])), py = L.peer_year, ly = L.years[L.years.length - 1];
    const svcs = L.services, label = Object.fromEntries(svcs.map(s => [s.key, s.label])), denom = Object.fromEntries(svcs.map(s => [s.key, s.denom]));
    const dName = { pop: "per resident", age0_17: "per child (0-17)", age65: "per person aged 65+" };
    const stat = (k, g) => L.stats.find(s => s.key === k && s.group === g);
    const real = (v, y) => v == null ? null : v * rf(y) / 1000;                 // £ thousand -> £ million, latest prices
    const byCode = new Map(L.councils.map(c => [c.code, c]));
    const val = (c, y, k) => { const v = c.y[y]; return v ? v[F[k]] : null; };
    const unit = (c, y, k) => { const v = val(c, y, k), d = c[denom[k] || "pop"]; return v == null || !d ? null : v * 1000 / d; };
    const eng = L.england, e1 = eng[ly], e0 = eng[L.years[L.years.length - 2]];
    const nSub = L.councils.filter(c => c.y[py]).length, nAll = L.councils.filter(c => c.y[py] || c.missing.includes(py)).length;
    const axb = v => "£" + nf0.format(v / 1000) + "bn";
    const nFlag = L.flags.filter(f => f.sev === 3).length;
    const svcOrder = svcs.map(s => s.key).sort((a, b) => (e1[F[b]] || 0) - (e1[F[a]] || 0));
    const top = svcOrder[0];
    const out = [];
    out.push(el("p", { class: "lede" }, `Figures are net current expenditure by service, from the Ministry of Housing, Communities and Local Government (MHCLG) revenue outturn returns, ${L.years[0]} to ${ly}. ${ly} is provisional and ${nSub} of ${nAll} councils have submitted for ${py}. Spending is shown in ${ly} prices using the GDP deflator. Population is ONS ${L.population_year}.`));
    out.push(el("div", { class: "notice" }, el("b", {}, "A screening tool, not an accusation. "), "Councils differ in the people they serve (age, deprivation, rurality, London costs), in whether they run a service themselves or share it, and in accounting choices. A council far from its peers is a prompt to ask why. Only England is covered; Scotland, Wales and Northern Ireland publish on different systems."));
    out.push(el("div", { class: "kpis" },
      kpi("Council service spending", mm(real(e1[F.totsx], ly)), `${ly} · all English councils incl. police and fire`),
      kpi("Change in real terms", dpc((e1[F.totsx] * rf(ly) / (e0[F.totsx] * rf(L.years[L.years.length - 2])) - 1) * 100), `vs ${L.years[L.years.length - 2]}`),
      kpi("Largest service", label[top], `${mm(real(e1[F[top]], ly))} in ${ly}`),
      kpi("Councils with returns", `${nSub} / ${nAll}`, `${nSub} of ${nAll} English councils have submitted for ${py}`),
      kpi("Schools deficits (DSG)", mm(-L.councils.reduce((a, c) => a + Math.min(0, val(c, py, "dsg") || 0), 0) / 1000), "held on councils' books, " + py),
      kpi("High-priority flags", String(nFlag), "councils to look at first")));
    // England by service over time
    const c1 = chartBox();
    out.push(card("Where English council spending goes", `Net service spending by service, £ million in ${ly} prices. Adult social care and children's services are the fastest-growing.`, c1));
    draw(() => stackedBars(c1, { x: L.years, fmt: mm, axisFmt: axb, title: "English council spending by service",
      series: topPlusOther(svcOrder.map(k => ({ name: label[k], values: L.years.map(y => eng[y] ? real(eng[y][F[k]], y) : null) })), 6, L.years) }));
    // finder
    const prof = el("div", { id: "lc-profile" });
    const sel = select("lcsel", "Choose a council", [["", "Select a council…"], ...L.councils.map(c => [c.code, c.name])], lcState.code, v => { lcState.code = v; paintProfile(); });
    out.push(card("Council profile", "Pick a council to see its spending by service against similar councils: districts with districts, counties with counties, unitary/metropolitan/London councils together.", el("div", { class: "controls" }, sel), prof));
    function paintProfile() {
      prof.replaceChildren();
      const c = byCode.get(lcState.code);
      if (!c) return;
      const g = c.group, yr = c.y[py] ? py : Object.keys(c.y).sort().pop();
      const rows = svcs.filter(s => val(c, yr, s.key) != null && Math.abs(val(c, yr, s.key)) > 0).map(s => {
        const st = stat(s.key, g), u = unit(c, yr, s.key);
        return { s, st, u, tot: val(c, yr, s.key), d: st && u != null ? (u / st.median - 1) * 100 : null };
      });
      const c2 = chartBox();
      prof.append(el("p", {}, el("b", {}, c.name), ` · ${c.cls} · population ${c.pop ? nf0.format(c.pop) : "unknown"} · compared with ${L.groups[g]} · ${yr}${yr !== py ? " (latest year it submitted)" : ""}`));
      if (c.missing.length) prof.append(el("div", { class: "notice" }, `No return received for ${c.missing.join(", ")}.`));
      prof.append(el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Service", "Total", "Rate", "Typical", "Range (10th–90th)", "vs typical"].map((h, i) => el("th", { class: i > 0 && i < 4 || i === 5 ? "n" : "" }, h)))),
        el("tbody", {}, rows.map(r => el("tr", {}, el("td", {}, r.s.label), el("td", { class: "n" }, mm(real(r.tot, yr))),
          el("td", { class: "n" }, r.u == null ? "–" : `£${nf0.format(r.u)}`), el("td", { class: "n" }, r.st ? `£${nf0.format(r.st.median)}` : "–"),
          el("td", {}, r.st ? rangeBar(r.u, r.st) : "–"), el("td", { class: "n" }, r.d == null ? "–" : dpc(r.d))))))));
      prof.append(el("p", { class: "small" }, "Rates are £ per resident, except adult social care (per person aged 65+) and children's social care and education (per child aged 0-17). “Typical” is the median council of the same kind."));
      const ys = L.years.filter(y => c.y[y]);
      prof.append(el("h4", {}, "Total service spending over time (real terms)"), c2);
      draw(() => lineChart(c2, { x: ys, fmt: mm, axisFmt: axb, zero: true, title: c.name + " service spending",
        series: [{ name: c.name, values: ys.map(y => real(val(c, y, "totsx"), y)) }] }));
      const res = val(c, yr, "reserves"), dsg = val(c, yr, "dsg"), nr = val(c, yr, "netrev");
      prof.append(el("div", { class: "kpis" }, kpi("Net revenue spending", mm((nr || 0) / 1000), yr), kpi("Usable reserves", mm((res || 0) / 1000), nr ? pc(res / nr * 100) + " of net spending" : ""),
        kpi("Schools funding (DSG) balance", mm((dsg || 0) / 1000), dsg < 0 ? "deficit" : "surplus or none"), kpi("Net interest paid", mm((val(c, yr, "netint") || 0) / 1000), nr ? pc(val(c, yr, "netint") / nr * 100) + " of net spending" : "")));
      const fl = L.flags.filter(f => f.code === c.code);
      if (fl.length) prof.append(el("ul", { class: "tight" }, fl.map(f => el("li", {}, sevBadge(f.sev), " ", el("b", {}, L.flag_types[f.type].title), " · ", f.year, " – ", f.detail))));
    }
    function rangeBar(u, st) {
      const lo = Math.min(st.p10, u ?? st.p10), hi = Math.max(st.p90, u ?? st.p90), X = v => ((v - lo) / ((hi - lo) || 1) * 100).toFixed(1) + "%";
      return el("div", { class: "rangebar", title: `Typical range £${nf0.format(st.p10)} to £${nf0.format(st.p90)}` },
        el("i", { class: "band", style: `left:${X(st.p10)};width:calc(${X(st.p90)} - ${X(st.p10)})` }), el("i", { class: "med", style: `left:${X(st.median)}` }), el("i", { class: "pt", style: `left:${u == null ? X(st.median) : X(u)}` }));
    }
    // league table
    const lt = el("div", { id: "lc-league" });
    out.push(card("League tables", "Who spends most and least on a service, compared with councils of the same kind. High is not bad and low is not good: it shows where to ask why.",
      el("div", { class: "controls" },
        select("lsv", "Service", svcs.map(s => [s.key, s.label]), lcState.svc, v => { lcState.svc = v; paintLeague(); }),
        select("lgr", "Councils", Object.entries(L.groups).map(([k, t]) => [k, t[0].toUpperCase() + t.slice(1)]), lcState.group, v => { lcState.group = v; paintLeague(); })), lt));
    function paintLeague() {
      const k = lcState.svc, g = lcState.group;
      const items = L.councils.filter(c => c.group === g && c.y[py]).map(c => ({ label: c.name, value: unit(c, py, k) })).filter(i => i.value != null && i.value > 0).sort((a, b) => b.value - a.value);
      const ch = items.slice(0, 12).concat(items.length > 24 ? items.slice(-12) : []);
      const cb = chartBox();
      lt.replaceChildren(el("p", { class: "sub" }, `${label[k]}, £ ${dName[denom[k]]}, ${py}. Top 12 and bottom 12 of ${items.length} councils.`), cb);
      draw(() => barChart(cb, { items: ch, fmt: v => "£" + nf0.format(v), title: label[k] + " league table" }));
    }
    paintLeague();
    // flags
    const fw = el("div", { id: "lc-flags" });
    out.push(el("section", { class: "card", id: "lc-flagcard" }, el("h3", {}, "Councils worth a closer look"), fw));
    function paintFlags() {
      const fl = L.flags.filter(f => f.sev >= lcState.fsev && (!lcState.ftype || f.type === lcState.ftype));
      fw.replaceChildren(el("div", { class: "controls" },
        select("lft", "Kind of flag", [["", "All kinds"], ...Object.entries(L.flag_types).map(([k, t]) => [k, t.title])], lcState.ftype, v => { lcState.ftype = v; lcState.flimit = 15; paintFlags(); }),
        select("lfs", "Minimum severity", [["3", "High only"], ["2", "Medium and above"], ["1", "Everything"]], String(lcState.fsev), v => { lcState.fsev = +v; lcState.flimit = 15; paintFlags(); })),
        el("p", { class: "sub" }, lcState.ftype ? L.flag_types[lcState.ftype].text : "Sorted by severity, then size. Click a row to open that council's profile."),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Year", "Kind", "What the data show"].map(h => el("th", {}, h)))),
          el("tbody", {}, fl.slice(0, lcState.flimit).map(f => el("tr", { class: "click", onclick: () => { lcState.code = f.code; const s = document.getElementById("lcsel"); if (s) s.value = f.code; paintProfile(); jumpTo("lc-profile"); } },
            el("td", {}, sevBadge(f.sev)), el("td", {}, f.year), el("td", {}, L.flag_types[f.type].title), el("td", {}, f.detail)))))),
        fl.length > lcState.flimit ? el("p", {}, el("button", { onclick: () => { lcState.flimit += 25; paintFlags(); } }, `Show more (${fl.length - lcState.flimit} left)`)) : el("p", { class: "small" }, `${fl.length} shown. Click a row to open that council's profile.`));
    }
    paintFlags();
    out.push(el("p", { class: "small" }, "Source: MHCLG, Local authority revenue expenditure and financing, England: revenue outturn; ONS mid-year population estimates. Tests are explained on the Method & sources page."));
    paintProfile();
    return out;
  }

  /* ---------- Compare */
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
    const tileBtn = (title, value, sub, onclick, extra = {}) => el("button", { class: "kpi", style: "text-align:left;cursor:pointer", onclick, ...extra },
      el("div", { class: "l" }, title), el("div", { class: "v" }, String(value)), el("div", { class: "d" }, sub));
    const tiles = el("div", { class: "kpis" }, Object.entries(F.types).map(([k, t]) => {
      if (k === "function_jump") {   // lives in its own table, not the departmental-line list
        return tileBtn(t.title, F.function_flags.length, "in the function tables · jump to table ↓", () => jumpTo("fn-flags"));
      }
      return tileBtn(t.title, F.counts[k] || 0, "in departmental lines · show list ↓", () => {
        const on = fState.type !== k;
        fState.type = on ? k : "";
        if (on) fState.sev = 1;          // the tile counts every flag of this type, so the list must too
        fState.limit = 40; rebuild();
        jumpTo(listWrap);
      }, { "aria-pressed": String(fState.type === k) });
    }));
    const hf = D.hmrc.flags, hTiles = [["monthly_jump", "Unusual change in monthly tax receipts"], ["taxgap_revision", "Tax gap estimate later revised"]];
    hTiles.forEach(([k, t]) => tiles.append(tileBtn(t, hf.filter(f => f.type === k).length, "in HMRC statistics · jump to section ↓", () => jumpTo("hmrc-flags"))));
    tiles.append(tileBtn(D.ons.flag_types.ons_monthly_jump.title, D.ons.flags.length, "in ONS monthly series · jump to section ↓", () => jumpTo("ons-flags")));
    tiles.append(tileBtn("Benefit fraud and error flags (DWP)", D.dwp.flags.length, "high rates, old measurements · jump to section ↓", () => jumpTo("dwp-flags")));
    if (D.proc) tiles.append(tileBtn("Government contract flags (Contracts Finder, Find a Tender)", Object.values(D.proc.flag_counts).reduce((a, b) => a + b, 0), "direct awards, late notices · jump to section ↓", () => jumpTo("proc-summary")));
    tiles.append(tileBtn("Local council flags (England)", "see below", "spending, reserves, schools deficits · jump to section ↓", () => jumpTo("lc-flags-summary")));
    tiles.append(tileBtn("Unusual borrowing months", D.bor.flags.length, "year-on-year changes · jump to section ↓", () => jumpTo("bor-flags")));
    root.append(tiles);
    const listWrap = el("div", { id: "flag-list" });
    root.append(listWrap);
    rebuild();
    // priority list
    const pr = card("Priority review list", "Lines with several kinds of flag at once, weighted by severity. This is where a reader with limited time should start.",
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["#", "Line", "Department", "Largest amount", "Score", "Flags"].map((h, i) => el("th", { class: i === 3 || i === 4 ? "n" : "" }, h)))),
        el("tbody", {}, F.ranked.slice(0, 25).map((r, i) => el("tr", { class: "click", onclick: () => { fState.q = r.name; fState.type = ""; fState.sev = 1; fState.dept = ""; rebuild(); jumpTo(listWrap); } },
          el("td", {}, i + 1), el("td", {}, r.name), el("td", {}, r.dept), el("td", { class: "n" }, mm(r.max_m)), el("td", { class: "n" }, r.score), el("td", {}, r.types.map(t => F.types[t].title).join(", "))))))));
    root.append(pr);
    // function-level
    const fl = card("Unusual moves in whole functions", "Real-terms year-on-year changes that are extreme against that function's own history (Table 4.3). Many cluster in 2020-21 (Covid-19 response) and 2021-23 (debt interest on inflation-linked gilts).",
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Year", "What happened"].map(h => el("th", {}, h)))),
        el("tbody", {}, F.function_flags.slice(0, 15).map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, f.year), el("td", {}, f.detail)))))));
    fl.id = "fn-flags";
    root.append(fl);
    root.append(hmrcFlagsCard(), onsFlagsCard(), dwpFlagsCard(), ...(D.proc ? [procFlagsCard()] : []), borFlagsCard(), lcFlagsCard(), benfordCard(), opacityCard());
    return root;

    function rebuild() {
      listWrap.replaceChildren();
      const depts = [...new Set(F.flags.map(f => f.dept))].sort();
      const filtered = F.flags.filter(f => (!fState.type || f.type === fState.type) && f.sev >= fState.sev && (!fState.dept || f.dept === fState.dept) &&
        (!fState.q || (f.name + " " + f.dept + " " + f.code).toLowerCase().includes(fState.q.toLowerCase())));
      const ctl = el("div", { class: "controls" },
        select("fs", "Minimum severity", [["3", "High only"], ["2", "Medium and above"], ["1", "Everything"]], String(fState.sev), v => { fState.sev = +v; fState.limit = 40; rebuild(); }),
        select("fd", "Department", [["", "All departments"], ...depts.map(d => [d, d])], fState.dept, v => { fState.dept = v; fState.limit = 40; rebuild(); }),
        select("ft", "Type", [["", "All types"], ...Object.entries(F.types).filter(([k]) => k !== "function_jump").map(([k, t]) => [k, t.title])], fState.type, v => { fState.type = v; fState.limit = 40; rebuild(); }),
        el("label", {}, "Search", el("input", { type: "search", id: "fq", value: fState.q, placeholder: "line, department, code", oninput: e => { fState.q = e.target.value; fState.limit = 40; clearTimeout(rebuild.t); rebuild.t = setTimeout(() => { const release = holdView(); rebuild(); release(); }, 250); } })));
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

  const hState = { sev: 2, limit: 15 };
  function hmrcFlagsCard() {
    const H = D.hmrc, out = el("section", { class: "card", id: "hmrc-flags" });
    function paint() {
      const mj = H.flags.filter(f => f.type === "monthly_jump" && f.sev >= hState.sev), tg = H.flags.filter(f => f.type === "taxgap_revision");
      out.replaceChildren(el("h3", {}, "HMRC: unusual months and revised tax gap estimates"),
        el("p", { class: "sub" }, "Each tax's monthly receipts are compared with the same month a year earlier and scored against that tax's own history. A shock is reported once: the following year's rebound is treated as a base effect. Tax rises, tax cuts, payment-date timing and the pandemic are common innocent causes."),
        el("div", { class: "controls" }, select("hs", "Minimum severity", [["3", "High only"], ["2", "Medium and above"], ["1", "Everything"]], String(hState.sev), v => { hState.sev = +v; hState.limit = 15; paint(); })),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Month", "Tax", "Amount", "What happened"].map((h, i) => el("th", { class: i === 3 ? "n" : "" }, h)))),
          el("tbody", {}, mj.slice(0, hState.limit).map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, monLabel(f.month)), el("td", {}, cleanTax(f.tax)), el("td", { class: "n" }, mm(f.value)), el("td", {}, f.detail)))))),
        mj.length > hState.limit ? el("p", {}, el("button", { onclick: () => { hState.limit += 25; paint(); } }, `Show more (${mj.length - hState.limit} left)`)) : null,
        el("h3", { style: "margin-top:16px" }, "Tax gap years whose estimate moved by 1 percentage point or more"),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Year", "What happened"].map(h => el("th", {}, h)))),
          el("tbody", {}, tg.map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, f.year), el("td", {}, f.detail)))))),
        el("p", { class: "small" }, "Older years' estimates mostly moved down as HMRC changed its methods; recent years' first estimates have mostly moved up."));
    }
    paint();
    return out;
  }

  function dwpFlagsCard() {
    const T = D.dwp.flag_types, fl = D.dwp.flags;
    return el("section", { class: "card", id: "dwp-flags" }, el("h3", {}, "DWP: benefit fraud and error"),
      el("p", { class: "sub" }, "Three screens on DWP's estimates: benefits with a high overpayment rate, benefits whose rate was last measured more than three years ago (or never), and past estimates that were later restated. See the Benefit fraud & error page for the charts."),
      el("ul", { class: "tight small" }, Object.values(T).map(t => el("li", {}, el("b", {}, t.title + ": "), t.text))),
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Test", "Benefit", "Year", "What the data say"].map(h => el("th", {}, h)))),
        el("tbody", {}, fl.map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, T[f.type].title), el("td", {}, f.benefit), el("td", {}, f.year), el("td", {}, f.detail)))))));
  }

  function procFlagsCard() {
    const P = D.proc, top = P.flags.filter(f => f.sev === 3).slice(0, 12);
    return el("section", { class: "card", id: "proc-summary" }, el("h3", {}, "Government contracts: the most serious flags"),
      el("p", { class: "sub" }, "Screens on public award notices: large awards without competition, notices published long after the award, awards far from the advertised value, repeat awards to one supplier, and buyers that rarely say how they bought. They are prompts to look closer. The full list, with filters, is on the "),
      el("p", {}, el("a", { href: "#/procurement" }, "Contracts page →")),
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Test", "Buyer", "Value", "What the notice shows"].map((h, i) => el("th", { class: i === 3 ? "n" : "" }, h)))),
        el("tbody", {}, top.map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, P.types[f.type].title), el("td", {}, f.buyer), el("td", { class: "n" }, f.value_fmt), el("td", {}, f.detail)))))));
  }

  function lcFlagsCard() {
    const box = el("section", { class: "card", id: "lc-flags-summary" }, el("h3", {}, "Local councils: unusual spending and finances"), el("p", { class: "sub" }, "Loading…"));
    (D.lc ? Promise.resolve(D.lc) : loadJSON("councils").then(d => (D.lc = d))).then(L => {
      const hi = L.flags.filter(f => f.sev === 3).slice(0, 10);
      box.replaceChildren(el("h3", {}, "Local councils: unusual spending and finances"),
        el("p", { class: "sub" }, `${L.flags.length} flags across English councils (${L.flags.filter(f => f.sev === 3).length} high). Councils are compared with councils that do the same job, after allowing for population. The ten largest high-severity ones are below; the Local councils page has all of them, with filters and council profiles.`),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Year", "Kind", "What the data show"].map(h => el("th", {}, h)))),
          el("tbody", {}, hi.map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, f.year), el("td", {}, L.flag_types[f.type].title), el("td", {}, f.detail)))))),
        el("p", {}, el("a", { href: "#/councils" }, "See all council flags →")));
    }, () => box.replaceChildren(el("p", { class: "sub" }, "Council data could not be loaded.")));
    return box;
  }

  function borFlagsCard() {
    const fl = D.bor.flags;
    return el("section", { class: "card", id: "bor-flags" }, el("h3", {}, "Borrowing: unusual months (since 2015)"),
      el("p", { class: "sub" }, D.bor.flag_types.borrowing_jump.text + " A shock is reported once; the rebound a year later is treated as a base effect. See the Borrowing & debt page for the charts."),
      el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Month", "Borrowing", "What happened"].map((h, i) => el("th", { class: i === 2 ? "n" : "" }, h)))),
        el("tbody", {}, fl.map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, monLabel(f.month)), el("td", { class: "n" }, mm(f.value)), el("td", {}, f.detail)))))));
  }

  const oState = { sev: 2, limit: 15 };
  function onsFlagsCard() {
    const out = el("section", { class: "card", id: "ons-flags" });
    function paint() {
      const fl = D.ons.flags.filter(f => f.sev >= oState.sev);
      out.replaceChildren(el("h3", {}, "ONS: unusual months in the public finances (since 2015)"),
        el("p", { class: "sub" }, D.ons.flag_types.ons_monthly_jump.text + " Scores use each series' full history since 1997; a shock is reported once, and the rebound a year later is treated as a base effect. Net borrowing and net investment are not screened because they swing around zero."),
        el("div", { class: "controls" }, select("os", "Minimum severity", [["3", "High only"], ["2", "Medium and above"], ["1", "Everything"]], String(oState.sev), v => { oState.sev = +v; oState.limit = 15; paint(); })),
        el("div", { class: "tablewrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Severity", "Month", "Series", "Amount", "What happened"].map((h, i) => el("th", { class: i === 3 ? "n" : "" }, h)))),
          el("tbody", {}, fl.slice(0, oState.limit).map(f => el("tr", {}, el("td", {}, sevBadge(f.sev)), el("td", {}, monLabel(f.month)), el("td", {}, f.tax), el("td", { class: "n" }, mm(f.value)), el("td", {}, f.detail)))))),
        fl.length > oState.limit ? el("p", {}, el("button", { onclick: () => { oState.limit += 25; paint(); } }, `Show more (${fl.length - oState.limit} left)`)) : null,
        el("p", { class: "small" }, "In 2020-23 most of these are the pandemic support schemes (furlough was paid as subsidies) and the energy-price support."));
    }
    paint();
    return out;
  }

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
      el("p", { class: "lede" }, "The Treasury, HMRC and the ONS publish overlapping totals in several tables. These checks recompute sums and compare tables against each other. A gap is not proof of error (rounding, timing and revisions all matter) but it is exactly what a careful reader would want pointed out."));
    root.append(el("div", { class: "kpis" }, kpi("Pass", String(C.filter(c => c.status === "pass").length), "agree within rounding"), kpi("Discrepancy", String(C.filter(c => c.status === "warn").length), "outside rounding tolerance"), kpi("Documented gap", String(C.filter(c => c.status === "info").length), "explained in the source notes")));
    let lastSource = null;
    C.forEach(c => {
      if (c.source !== lastSource) { lastSource = c.source; root.append(el("h3", { style: "margin:20px 0 8px" }, { "HMRC": "HMRC tables", "DWP": "DWP benefit fraud and error tables", "Contracts Finder": "Government contracts (Contracts Finder)", "Borrowing": "Borrowing and gilts (ONS, Debt Management Office)", "ONS": "ONS public sector finances (and agreement with the Treasury)" }[lastSource] || "HM Treasury tables")); }
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
    const P = D.flags.params, T = D.flags.types, T_ = D.hmrc.flag_types;
    const root = el("div", {}, el("h2", {}, "Method & sources"));
    root.append(card("Sources (and only these)", "Every number comes from an official source: HM Treasury (Public Spending Statistics and PESA), HMRC (tax receipts and tax gap statistics) and DWP (fraud and error in the benefit system), all on GOV.UK; the ONS Public Sector Finances dataset; the Cabinet Office's Contracts Finder (award notices); and, for who lends to government and at what price, the Debt Management Office and the Bank of England.",
      el("ul", { class: "tight" }, D.meta.collections.map(u => el("li", {}, el("a", { href: u, rel: "noopener" }, u)))),
      el("p", { class: "small" }, "Files used (all downloaded and processed by pipeline/build.py in the project, so anyone can reproduce the data):"),
      el("div", { class: "tablewrap" }, el("table", {}, el("tbody", {}, D.meta.files.map(f => el("tr", {}, el("td", {}, f.publisher), el("td", {}, f.release), el("td", {}, f.title), el("td", {}, el("a", { href: f.url, rel: "noopener" }, f.api ? "API" : "download")))))))));
    root.append(card("What the site can and cannot tell you", null, el("ul", { class: "tight" },
      el("li", {}, el("b", {}, "Spending is annual. "), "The Treasury publishes financial-year outturn. Monthly figures come from the ONS (spending, receipts, borrowing, debt) and HMRC (tax receipts). ONS monthly figures are not seasonally adjusted and are revised; the latest months are provisional. ONS does not publish earlier versions of the dataset, so how much each month was later revised cannot be tested."),
      el("li", {}, el("b", {}, "Borrowing sign. "), "ONS publishes net borrowing as a negative number; the site shows borrowing as positive. The Treasury's totals are built on ONS data, so the two agree almost exactly in older years; that is not an independent test."),
      el("li", {}, el("b", {}, "Tax gap is an estimate. "), "HMRC builds it from sampling, models and assumptions; it is not a count of detected fraud, and recent years are routinely revised."),
      el("li", {}, el("b", {}, "Aggregate, not transactions. "), "The most detailed level is about 1,600 departmental spending lines per year. Individual payments, contracts and benefit claims are not in these sources, so the site cannot detect an individual fraud. The nearest things to a fraud measure are HMRC's tax gap by behaviour (evasion, criminal attacks, error…) and DWP's estimates of fraud and error in benefits. Both are statistical estimates from samples, not counts of proven cases."),
      el("li", {}, el("b", {}, "Contracts are notices, not payments. "), "Contracts Finder and Find a Tender hold award notices published by buyers; the two services overlap very little. Notices on Find a Tender that say “outside the scope” of the procurement rules, or that name a framework, are treated as call-offs or other, not as direct awards. A contract's value is its lifetime value, many contracts never appear, and the notices do not state how many bidders there were, so \"single bidder\" cannot be tested. Suppliers are named only when they are recognisably organisations."),
      el("li", {}, el("b", {}, "Benefit estimates are for Great Britain, "), "not the UK, and some benefits are measured only every few years, so part of the headline is carried forward from earlier measurements. DWP also reclassified some underpayments from 2022-23 and changed methods in places, which limits comparison across years."),
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
        trow(T_.monthly_jump.title, "Same method as the spending-line jump test, applied to each tax's receipts compared with the same month a year earlier (median/MAD score against that tax's own history). A shock is reported once; a rebound twelve months later is treated as a base effect.", "score ≥ 4; change ≥ £300m a month"),
        trow(D.ons.flag_types.ons_monthly_jump.title, "The HMRC monthly method applied to ONS spending, receipt and debt-interest series from 2015, scored against each series' history since 1997.", "score ≥ 4; change ≥ £300m a month"),
        trow(D.dwp.flag_types.dwp_rate.title, "Benefits with at least £1bn of spending whose overpayment rate (fraud plus both kinds of error) is 3% or more; severity rises at 5% and 8%.", "≥ 3% of spending"),
        trow(D.dwp.flag_types.dwp_stale.title, "Benefits with at least £1bn of spending whose fraud and error rate was last measured more than three years before the end of the period, plus spending that has never been reviewed.", "> 36 months; ≥ £1bn"),
        trow(D.dwp.flag_types.dwp_revision.title, "The same year's DWP estimate is compared across the FYE 2024, 2025 and 2026 releases. A change is flagged when it is at least £100m and 1%, and more seriously when the new figure falls outside the earlier confidence interval.", "≥ £100m and ≥ 1%"),
        ...Object.entries(D.proc ? D.proc.types : {}).map(([k, t]) => trow(t.title, t.text + " " + ({
          proc_direct: "Awards classed as direct award, single tender action, waiver or negotiation without publication, from £0.25m (severity rises at £1m and £5m).",
          proc_late: "Award notice published at least 90 days after the award date, for awards of £0.1m or more.",
          proc_estimate: "Award at least 2× the advertised estimate (or under a tenth of it), for contracts of £0.25m or more.",
          proc_long: "Contract term over 10 years, for awards of £1m or more.",
          proc_split: "Three or more non-framework awards to the same supplier by the same buyer within 90 days, together £0.15m or more.",
          proc_conc: "A buyer with at least 20 awards and £5m of awards where one supplier received 40% or more of the value.",
          proc_implausible: "A single award of £10bn or more; excluded from totals and shown as a data-entry error.",
          proc_unspec: "A buyer with at least 20 awards where 40% or more do not state the procedure used.",
        }[k] || ""), "see description")),
        trow("Pile-up below round values", "For each round-number value, awards in the 5% band just below are compared with the 5% band just above (equal widths on a log scale); a binomial z-score of 3 or more with at least 30 awards below is flagged.", "z ≥ 3; ≥ 30 awards"),
        trow(D.bor.flag_types.borrowing_jump.title, "Year-on-year change in each month's net borrowing (in £, because borrowing crosses zero) scored against its own history since 1997; a shock is reported once, with the rebound a year later treated as a base effect.", "score ≥ 4; change ≥ £3bn"),
        ...["lc_outlier|After allowing for residents (or children, or people aged 65+), a service costs far more or less than the median council of the same kind (districts, counties, or unitary/metropolitan/London). Robust score against the peer group.|score ≥ 3.5; spending ≥ £10m (£3m districts); severity rises at 4.5 and 6",
          "lc_jump|Year-on-year change in a council's total service spending compared with the change at councils of its kind over the last four years.|score ≥ 4 and ≥ 15 points from typical",
          "lc_reserves|Unallocated plus earmarked reserves (excluding schools and public health) below 10% of net revenue spending.|< 10% (severity rises below 5% and at zero)",
          "lc_dsg|A negative Dedicated Schools Grant reserve of at least £5m and 3% of net revenue spending.|≥ 3% (severity rises at 15% and 30%)",
          "lc_interest|Net interest paid at least 10% of net revenue spending.|≥ 10% (rises at 15% and 25%)",
          "lc_invest|Commercial investment properties whose carrying cost exceeds their income by £1m or more.|≥ £1m",
          "lc_missing|No revenue outturn return for a recent year when at least 90% of councils submitted.|2021-22 onward"].map(x => { const [k, h, t] = x.split("|"); return trow((D.lc ? D.lc.flag_types[k].title : ({ lc_outlier: "Council spend far from similar councils", lc_jump: "Council: sudden change in spending", lc_reserves: "Council: thin reserves", lc_dsg: "Council: schools funding deficit", lc_interest: "Council: heavy debt-servicing cost", lc_invest: "Council: investment properties costing more than they earn", lc_missing: "Council: accounts not submitted" })[k]), h, t); }),
        trow("What it buys: spending against results", "Council spending lines are joined by ONS area code to a result from another department (Defra waste, DfT road condition). Councils are compared only with similar councils; Spearman rank correlation is reported with a 95% range, then repeated after removing the linear effect of deprivation (IoD2025 average score), and for roads also people per km of road. Councils far from the pattern once need is allowed for are listed.", "≥ 12 councils; outliers beyond 0.5 standard deviations on both"),
        trow(T_.taxgap_revision.title, "HMRC re-estimates earlier years in each annual edition. The first estimate for each year is compared with the latest.", "revision ≥ 1.0 percentage point"),
        trow("Table cross-checks", "Recomputes totals (functions → services → TME, regions → nations → UK; HMRC's taxes → total receipts, tax gap components → total) and compares the same total across tables and real-vs-cash deflators.", "rounding tolerance of the table"),
      )))));
    root.append(card("ONS series used", "Official ONS titles, so you can look each one up by its four-letter code (CDID) on ons.gov.uk.",
      el("details", { class: "tbl" }, el("summary", {}, `Show all ${D.ons.series.length} series`), el("div", { class: "tablewrap" }, el("table", {}, el("tbody", {}, D.ons.series.map(x => el("tr", {}, el("td", {}, el("code", {}, x.cdid)), el("td", {}, x.title), el("td", {}, x.sign < 0 ? "shown with sign reversed" : ""))))))))); 
    root.append(card("Priority score", null, el("p", { class: "small" }, "Per spending line: Low = 1 point, Medium = 3, High = 6, summed over all its flags, plus 2 for each additional kind of flag. Lines are ranked by score, then size. It is deliberately simple so anyone can reproduce it.")));
    root.append(card("Reproduce it", null, el("p", { class: "small" }, "Run "), el("pre", { style: "overflow:auto" }, "python3 pipeline/build.py\npython3 -m unittest discover -s pipeline/tests")));
    return root;
    function trow(a, b, c) { return el("tr", {}, el("td", { style: "min-width:150px;font-weight:600" }, a), el("td", {}, b), el("td", { style: "min-width:150px" }, c)); }
  };

  /* ------------------------------------------------------------ theme */
  (function theme() {
    const btn = document.getElementById("themebtn"), lab = document.getElementById("themelabel"), modes = ["auto", "light", "dark"];
    let mode = "auto";
    try { mode = modes.includes(localStorage.getItem("theme")) ? localStorage.getItem("theme") : "auto"; } catch (e) { /* storage blocked: stay on auto */ }
    const apply = () => {
      if (mode === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", mode);
      lab.textContent = { auto: "Auto", light: "Light", dark: "Dark" }[mode];
      btn.setAttribute("aria-label", `Colour theme: ${mode === "auto" ? "automatic (follows your device)" : mode}. Press to change.`);
    };
    btn.addEventListener("click", () => { mode = modes[(modes.indexOf(mode) + 1) % 3]; try { localStorage.setItem("theme", mode); } catch (e) { /* ignore */ } apply(); draws.forEach(f => f()); });
    apply();
  })();

  /* --------------------------------------------------------------- boot */
  /* Fetch one data file, retrying transient failures, and say exactly what went wrong if it still fails. */
  async function loadJSON(name, optional = false) {
    let last;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const r = await fetch(`data/${name}.json`, { cache: "no-cache" });
        if (r.status === 404 && optional) return null;     // an optional dataset that has not been built yet
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return await r.json();
      } catch (e) {
        last = e;
        await new Promise(res => setTimeout(res, 400 * (attempt + 1)));
      }
    }
    throw new Error(`data/${name}.json: ${last && last.message ? last.message : last}`);
  }

  async function boot() {
    const names = ["meta", "aggregates", "functions", "regions", "departments", "segments", "flags", "checks", "hmrc", "ons", "dwp", "procurement", "borrowing"];
    const OPTIONAL = new Set(["procurement"]);   // only requested when meta.json says it was built
    try {
      D.meta = await loadJSON("meta");
      const res = await Promise.all(names.slice(1).map(n => (OPTIONAL.has(n) && !D.meta.has_procurement) ? null : loadJSON(n, OPTIONAL.has(n))));
      [D.agg, D.fn, D.reg, D.dept, D.segments, D.flags, D.checks, D.hmrc, D.ons, D.dwp, D.proc, D.bor] = res;
    } catch (e) {
      const hint = location.protocol === "file:"
        ? "You opened index.html directly from disk. Serve the folder instead, for example: python3 -m http.server -d site"
        : "This is usually a temporary network problem, an ad or content blocker, or a stale cached copy. Try again, or hard-refresh (Ctrl+Shift+R).";
      main.replaceChildren(el("div", { class: "notice" }, el("b", {}, "Could not load the data. "), `Failed on ${e.message}. `, hint, " ",
        el("button", { onclick: () => location.reload() }, "Try again")));
      return;
    }
    if (!D.proc) { const i = ROUTES.findIndex(r => r[0] === "procurement"); if (i >= 0) ROUTES.splice(i, 1); }   // Contracts page only when its data exists
    document.getElementById("foot-meta").textContent = `Data: HM Treasury ${D.meta.latest_release} (plus July 2024 and 2025 releases for revision checks), HMRC receipts and tax gap statistics, DWP fraud and error statistics (${D.dwp.release.replace(/ \(.*/, "")}), ONS public sector finances (${D.ons.release}), and Debt Management Office and Bank of England gilt data. Processed ${D.meta.generated}.`;
    route();
  }
  boot();
})();
