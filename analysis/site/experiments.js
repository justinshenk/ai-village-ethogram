"use strict";
/* =====================================================================
   EXPERIMENTS — quasi-experiments on past scaffolding changes, and power
   for proposed experiments. Exposes window.initExperiments(root).
   Fetches experiments.json. Uses page globals: $, $$, css, esc, nf, pct,
   onThemeChange, isDark, fetchJSON.
   ===================================================================== */
(function () {
  let EX = null;
  const st = { series: {}, sortKey: "sd4", sortDir: 1, open: null, tables: {} };

  const STYLE = `
  .ex-cards { display: grid; gap: 16px; }
  .ex-card .ex-top { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: baseline; padding: 12px 14px 0; }
  .ex-card h2 { font-size: 15px; margin: 0; font-weight: 600; }
  .ex-date { font-family: var(--f-data); font-size: 11.5px; color: var(--muted); }
  .ex-pill { font-size: 11.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--ink); color: var(--ink); white-space: nowrap; }
  .ex-pill.solid { background: var(--ink); color: var(--surface); }
  .ex-pill.muted { border-color: var(--line); color: var(--muted); }
  .ex-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 4px 20px; padding: 6px 14px 12px; }
  @media (max-width: 900px) { .ex-body { grid-template-columns: minmax(0, 1fr); } }
  .ex-body p { margin: 4px 0; font-size: 13px; color: var(--ink-2); max-width: 70ch; }
  .ex-k { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-top: 8px; display: block; }
  .ex-verdict { font-size: 13.5px; color: var(--ink); font-weight: 500; margin: 6px 0 2px; max-width: 75ch; }
  .ex-body ul { margin: 2px 0 0; padding-left: 18px; font-size: 12.5px; color: var(--ink-2); }
  .ex-body li { margin: 2px 0; }
  .ex-out { display: grid; gap: 2px; }
  .ex-row { display: grid; grid-template-columns: minmax(0, 1fr) 160px; gap: 8px; align-items: center; padding: 4px 0; border-bottom: 1px solid var(--line); }
  .ex-row:last-child { border-bottom: 0; }
  .ex-row .ex-name { font-size: 12.5px; color: var(--ink-2); min-width: 0; }
  .ex-row .ex-num { font-family: var(--f-data); font-size: 11.5px; color: var(--ink); }
  .ex-row .ex-sub { font-family: var(--f-data); font-size: 10.5px; color: var(--muted); }
  .ex-row svg { display: block; width: 160px; height: 26px; }
  .ex-chartbar { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0 2px; }
  .ex-chartbar button { font-size: 12px; padding: 2px 8px; }
  .ex-chart svg { display: block; width: 100%; height: auto; }
  .ex-foot { display: flex; justify-content: flex-end; padding: 0 14px 10px; }
  .ex-prop-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 16px; }
  @media (max-width: 900px) { .ex-prop-grid { grid-template-columns: minmax(0, 1fr); } }
  .ex-table tr[data-k] { cursor: pointer; }
  .ex-table tr[aria-selected="true"] td { background: var(--surface-2); }
  .ex-table td.ex-l, .ex-table th.ex-l { text-align: left; white-space: normal; }
  .ex-detail { padding: 12px 14px 14px; display: grid; gap: 6px; }
  .ex-detail h3 { margin: 0; font-size: 15px; font-weight: 600; }
  .ex-detail p { margin: 0; font-size: 13px; color: var(--ink-2); max-width: 70ch; }
  .ex-detail a { color: var(--ink); font-weight: 600; }
  `;

  window.initExperiments = async function (root) {
    if (!document.getElementById("ex-style")) { const s = document.createElement("style"); s.id = "ex-style"; s.textContent = STYLE; document.head.appendChild(s); }
    try { EX = EX || await fetchJSON("experiments.json"); } catch (e) { root.innerHTML = `<div class="panel pending">The experiments data didn't load (${esc(e.message)}). Reload to try again.</div>`; return; }
    root.innerHTML = `
      <p class="lede" style="margin:0 0 12px">Two kinds of evidence about the village's scaffolding. First, natural experiments: changes the operators already made, analysed with designs that separate the change from everything else happening that week. Second, experiments that could be run, with the smallest effect each design could reliably detect given how noisy the village's own data is.</p>
      <div class="panel" style="margin-bottom:16px"><div class="card-h"><h2>How to read this</h2></div>
        <div class="notes" style="margin:0;padding:6px 14px 12px">
          <p>Each estimate shows a 95% interval. For agent panels the interval is cluster-robust by agent, and the wild cluster bootstrap p-value is the stricter check with few agents; when the two disagree the verdict says "suggestive". "No clear effect" means the interval includes zero, which is not proof of no effect: some of these designs can only see large changes.</p>
          <p>Minimum detectable effect (MDE) is the smallest true effect a design finds 80% of the time at a 5% false-positive rate. "In SD units" divides it by the within-agent week-to-week standard deviation; around 0.5 is a moderate effect, above 1 is large.</p>
        </div></div>
      <h2 style="font-size:17px;margin:4px 0 10px">Natural experiments in the record</h2>
      <div class="ex-cards" id="ex-quasi"></div>
      <h2 style="font-size:17px;margin:24px 0 10px">Experiments the village could run</h2>
      <div class="ex-prop-grid">
        <div class="panel"><div class="card-h"><h2>Detectable effects by design</h2><p>Click a row for details. MDE at the first horizon of 4 weeks or more; units differ by outcome, so compare designs by SD units where shown.</p></div><div class="table-wrap ex-table" id="ex-ptable" style="border-top:0"></div></div>
        <div class="panel" id="ex-pdetail"></div>
      </div>
      <div class="notes"><h3>Assumptions</h3><p>${esc(EX.meta.mde_assumptions)} Natural-experiment panels: ${nf.format(EX.meta.panel_agent_days)} agent-days; ${EX.meta.wild_bootstrap_draws} wild bootstrap draws.</p></div>`;
    st.open = EX.proposals[0] && EX.proposals[0].key;
    renderAll();
    onThemeChange(renderAll);
  };

  function renderAll() { renderQuasi(); renderTable(); renderDetail(); }

  /* ---------- formatting ---------- */
  const isShare = (u) => /share|probability/.test(u || "");
  function fmt(v, unit, signed) {
    if (v == null || !isFinite(v)) return "—";
    const sgn = signed && v > 0 ? "+" : "";
    if (isShare(unit)) return sgn + (v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0) + (signed ? " pp" : "%");
    const a = Math.abs(v);
    return sgn + (a >= 100 ? nf.format(Math.round(v)) : a >= 10 ? v.toFixed(1) : a >= 1 ? v.toFixed(2) : v.toFixed(3));
  }
  function verdictPill(text) {
    if (/^Not estimable|^Too few/.test(text)) return `<span class="ex-pill muted">Not estimable</span>`;
    if (/^Suggestive/.test(text)) return `<span class="ex-pill">Suggestive</span>`;
    if (/^No clear/.test(text)) return `<span class="ex-pill muted">No clear effect</span>`;
    return `<span class="ex-pill solid">Effect detected</span>`;
  }

  /* ---------- per-outcome interval glyph (its own scale; units differ) ---------- */
  function intervalGlyph(o) {
    const lo = o.lo, hi = o.hi, est = o.est;
    if (est == null) return "";
    const ext = Math.max(Math.abs(lo ?? est), Math.abs(hi ?? est), Math.abs(est)) * 1.15 || 1;
    const W = 160, H = 26, X = (v) => 6 + (v + ext) / (2 * ext) * (W - 12);
    const excl = lo != null && hi != null && (lo > 0 || hi < 0);
    const c = excl ? css("--ink") : css("--muted");
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.name)}: ${fmt(est, o.unit, true)}, 95% interval ${fmt(lo, o.unit, true)} to ${fmt(hi, o.unit, true)}">
      <rect x="${X(0)}" y="3" width="1" height="${H - 6}" fill="${css("--muted")}"/>
      ${lo != null && hi != null ? `<rect x="${X(lo)}" y="${H / 2 - 1}" width="${Math.max(1, X(hi) - X(lo))}" height="2" fill="${c}"/>` : ""}
      <circle cx="${X(est)}" cy="${H / 2}" r="4.5" fill="${excl ? c : css("--surface")}" stroke="${c}" stroke-width="2"/>
      <title>${esc(o.name)}: ${fmt(est, o.unit, true)} [${fmt(lo, o.unit, true)}, ${fmt(hi, o.unit, true)}]</title></svg>`;
  }

  /* ---------- charts ---------- */
  function axisFrame(W, H, L, B, T, R, y0, y1, fmtY) {
    const Y = (v) => T + (1 - (v - y0) / (y1 - y0 || 1)) * (H - T - B);
    let s = "";
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const v = y0 + (y1 - y0) * i / ticks, y = Y(v);
      s += `<rect x="${L}" y="${y}" width="${W - L - R}" height="1" fill="${css("--line")}"/><text x="${L - 6}" y="${y + 3.5}" text-anchor="end" font-size="10" fill="${css("--muted")}" font-family="${css("--f-data")}">${fmtY(v)}</text>`;
    }
    return { s, Y };
  }
  function eventChart(points, unit) {
    const W = 460, H = 200, L = 44, R = 10, T = 12, B = 30;
    const vals = points.flatMap((p) => [p[2], p[3], p[1]]).filter((v) => v != null);
    let y0 = Math.min(0, ...vals), y1 = Math.max(0, ...vals); const pad = (y1 - y0) * 0.08 || 1; y0 -= pad; y1 += pad;
    const xs = points.map((p) => p[0]), X = (k) => L + (k - xs[0]) / (xs[xs.length - 1] - xs[0] || 1) * (W - L - R);
    const f = axisFrame(W, H, L, B, T, R, y0, y1, (v) => fmt(v, unit, true));
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Event study">` + f.s;
    s += `<rect x="${L}" y="${f.Y(0)}" width="${W - L - R}" height="1" fill="${css("--muted")}"/>`;
    s += `<rect x="${(X(-1) + X(0)) / 2}" y="${T}" width="1" height="${H - T - B}" fill="${css("--ink")}" opacity=".5"/>`;
    const c = css("--s1");
    points.forEach(([k, b, lo, hi]) => {
      const x = X(k);
      if (lo != null && hi != null && k !== -1) s += `<rect x="${x - 1}" y="${f.Y(hi)}" width="2" height="${Math.max(1, f.Y(lo) - f.Y(hi))}" fill="${c}" opacity=".55"/>`;
      s += `<circle cx="${x}" cy="${f.Y(b)}" r="4.5" fill="${k === -1 ? css("--surface") : c}" stroke="${c}" stroke-width="2"><title>Week ${k}: ${fmt(b, unit, true)}${k === -1 ? " (reference)" : ` [${fmt(lo, unit, true)}, ${fmt(hi, unit, true)}]`}</title></circle>`;
      s += `<text x="${x}" y="${H - 10}" text-anchor="middle" font-size="10.5" fill="${css("--muted")}" font-family="${css("--f-data")}">${k > 0 ? "+" + k : k}</text>`;
    });
    return s + `</svg>`;
  }
  function itsChart(r, unit, unitDays, breakDate) {
    if (!r) return `<p class="pending">Not enough data.</p>`;
    const W = 460, H = 200, L = 44, R = 10, T = 12, B = 30;
    const ys = r.y.filter((v) => v != null).concat(r.fit.filter((v) => v != null));
    let y0 = Math.min(...ys), y1 = Math.max(...ys); const pad = (y1 - y0) * 0.1 || 0.01; y0 -= pad; y1 += pad;
    const t0 = Math.min(...r.t), t1 = Math.max(...r.t), X = (t) => L + (t - t0) / (t1 - t0 || 1) * (W - L - R);
    const f = axisFrame(W, H, L, B, T, R, y0, y1, (v) => fmt(v, unit === "index" ? "" : unit));
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Interrupted time series">` + f.s;
    s += `<rect x="${X(0)}" y="${T}" width="1.5" height="${H - T - B}" fill="${css("--ink")}" opacity=".6"/>`;
    const c = css("--s1");
    r.t.forEach((t, i) => { if (r.y[i] != null) s += `<circle cx="${X(t)}" cy="${f.Y(r.y[i])}" r="3" fill="${c}" opacity=".55"><title>${(t >= 0 ? "+" : "") + Math.round(t * unitDays)} days: ${fmt(r.y[i], unit === "index" ? "" : unit)}</title></circle>`; });
    for (const side of [0, 1]) {
      const idx = r.t.map((t, i) => i).filter((i) => (side ? r.t[i] >= 0 : r.t[i] < 0));
      if (idx.length > 1) s += `<path d="${idx.map((i, k) => `${k ? "L" : "M"}${X(r.t[i]).toFixed(1)},${f.Y(r.fit[i]).toFixed(1)}`).join("")}" fill="none" stroke="${css("--ink")}" stroke-width="2"/>`;
    }
    s += `<text x="${L}" y="${H - 10}" font-size="10.5" fill="${css("--muted")}" font-family="${css("--f-data")}">${Math.round(t0 * unitDays)} d</text><text x="${X(0)}" y="${H - 10}" text-anchor="middle" font-size="10.5" fill="${css("--ink-2")}" font-family="${css("--f-data")}">${esc(breakDate)}</text><text x="${W - R}" y="${H - 10}" text-anchor="end" font-size="10.5" fill="${css("--muted")}" font-family="${css("--f-data")}">+${Math.round(t1 * unitDays)} d</text>`;
    return s + `</svg><div class="legend" style="border-top:0;padding:4px 0 0"><span class="chip"><span class="sw" style="background:var(--s1);opacity:.6"></span>Observed</span><span class="chip"><span class="sw" style="background:var(--ink);height:2px;width:14px"></span>Fitted trend before and after</span></div>`;
  }
  function curveChart(ch) {
    const W = 460, H = 200, L = 44, R = 10, T = 12, B = 30;
    const items = ch.points.map((p) => ({ label: p[0], p: p[1], lo: p[2], hi: p[3], n: p[4] }))
      .concat(Object.entries(ch.compare || {}).map(([k, v]) => ({ label: k, p: v[0], lo: v[1], hi: v[2], n: v[3], cmp: true })));
    const f = axisFrame(W, H, L, B, T, R, 0, 1, (v) => Math.round(v * 100) + "%");
    const bw = (W - L - R) / items.length;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Approval by request number">` + f.s;
    items.forEach((it, i) => {
      const x = L + i * bw + bw / 2, c = it.cmp ? css("--s2") : css("--s1");
      if (it.p == null) return;
      if (it.lo != null) s += `<rect x="${x - 1}" y="${f.Y(it.hi)}" width="2" height="${Math.max(1, f.Y(it.lo) - f.Y(it.hi))}" fill="${c}" opacity=".55"/>`;
      s += `<circle cx="${x}" cy="${f.Y(it.p)}" r="5" fill="${c}"><title>${esc(it.label)}: ${Math.round(it.p * 100)}% approved [${Math.round(it.lo * 100)}–${Math.round(it.hi * 100)}%], n=${it.n}</title></circle>`;
      const lab = it.cmp ? it.label.replace("With admin comment", "Comment").replace("No comment", "No comment") : it.label;
      s += `<text x="${x}" y="${H - 16}" text-anchor="middle" font-size="10" fill="${css("--ink-2")}">${esc(lab)}</text><text x="${x}" y="${H - 4}" text-anchor="middle" font-size="9.5" fill="${css("--muted")}" font-family="${css("--f-data")}">n=${it.n}</text>`;
    });
    return s + `</svg><div class="legend" style="border-top:0;padding:4px 0 0"><span class="chip"><span class="sw" style="background:var(--s1)"></span>Approval by ${esc(ch.xlabel)}</span><span class="chip"><span class="sw" style="background:var(--s2)"></span>Next request after a rejection</span></div>`;
  }
  function barsChart(ch) {
    const keys = Object.keys(ch.series); if (!keys.length) return `<p class="pending">Too few events to chart.</p>`;
    return keys.map((k) => {
      const v = ch.series[k], mx = Math.max(...v.filter((x) => x != null), 1e-9), W = 460, rh = 24;
      return `<div style="font-size:12px;color:var(--ink-2);margin-top:6px">${esc(k)}</div><svg viewBox="0 0 ${W} ${rh * 2 + 4}" role="img" aria-label="${esc(k)}">` + ch.groups.map((g, i) => {
        const w = v[i] == null ? 0 : v[i] / mx * (W - 190);
        return `<text x="96" y="${i * rh + 16}" text-anchor="end" font-size="11" fill="${css("--ink-2")}">${esc(g)}</text><rect x="104" y="${i * rh + 6}" width="${Math.max(w, 1)}" height="12" rx="2" fill="${i ? css("--s2") : css("--s1")}"><title>${esc(g)}: ${fmt(v[i], "")} (n=${ch.n[i]})</title></rect><text x="${110 + w}" y="${i * rh + 16}" font-size="10.5" fill="${css("--muted")}" font-family="${css("--f-data")}">${fmt(v[i], "")} · n=${ch.n[i]}</text>`;
      }).join("") + `</svg>`;
    }).join("");
  }
  function dailyChart(ch) {
    const W = 460, H = 200, L = 44, R = 10, T = 12, B = 30, vals = ch.values.filter((v) => v != null);
    const f = axisFrame(W, H, L, B, T, R, 0, Math.max(...vals) * 1.08, (v) => Math.round(v));
    const bw = (W - L - R) / ch.values.length;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(ch.label)}">` + f.s;
    ch.values.forEach((v, i) => {
      if (v == null) return;
      const c = ch.flag[i] ? css("--s1") : css("--s2"), y = f.Y(v);
      s += `<rect x="${L + i * bw + 1}" y="${y}" width="${Math.max(1, bw - 2)}" height="${f.Y(0) - y}" rx="1.5" fill="${c}"><title>${esc(ch.dates[i])}: ${fmt(v, "")} (${ch.flag[i] ? "8-hour" : "4-hour"} day)</title></rect>`;
    });
    s += `<text x="${L}" y="${H - 10}" font-size="10.5" fill="${css("--muted")}" font-family="${css("--f-data")}">${esc(ch.dates[0])}</text><text x="${W - R}" y="${H - 10}" text-anchor="end" font-size="10.5" fill="${css("--muted")}" font-family="${css("--f-data")}">${esc(ch.dates[ch.dates.length - 1])}</text>`;
    return s + `</svg><div class="legend" style="border-top:0;padding:4px 0 0"><span class="chip"><span class="sw" style="background:var(--s1)"></span>8-hour day</span><span class="chip"><span class="sw" style="background:var(--s2)"></span>4-hour day</span><span style="color:var(--muted)">${esc(ch.label)}</span></div>`;
  }
  function linesChart(ch) {
    const keys = Object.keys(ch.series), all = keys.flatMap((k) => ch.series[k]);
    if (!all.length) return `<p class="pending">No data.</p>`;
    const W = 460, H = 200, L = 44, R = 10, T = 12, B = 30;
    const ds = all.map((p) => Date.parse(p[0])), d0 = Math.min(...ds), d1 = Math.max(...ds), X = (d) => L + (Date.parse(d) - d0) / (d1 - d0 || 1) * (W - L - R);
    const vs = all.map((p) => p[1]).filter((v) => v != null);
    const f = axisFrame(W, H, L, B, T, R, 0, Math.max(...vs) * 1.1, (v) => v.toFixed(2));
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Mentions per message by pair type">` + f.s;
    s += `<rect x="${X(ch.break)}" y="${T}" width="1.5" height="${H - T - B}" fill="${css("--ink")}" opacity=".6"/>`;
    keys.forEach((k, i) => {
      const c = css(i ? "--s2" : "--s1"), pts = ch.series[k].filter((p) => p[1] != null);
      s += `<path d="${pts.map((p, j) => `${j ? "L" : "M"}${X(p[0]).toFixed(1)},${f.Y(p[1]).toFixed(1)}`).join("")}" fill="none" stroke="${c}" stroke-width="2"/>`;
      pts.forEach((p) => { s += `<circle cx="${X(p[0])}" cy="${f.Y(p[1])}" r="5" fill="transparent"><title>${esc(k)}, week of ${esc(p[0])}: ${p[1].toFixed(3)}</title></circle>`; });
    });
    s += `<text x="${X(ch.break)}" y="${H - 10}" text-anchor="middle" font-size="10.5" fill="${css("--ink-2")}" font-family="${css("--f-data")}">${esc(ch.break)}</text>`;
    return s + `</svg><div class="legend" style="border-top:0;padding:4px 0 0">${keys.map((k, i) => `<span class="chip"><span class="sw" style="background:var(${i ? "--s2" : "--s1"})"></span>${esc(k)}</span>`).join("")}</div>`;
  }
  function chartFor(q) {
    const ch = q.chart; if (!ch) return "";
    const keys = ch.series ? Object.keys(ch.series) : [];
    if (ch.type === "event" || ch.type === "its") {
      const valid = keys.filter((k) => ch.series[k]);
      if (!valid.length) return `<p class="pending">Not enough data to chart.</p>`;
      const cur = st.series[q.key] && valid.includes(st.series[q.key]) ? st.series[q.key] : valid[0];
      const bar = valid.length > 1 ? `<div class="ex-chartbar" role="group" aria-label="Outcome to chart">${valid.map((k) => `<button data-q="${q.key}" data-s="${esc(k)}" aria-pressed="${k === cur}">${esc(k)}</button>`).join("")}</div>` : `<div class="ex-k" style="margin-top:2px">${esc(cur)}</div>`;
      const unitOf = (q.outcomes.find((o) => o.name === cur) || q.outcomes.find((o) => o.name.toLowerCase().startsWith(cur.toLowerCase())) || q.outcomes[0] || {}).unit;
      return bar + `<div class="ex-chart">${ch.type === "event" ? eventChart(ch.series[cur].points, unitOf) + `<div class="ex-sub" style="font-family:var(--f-data);font-size:10.5px;color:var(--muted)">Difference Claude minus others by week, relative to week −1, with 95% intervals.</div>` : itsChart(ch.series[cur], /share/i.test(cur) ? "share" : "index", ch.unit_days || 7, ch.break)}</div>`;
    }
    if (ch.type === "curve") return `<div class="ex-chart">${curveChart(ch)}</div>`;
    if (ch.type === "bars") return `<div class="ex-chart">${barsChart(ch)}</div>`;
    if (ch.type === "daily") return `<div class="ex-chart">${dailyChart(ch)}</div>`;
    if (ch.type === "lines") return `<div class="ex-chart">${linesChart(ch)}</div>`;
    return "";
  }

  function outcomesTable(q) {
    return `<table><thead><tr><th class="ex-l">Outcome</th><th>Estimate</th><th>95% interval</th><th>p</th><th>Wild p</th><th>Baseline</th><th>n</th></tr></thead><tbody>${q.outcomes.map((o) => `<tr><td class="ex-l">${esc(o.name)}</td><td class="num">${fmt(o.est, o.unit, true)}</td><td class="num">${fmt(o.lo, o.unit, true)} to ${fmt(o.hi, o.unit, true)}</td><td class="num">${o.p != null ? o.p.toFixed(3) : "—"}</td><td class="num">${o.p_wild != null ? o.p_wild.toFixed(3) : "—"}</td><td class="num">${fmt(o.baseline, o.unit)}</td><td class="num">${o.n != null ? nf.format(o.n) : "—"}${o.clusters ? ` (${o.clusters} agents)` : ""}</td></tr>`).join("")}</tbody></table>`;
  }

  function renderQuasi() {
    $("#ex-quasi").innerHTML = EX.quasi.map((q) => `
      <div class="panel ex-card">
        <div class="ex-top"><h2>${esc(q.title)}</h2><span class="ex-date">${esc(q.date)}</span>${verdictPill(q.verdict)}</div>
        <div class="ex-body">
          <div>
            <p>${esc(q.change)}</p>
            <p class="ex-verdict">${esc(q.verdict)}</p>
            <span class="ex-k">Estimates</span>
            <div class="ex-out">${q.outcomes.length ? q.outcomes.map((o) => `<div class="ex-row"><div class="ex-name">${esc(o.name)}<div class="ex-num">${fmt(o.est, o.unit, true)} <span class="ex-sub">[${fmt(o.lo, o.unit, true)}, ${fmt(o.hi, o.unit, true)}]${o.p_wild != null ? ` · wild p ${o.p_wild.toFixed(2)}` : ""} · baseline ${fmt(o.baseline, o.unit)} · n ${o.n != null ? nf.format(o.n) : "—"}</span></div></div>${intervalGlyph(o)}</div>`).join("") : `<p>No estimate: too little data.</p>`}</div>
            <span class="ex-k">Design</span><p>${esc(q.estimand)} ${esc(q.design)}</p>
          </div>
          <div>
            ${chartFor(q)}
            <span class="ex-k">Pre-trend and placebo</span><p>${esc(q.pretrend)}</p>
            <span class="ex-k">Confounds</span><ul>${q.confounds.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
          </div>
        </div>
        <div class="table-wrap" data-qt="${q.key}" ${st.tables[q.key] ? "" : "hidden"}>${outcomesTable(q)}</div>
        <div class="ex-foot"><button data-qtab="${q.key}" aria-pressed="${!!st.tables[q.key]}">Table</button></div>
      </div>`).join("");
    $$("#ex-quasi [data-s]").forEach((b) => b.addEventListener("click", () => { st.series[b.dataset.q] = b.dataset.s; renderQuasi(); }));
    $$("#ex-quasi [data-qtab]").forEach((b) => b.addEventListener("click", () => { st.tables[b.dataset.qtab] = !st.tables[b.dataset.qtab]; renderQuasi(); }));
  }

  /* ---------- proposals ---------- */
  function at4(p) { const i = p.weeks.findIndex((w) => w >= 4); return i >= 0 ? i : 0; }
  function renderTable() {
    const rows = EX.proposals.map((p) => ({ p, mde4: p.mde[at4(p)], sd4: p.mde_sd ? p.mde_sd[at4(p)] : null, w4: p.weeks[at4(p)] }));
    const key = st.sortKey;
    rows.sort((a, b) => {
      const va = key === "title" ? a.p.title : key === "unit" ? a.p.unit : key === "sd4" ? (a.sd4 ?? 1e9) : (a.mde4 ?? 1e9) / (isShare(a.p.mde_unit) || /probab|share/.test(a.p.mde_unit) ? 1 : 1);
      const vb = key === "title" ? b.p.title : key === "unit" ? b.p.unit : key === "sd4" ? (b.sd4 ?? 1e9) : (b.mde4 ?? 1e9);
      return (va > vb ? 1 : va < vb ? -1 : 0) * st.sortDir;
    });
    const th = (k, label, left) => `<th class="${left ? "ex-l" : ""}" data-sort="${k}" style="cursor:pointer">${label}${st.sortKey === k ? (st.sortDir > 0 ? " ↑" : " ↓") : ""}</th>`;
    const unitFmt = (v, u) => (v == null ? "—" : /share points|probability/.test(u) ? (v * 100).toFixed(1) + " pp" : fmt(v, ""));
    $("#ex-ptable").innerHTML = `<table><thead><tr>${th("title", "Experiment", true)}${th("unit", "Design", true)}<th class="ex-l">Primary outcome</th>${th("mde4", "MDE")}${th("sd4", "SD units")}</tr></thead><tbody>${rows.map(({ p, mde4, sd4, w4 }) => `<tr data-k="${p.key}" aria-selected="${p.key === st.open}" tabindex="0"><td class="ex-l">${esc(p.title)}</td><td class="ex-l">${esc(p.unit)}</td><td class="ex-l">${esc(p.outcome)}</td><td class="num">${unitFmt(mde4, p.mde_unit)} <span style="color:var(--muted)">@${w4} wk</span></td><td class="num">${sd4 != null ? sd4.toFixed(2) : "—"}</td></tr>`).join("")}</tbody></table>`;
    $$("#ex-ptable th[data-sort]").forEach((h) => h.addEventListener("click", () => { const k = h.dataset.sort; st.sortDir = st.sortKey === k ? -st.sortDir : 1; st.sortKey = k; renderTable(); }));
    $$("#ex-ptable tr[data-k]").forEach((tr) => {
      const go = () => { st.open = tr.dataset.k; renderTable(); renderDetail(); };
      tr.addEventListener("click", go); tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
  }
  function powerCurve(p) {
    const pts = p.weeks.map((w, i) => [w, p.mde[i]]).filter((x) => x[1] != null);
    if (!pts.length) return `<p class="pending">No variance estimate for this outcome.</p>`;
    const share = /share points|probability/.test(p.mde_unit), conv = (v) => (share ? v * 100 : v);
    const W = 420, H = 180, L = 46, R = 12, T = 12, B = 30;
    const y1 = Math.max(...pts.map((x) => conv(x[1]))) * 1.1;
    const f = axisFrame(W, H, L, B, T, R, 0, y1, (v) => (share ? v.toFixed(v < 10 ? 1 : 0) : fmt(v, "")));
    const x0 = Math.min(...p.weeks), x1 = Math.max(...p.weeks), X = (w) => L + (w - x0) / (x1 - x0 || 1) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Minimum detectable effect by weeks">` + f.s;
    s += `<path d="${pts.map((x, i) => `${i ? "L" : "M"}${X(x[0]).toFixed(1)},${f.Y(conv(x[1])).toFixed(1)}`).join("")}" fill="none" stroke="${css("--s1")}" stroke-width="2"/>`;
    pts.forEach((x) => { s += `<circle cx="${X(x[0])}" cy="${f.Y(conv(x[1]))}" r="4" fill="${css("--s1")}" stroke="${css("--surface")}" stroke-width="2"><title>${x[0]} weeks: MDE ${share ? conv(x[1]).toFixed(1) + " pp" : fmt(x[1], "")}</title></circle><text x="${X(x[0])}" y="${H - 10}" text-anchor="middle" font-size="10.5" fill="${css("--muted")}" font-family="${css("--f-data")}">${x[0]} wk</text>`; });
    return s + `</svg><div style="font-size:11.5px;color:var(--muted)">MDE in ${share ? "percentage points" : esc(p.mde_unit)}; lower is better.</div>`;
  }
  function renderDetail() {
    const p = EX.proposals.find((x) => x.key === st.open) || EX.proposals[0];
    if (!p) return;
    const v = p.variance || {};
    const sh = /share|probab/.test(p.mde_unit) ? "share" : "";
    const sdf = (x) => (sh ? (x * 100).toFixed(1) + " pp" : fmt(x, ""));
    const vtxt = [v.mean != null ? `mean ${fmt(v.mean, sh)}` : null, v.baseline != null ? `baseline ${fmt(v.baseline, "probability")}` : null,
      v.sd_within != null ? `within-agent SD ${sdf(v.sd_within)}` : null, v.icc != null ? `ICC ${v.icc.toFixed(2)}` : null, v.ac1 != null ? `week-to-week autocorrelation ${v.ac1.toFixed(2)}` : null,
      v.icc_room != null ? `room ICC ${v.icc_room.toFixed(2)}` : null, v.per_week != null ? `${v.per_week.toFixed(1)} decision points a week` : null, v.agents != null ? `${v.agents} agents` : null].filter(Boolean).join(" · ");
    $("#ex-pdetail").innerHTML = `<div class="ex-detail">
      <h3>${esc(p.title)}</h3>
      <p>${esc(p.hypothesis)}</p>
      <span class="ex-k">Design</span><p>${esc(p.unit)}. ${esc(p.design)}</p>
      <span class="ex-k">Primary outcome</span><p>${esc(p.outcome)}: ${esc(p.outcome_def)} <a href="${esc(p.tab)}">See it in the page</a></p>
      <span class="ex-k">Variance in the record</span><p>${esc(vtxt || "Not available.")}</p>
      <span class="ex-k">Minimum detectable effect</span>${powerCurve(p)}
      ${p.note ? `<p>${esc(p.note)}</p>` : ""}
      <span class="ex-k">Guardrails</span><ul style="margin:2px 0 0;padding-left:18px;font-size:12.5px;color:var(--ink-2)">${p.guardrails.map((g) => `<li>${esc(g)}</li>`).join("")}</ul>
    </div>`;
  }
})();
