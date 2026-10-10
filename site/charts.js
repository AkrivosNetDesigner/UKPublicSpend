/* Tiny dependency-free SVG chart helpers: line, stacked bars, horizontal bars.
 * Colours come from CSS variables (--s1..--s8) so light/dark follow the theme. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"];
  const OTHER = "var(--other)";
  const tip = () => document.getElementById("tip");

  function svg(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function html(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) {
      if (k === "class") e.className = attrs[k];
      else if (k === "style") e.style.cssText = attrs[k];
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    }
    for (const kid of kids.flat()) if (kid != null) e.append(kid.nodeType ? kid : document.createTextNode(kid));
    return e;
  }

  function niceTicks(min, max, n = 5) {
    if (min === max) { max = min + 1; }
    const span = max - min, raw = span / n;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
    const t = [];
    for (let v = lo; v <= hi + step / 2; v += step) t.push(+v.toPrecision(12));
    return t;
  }

  function showTip(ev, content) {
    const t = tip();
    t.replaceChildren(content);
    t.hidden = false;
    const pad = 14, w = t.offsetWidth, h = t.offsetHeight;
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + w > innerWidth - 8) x = ev.clientX - w - pad;
    if (y + h > innerHeight - 8) y = ev.clientY - h - pad;
    t.style.left = Math.max(8, x) + "px";
    t.style.top = Math.max(8, y) + "px";
  }
  function hideTip() { tip().hidden = true; }

  function legend(series, onToggle) {
    if (series.length < 2) return null;
    return html("div", { class: "legend" }, series.map(s =>
      html("span", {}, html("i", { class: "sw", style: `background:${s.color}` }), s.name)));
  }

  function tableView(x, series, fmt, xlabel = "") {
    const d = html("details", { class: "tbl" }, html("summary", {}, "View as table"));
    const head = html("tr", {}, html("th", {}, xlabel || ""), series.map(s => html("th", { class: "n" }, s.name)));
    const body = x.map((lab, i) => html("tr", {}, html("td", {}, lab),
      series.map(s => html("td", { class: "n" }, s.values[i] == null ? "–" : fmt(s.values[i])))));
    d.append(html("div", { class: "tablewrap" }, html("table", {}, html("thead", {}, head), html("tbody", {}, body))));
    return d;
  }

  /* indexes of x labels to show: every `step`, plus the last one if it will not collide */
  function labelIdx(n, room, per) {
    const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(room / per))));
    const out = [];
    for (let i = 0; i < n; i += step) out.push(i);
    const last = out[out.length - 1];
    if (last !== n - 1) { if (n - 1 - last >= step * 0.75) out.push(n - 1); else out[out.length - 1] = n - 1; }
    return out;
  }

  /* horizontal room one x label needs: at least `min`, more for long labels like "Apr 2017" */
  function perLabel(x, min) {
    const longest = x.reduce((a, l) => Math.max(a, String(l).length), 0);
    return Math.max(min, longest * 6.6 + 22);
  }

  function sizeOf(el, h) { return { W: Math.max(300, el.clientWidth || 640), H: h }; }

  /* ------------------------------------------------------------- line */
  function lineChart(el, o) {
    el.replaceChildren();
    const series = o.series.map((s, i) => ({ color: SERIES[i % 8], ...s }));
    const { W, H } = sizeOf(el, o.height || 300);
    const m = { l: 58, r: 14, t: 10, b: 26 };
    const all = series.flatMap(s => s.values).filter(v => v != null && isFinite(v));
    if (!all.length) { el.append(html("p", { class: "sub" }, "No data for this selection.")); return; }
    let lo = Math.min(...all), hi = Math.max(...all);
    if (o.zero !== false && lo > 0) lo = 0;
    if (hi < 0) hi = 0;
    const ticks = niceTicks(lo, hi, 5);
    lo = ticks[0]; hi = ticks[ticks.length - 1];
    const n = o.x.length;
    const X = i => m.l + (n === 1 ? 0.5 : i / (n - 1)) * (W - m.l - m.r);
    const Y = v => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    { const lg = legend(series); if (lg) el.append(lg); }
    const s = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.title || "Line chart" }, el);
    const g = svg("g", { class: "grid" }, s);
    ticks.forEach(t => {
      svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), ...(t === 0 ? { class: "axis" } : {}) }, g);
      const tx = svg("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, s); tx.textContent = o.axisFmt ? o.axisFmt(t) : o.fmt(t);
    });
    if (o.zero === false || lo < 0) { /* zero line already drawn via ticks */ }
    labelIdx(n, W - m.l - m.r, perLabel(o.x, 62)).forEach(i => {
      const tx = svg("text", { x: X(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" }, s);
      tx.textContent = o.x[i];
    });
    (o.bands || []).forEach(b => { /* highlighted x positions */
      const i = o.x.indexOf(b.x); if (i < 0) return;
      svg("rect", { x: X(i) - 8, y: m.t, width: 16, height: H - m.t - m.b, fill: "var(--grid)", opacity: .55 }, s);
    });
    series.forEach(se => {
      let d = "", pen = false;
      se.values.forEach((v, i) => {
        if (v == null || !isFinite(v)) { pen = false; return; }
        d += (pen ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1); pen = true;
      });
      svg("path", { d, fill: "none", stroke: se.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
        ...(se.dash ? { "stroke-dasharray": "5 4" } : {}) }, s);
      if (n <= 12) se.values.forEach((v, i) => v != null && svg("circle", { cx: X(i), cy: Y(v), r: 3, fill: se.color, stroke: "var(--surface)", "stroke-width": 2 }, s));
    });
    const guide = svg("line", { y1: m.t, y2: H - m.b, stroke: "var(--ink2)", "stroke-width": 1, opacity: 0 }, s);
    const dots = series.map(se => svg("circle", { r: 4.5, fill: se.color, stroke: "var(--surface)", "stroke-width": 2, opacity: 0 }, s));
    const hit = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, s);
    const move = ev => {
      const r = s.getBoundingClientRect(), px = (ev.clientX - r.left) * (W / r.width);
      const i = Math.max(0, Math.min(n - 1, Math.round((px - m.l) / (W - m.l - m.r) * (n - 1))));
      guide.setAttribute("x1", X(i)); guide.setAttribute("x2", X(i)); guide.setAttribute("opacity", .5);
      const rows = [];
      series.forEach((se, k) => {
        const v = se.values[i];
        dots[k].setAttribute("opacity", v == null ? 0 : 1);
        if (v != null) { dots[k].setAttribute("cx", X(i)); dots[k].setAttribute("cy", Y(v)); rows.push([se, v]); }
      });
      rows.sort((a, b) => b[1] - a[1]);
      showTip(ev, html("div", {}, html("b", {}, o.x[i]), rows.slice(0, 12).map(([se, v]) =>
        html("div", { class: "r" }, html("span", {}, html("i", { class: "sw", style: `background:${se.color}` }), se.name), html("span", { class: "mono" }, o.fmt(v))))));
    };
    hit.addEventListener("mousemove", move);
    hit.addEventListener("touchstart", e => move(e.touches[0]), { passive: true });
    hit.addEventListener("touchmove", e => move(e.touches[0]), { passive: true });
    hit.addEventListener("mouseleave", () => { hideTip(); guide.setAttribute("opacity", 0); dots.forEach(d => d.setAttribute("opacity", 0)); });
    el.append(tableView(o.x, series, o.fmt, o.xlabel));
  }

  /* ----------------------------------------------------- stacked bars */
  function stackedBars(el, o) {
    el.replaceChildren();
    const series = o.series.map((s, i) => ({ color: s.name === "Other" ? OTHER : SERIES[i % 8], ...s }));
    const { W, H } = sizeOf(el, o.height || 320);
    const m = { l: 58, r: 10, t: 10, b: 26 };
    const n = o.x.length;
    const pos = o.x.map((_, i) => series.reduce((a, s) => a + Math.max(0, s.values[i] || 0), 0));
    const neg = o.x.map((_, i) => series.reduce((a, s) => a + Math.min(0, s.values[i] || 0), 0));
    const ticks = niceTicks(Math.min(0, ...neg), Math.max(...pos), 5);
    const lo = ticks[0], hi = ticks[ticks.length - 1];
    const Y = v => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    const bw = (W - m.l - m.r) / n, w = Math.max(3, bw * 0.72);
    { const lg = legend(series); if (lg) el.append(lg); }
    const s = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.title || "Stacked bar chart" }, el);
    const g = svg("g", { class: "grid" }, s);
    ticks.forEach(t => {
      svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), ...(t === 0 ? { class: "axis" } : {}) }, g);
      const tx = svg("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, s); tx.textContent = o.axisFmt ? o.axisFmt(t) : o.fmt(t);
    });
    labelIdx(n, W - m.l - m.r, perLabel(o.x, 56)).forEach(i => {
      const tx = svg("text", { x: m.l + bw * i + bw / 2, y: H - 6, "text-anchor": i === n - 1 ? "end" : "middle" }, s);
      tx.textContent = o.x[i];
    });
    o.x.forEach((lab, i) => {
      let up = 0, down = 0;
      const x = m.l + bw * i + (bw - w) / 2;
      const col = svg("g", {}, s);
      series.forEach(se => {
        const v = se.values[i] || 0; if (!v) return;
        const y0 = v > 0 ? up : down, y1 = y0 + v;
        if (v > 0) up = y1; else down = y1;
        const top = Math.min(Y(y0), Y(y1)), h = Math.abs(Y(y0) - Y(y1));
        if (h < 0.4) return;
        svg("rect", { x, y: top + 1, width: w, height: Math.max(0.5, h - 2), fill: se.color, rx: h > 6 ? 2 : 0 }, col);
      });
      const hit = svg("rect", { x: m.l + bw * i, y: m.t, width: bw, height: H - m.t - m.b, fill: "transparent" }, col);
      hit.addEventListener("mousemove", ev => {
        const total = series.reduce((a, se) => a + (se.values[i] || 0), 0);
        showTip(ev, html("div", {}, html("b", {}, lab), series.slice().sort((a, b) => (b.values[i] || 0) - (a.values[i] || 0)).map(se =>
          html("div", { class: "r" }, html("span", {}, html("i", { class: "sw", style: `background:${se.color}` }), se.name), html("span", { class: "mono" }, o.fmt(se.values[i] || 0)))),
          o.noTotal ? null : html("div", { class: "r", style: "border-top:1px solid var(--grid);margin-top:4px;padding-top:4px" }, html("b", {}, "Total"), html("b", { class: "mono" }, o.fmt(total)))));
      });
      hit.addEventListener("mouseleave", hideTip);
    });
    el.append(tableView(o.x, series, o.fmt, o.xlabel));
  }

  /* ------------------------------------------------- horizontal bars */
  function barChart(el, o) {
    el.replaceChildren();
    const items = o.items;
    if (!items.length) { el.append(html("p", { class: "sub" }, "No data for this selection.")); return; }
    const W = Math.max(300, el.clientWidth || 640);
    const narrow = W < 400;
    const labW = W < 380 ? 110 : W < 520 ? 150 : 210, rowH = 26, m = { l: labW + 8, r: 84, t: 4, b: 22 };
    const H = m.t + m.b + rowH * items.length;
    const vals = items.map(i => i.value);
    const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const x0 = m.l + (lo < 0 ? 78 : 0);   /* room for value labels of negative bars */
    const X = v => x0 + (v - lo) / ((hi - lo) || 1) * (W - m.r - x0);
    const s = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.title || "Bar chart" }, el);
    const g = svg("g", { class: "grid" }, s);
    niceTicks(lo, hi, narrow ? 3 : 5).forEach(t => {
      if (t < lo - 1e-9 || t > hi + 1e-9) return;
      svg("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, ...(t === 0 ? { class: "axis" } : {}) }, g);
      const tx = svg("text", { x: X(t), y: H - 6, "text-anchor": "middle" }, s); tx.textContent = o.axisFmt ? o.axisFmt(t) : o.fmt(t);
    });
    items.forEach((it, i) => {
      const y = m.t + rowH * i;
      const lab = svg("text", { x: labW, y: y + rowH / 2 + 4, "text-anchor": "end", class: "lbl" }, s);
      const max = Math.floor(labW / 6.1);
      lab.textContent = it.label.length > max ? it.label.slice(0, max - 1) + "…" : it.label;
      const x0 = X(0), x1 = X(it.value);
      svg("rect", { x: Math.min(x0, x1), y: y + 4, width: Math.max(1, Math.abs(x1 - x0)), height: rowH - 9, rx: 3,
        fill: it.color || (it.value < 0 && o.diverging ? "var(--s2)" : "var(--s1)") }, s);
      const vt = svg("text", { x: it.value >= 0 ? x1 + 5 : x1 - 5, y: y + rowH / 2 + 4, "text-anchor": it.value >= 0 ? "start" : "end", class: "lbl" }, s);
      vt.textContent = o.valueFmt ? o.valueFmt(it) : o.fmt(it.value);
      const hit = svg("rect", { x: 0, y, width: W, height: rowH, fill: "transparent" }, s);
      hit.addEventListener("mousemove", ev => showTip(ev, html("div", {}, html("b", {}, it.label), html("div", { class: "mono" }, o.tipFmt ? o.tipFmt(it) : o.fmt(it.value)))));
      hit.addEventListener("mouseleave", hideTip);
    });
    if (o.table !== false) {
      const d = html("details", { class: "tbl" }, html("summary", {}, "View as table"));
      d.append(html("div", { class: "tablewrap" }, html("table", {}, html("tbody", {}, items.map(it =>
        html("tr", {}, html("td", {}, it.label), html("td", { class: "n" }, o.tipFmt ? o.tipFmt(it) : o.fmt(it.value))))))));
      el.append(d);
    }
  }

  function spark(values, w = 90, h = 22, color = "var(--s1)") {
    const v = values.filter(x => x != null);
    const lo = Math.min(...v), hi = Math.max(...v);
    const s = svg("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, "aria-hidden": "true" });
    let d = ""; const n = values.length;
    values.forEach((x, i) => { if (x == null) return; const X = i / (n - 1 || 1) * (w - 4) + 2, Y = h - 2 - ((x - lo) / ((hi - lo) || 1)) * (h - 4); d += (d ? "L" : "M") + X.toFixed(1) + " " + Y.toFixed(1); });
    svg("path", { d, fill: "none", stroke: color, "stroke-width": 1.6 }, s);
    return s;
  }

  window.Charts = { lineChart, stackedBars, barChart, spark, html, svg, SERIES, OTHER, hideTip };
})();
