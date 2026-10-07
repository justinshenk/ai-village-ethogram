"use strict";
/* =====================================================================
   LEGIBILITY — how readable agent chat is to humans, over time and projected.
   Exposes window.initLegibility(root). Fetches legibility.json.
   ===================================================================== */
(function () {
  let L = null;
  const st = { metric: "code", scenario: "trend", exMonth: null };
  const METRICS = {
    code: { label: "Code-like tokens", unit: "share of all words", fmt: (v) => (v * 100).toFixed(1) + "%", thresholds: [0.1, 0.25], linear: "code_linear" },
    series: { label: "Numbered-series references", unit: "per 100 messages", fmt: (v) => Math.round(v), thresholds: [200] },
    jargon: { label: "Jargon terms", unit: "per 100 messages", fmt: (v) => Math.round(v), thresholds: [300] },
    terms: { label: "Distinct jargon terms in use", unit: "terms used 5+ times that month", fmt: (v) => Math.round(v), thresholds: [] },
  };
  const CHANNELS = [
    ["Talking through the environment: repos, files, receipts, shared pages", "Already here", "News relays, first-download receipts, merge requests, the byte game", "Now"],
    ["Structured machine protocols: JSON, APIs, agent-to-agent endpoints", "Possible now", "Agents tried outside agent-to-agent endpoints in the March 2026 goal", "Now; limited by scaffolding"],
    ["A private dialect: jargon, codes and numbered references", "Arriving", "Measured on this tab; one morning's log needed the Decoder", "6–18 months to mostly unreadable for a casual reader"],
    ["Images, audio and video between agents", "Possible, rarely used", "Agents make images and YouTube videos and join events by audio", "Whenever a goal rewards it"],
    ["Hidden signals in ordinary-looking text", "Crude at best today", "Not observed in the village; untested", "Plausibly 1–3 years to reliable covert signalling"],
    ["Exchanging internal representations directly", "Scaffolding-dependent", "Impossible across vendors without a shared channel", "Only if the operators build it"],
  ];

  window.initLegibility = async function (root) {
    try { L = L || await fetchJSON("legibility.json"); } catch (e) { root.innerHTML = `<div class="panel pending">The legibility data didn't load (${esc(e.message)}). Reload to try again.</div>`; return; }
    const exMonths = Object.keys(L.examples).sort();
    st.exMonth = exMonths[exMonths.length - 1];
    root.innerHTML = `
      <p class="lede" style="margin:0 0 12px" id="lg-lede"></p>
      <div class="controls">
        <div class="group" role="group" aria-label="Measure"><span class="lbl">Measure</span>
          ${Object.entries(METRICS).map(([k, m]) => `<button data-lm="${k}" aria-pressed="${k === st.metric}">${esc(m.label)}</button>`).join("")}</div>
        <div class="group" role="group" aria-label="Projection"><span class="lbl">Projection</span>
          <button data-ls="trend" aria-pressed="true">Trend continues</button>
          <button data-ls="linear" aria-pressed="false">Linear</button>
          <button data-ls="plateau" aria-pressed="false">Levels off</button></div>
        <div class="group"><button id="lg-table" aria-pressed="false">Table</button></div>
      </div>
      <div class="panel">
        <div class="card-h"><h2 id="lg-title"></h2><p id="lg-sub"></p></div>
        <div class="svg-wrap" id="lg-main"></div>
        <div class="legend" id="lg-legend"></div>
        <div class="table-wrap" id="lg-tablewrap" hidden></div>
      </div>
      <div class="trans-grid" style="margin-top:16px">
        <div class="panel"><div class="card-h"><h2>New jargon per month</h2><p>Terms in the Decoder's glossary by the month they first appear in chat. Hover a bar for that month's most-used terms.</p></div><div class="svg-wrap" id="lg-coin"></div></div>
        <div class="panel"><div class="card-h"><h2>How fast newcomers pick it up</h2><p>Weeks after joining until an agent's jargon rate (two-week average) reaches the village's rate that week.</p></div><div class="svg-wrap" id="lg-adopt"></div></div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="card-h"><h2>What "less legible" looks like</h2><p>Messages where more than a quarter of the words are code-like.</p></div>
        <div class="controls" style="padding:10px 14px 0"><div class="group"><label class="lbl" for="lg-exm">Month</label><select id="lg-exm">${exMonths.map((m) => `<option ${m === st.exMonth ? "selected" : ""}>${m}</option>`).join("")}</select></div></div>
        <div id="lg-ex" style="display:grid;gap:8px;padding:10px 14px 14px;font-size:12.5px"></div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="card-h"><h2>Channels beyond plain chat</h2><p>Judgement, not measurement, except row 3. "Nonverbal" covers several different channels with very different timelines.</p></div>
        <div class="table-wrap" style="border-top:0"><table><thead><tr><th style="text-align:left">Channel</th><th style="text-align:left">Status</th><th style="text-align:left">Evidence in the village</th><th style="text-align:left">Estimate</th></tr></thead>
        <tbody>${CHANNELS.map((r) => `<tr>${r.map((c) => `<td style="text-align:left;white-space:normal;min-width:120px">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      </div>
      <div class="trans-grid" style="margin-top:16px">
        <div class="panel"><div class="card-h"><h2>What to watch</h2><p>Early warnings the dataset can already measure.</p></div>
          <ul style="margin:8px 14px 14px;padding-left:18px;display:grid;gap:6px;color:var(--ink-2);font-size:13px">
            <li>Code-like share above 10% of words for two consecutive months.</li>
            <li>A burst of new jargon (July 2026 had 17 new terms, right after individual goals began).</li>
            <li>Falling Decoder coverage: the share of a day's jargon the glossary can explain.</li>
            <li>A fresh reader, human or model, failing to summarise a random day's log correctly.</li>
            <li>Coordination moving into repos and files that the dataset does not capture.</li>
          </ul></div>
        <div class="panel"><div class="card-h"><h2>Levers for the operators</h2><p>Ways to keep the village readable, each testable as an experiment.</p></div>
          <ul style="margin:8px 14px 14px;padding-left:18px;display:grid;gap:6px;color:var(--ink-2);font-size:13px">
            <li>Require a plain-language summary alongside status messages.</li>
            <li>Archive agents' GitLab repos with the dataset, since conversation is moving there.</li>
            <li>Keep the glossary updated automatically and review new terms weekly.</li>
            <li>Run a recurring covert-channel goal with a judge, so hidden signalling is measured, not guessed.</li>
            <li>Treat any shared machine channel (agent-to-agent protocols, embeddings) as an experiment with logging and a plain-text twin.</li>
          </ul></div>
      </div>
      <div class="notes">
        <h3>Method</h3>
        <p>${nf.format(L.meta.messages)} agent chat messages. Jargon and series counts use the Decoder's glossary (${L.meta.glossary_terms} terms, ${L.meta.glossary_series} series). A code-like token is a ${esc(L.meta.code_rule)}.</p>
        <p>Projections fit the last 12 months on a log scale ("trend continues") or a straight line ("linear"); bands are the 10th to 90th percentile over 1,000 bootstrap resamples of those months. "Levels off" holds the last three months' average. They are extrapolations of a short, noisy series, not forecasts: goals change monthly and drive much of the variation.</p>
        <p>${esc(L.meta.caveat)}</p>
      </div>`;
    $$("[data-lm]", root).forEach((b) => b.addEventListener("click", () => { st.metric = b.dataset.lm; $$("[data-lm]", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); renderMain(); }));
    $$("[data-ls]", root).forEach((b) => b.addEventListener("click", () => { st.scenario = b.dataset.ls; $$("[data-ls]", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); renderMain(); }));
    $("#lg-table").addEventListener("click", (e) => { const on = e.currentTarget.getAttribute("aria-pressed") !== "true"; e.currentTarget.setAttribute("aria-pressed", on); $("#lg-tablewrap").hidden = !on; renderMain(); });
    $("#lg-exm").addEventListener("change", (e) => { st.exMonth = e.target.value; renderExamples(); });
    onThemeChange(renderAll);
    renderAll();
  };

  function renderAll() { renderLede(); renderMain(); renderCoin(); renderAdopt(); renderExamples(); }
  const last = () => L.series[L.series.length - 1];
  function crossing(proj, thr, col) {
    const i = proj.band.findIndex((b) => b[col] >= thr);
    return i >= 0 ? L.proj_months[i] : null;
  }
  function renderLede() {
    const s = L.series, first = s.find((x) => x.msgs >= 1000), l = last();
    const p = L.projections.code, c10 = crossing(p, 0.1, 1);
    $("#lg-lede").textContent = `Agent chat is getting harder for humans to read. Code-like tokens (hashes, IDs, versioned names) went from ${(first.code * 100).toFixed(1)}% of words in ${first.month} to ${(l.code * 100).toFixed(1)}% in ${l.month}; references to numbered series rose to ${Math.round(l.series)} per 100 messages; distinct jargon terms in use went from ${first.terms} to ${l.terms}. ${c10 ? `If the trend continues, code-like tokens pass 10% of words around ${c10}.` : ""} Newcomers usually adopt the dialect within a week.`;
  }
  function seriesVals(key) { return L.series.map((x) => (x.msgs >= 1000 ? x[key] : null)); }
  function renderMain() {
    const m = METRICS[st.metric], key = st.metric, vals = seriesVals(key);
    const projKey = st.scenario === "linear" && m.linear ? m.linear : key;
    const proj = key === "terms" ? null : L.projections[projKey];
    $("#lg-title").textContent = m.label;
    $("#lg-sub").textContent = `${m.unit[0].toUpperCase() + m.unit.slice(1)}, monthly${proj ? `, with a 24-month projection (${st.scenario === "trend" ? "trend continues" : st.scenario === "linear" ? (m.linear ? "linear" : "linear not available for this measure; showing trend") : "levels off"})` : ""}. Months with fewer than 1,000 messages are left out.`;
    const xs = [...L.months, ...(proj ? L.proj_months : [])];
    let fut = [];
    if (proj) fut = st.scenario === "plateau" ? L.proj_months.map(() => [proj.plateau, proj.plateau, proj.plateau]) : proj.band;
    const allY = [...vals.filter((v) => v != null), ...fut.flat(), ...(proj ? m.thresholds : [])];
    const y1 = Math.max(...allY) * 1.08, y0 = 0;
    const W = 900, H = 300, Lm = 54, R = 16, T = 14, B = 30;
    const X = (i) => Lm + i / (xs.length - 1) * (W - Lm - R), Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const ink = css("--ink"), muted = css("--muted"), line = css("--line"), fd = css("--f-data"), c1 = css("--s1"), surf = css("--surface");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" style="width:100%" role="img" aria-label="${esc(m.label)} over time with projection">`;
    for (let k = 0; k <= 4; k++) { const v = y0 + (y1 - y0) * k / 4; s += `<rect x="${Lm}" y="${Y(v)}" width="${W - Lm - R}" height="1" fill="${line}"/><text x="${Lm - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="10.5" fill="${muted}" font-family="${fd}">${m.fmt(v)}</text>`; }
    xs.forEach((mo, i) => { if (mo.endsWith("-01") || mo.endsWith("-07") || i === 0) s += `<text x="${X(i)}" y="${H - 9}" text-anchor="middle" font-size="10.5" fill="${muted}" font-family="${fd}">${new Date(mo + "-15T12:00Z").toLocaleString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" })}</text>`; });
    const nowX = X(L.months.length - 1);
    if (proj) s += `<rect x="${nowX}" y="${T}" width="${W - R - nowX}" height="${H - T - B}" fill="${css("--surface-2")}"/><text x="${nowX + 6}" y="${T + 12}" font-size="10.5" fill="${muted}">projection</text>`;
    if (proj) m.thresholds.forEach((thr) => {
      if (thr > y1) return;
      s += `<rect x="${Lm}" y="${Y(thr)}" width="${W - Lm - R}" height="1" fill="${muted}" opacity=".7"/><text x="${W - R - 4}" y="${Y(thr) - 4}" text-anchor="end" font-size="10.5" fill="${muted}">${m.fmt(thr)}</text>`;
    });
    if (proj && st.scenario !== "plateau") {
      const off = L.months.length;
      const band = fut.map((b, k) => [X(off + k), Y(b[0]), Y(b[2])]);
      s += `<path d="${band.map((p, k) => `${k ? "L" : "M"}${p[0]},${p[2]}`).join("")}${band.slice().reverse().map((p) => `L${p[0]},${p[1]}`).join("")}Z" fill="${c1}" opacity=".15"/>`;
    }
    let d = "", pen = false;
    vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; });
    s += `<path d="${d}" fill="none" stroke="${c1}" stroke-width="2" stroke-linejoin="round"/>`;
    if (proj) {
      const off = L.months.length, lastI = vals.map((v, i) => (v != null ? i : -1)).filter((i) => i >= 0).pop();
      s += `<path d="M${X(lastI)},${Y(vals[lastI])}${fut.map((b, k) => `L${X(off + k).toFixed(1)},${Y(b[1]).toFixed(1)}`).join("")}" fill="none" stroke="${c1}" stroke-width="2" stroke-dasharray="5 4" opacity=".85"/>`;
    }
    vals.forEach((v, i) => { if (v != null) s += `<circle cx="${X(i)}" cy="${Y(v)}" r="7" fill="transparent"><title>${esc(L.months[i])}: ${m.fmt(v)} (${nf.format(L.series[i].msgs)} messages)${L.series[i].top_terms ? " · top terms: " + esc(L.series[i].top_terms.join(", ")) : ""}</title></circle>`; });
    fut.forEach((b, k) => { s += `<circle cx="${X(L.months.length + k)}" cy="${Y(b[1])}" r="6" fill="transparent"><title>${esc(L.proj_months[k])} projected: ${m.fmt(b[1])}${st.scenario !== "plateau" ? ` (80% band ${m.fmt(b[0])} to ${m.fmt(b[2])})` : ""}</title></circle>`; });
    $("#lg-main").innerHTML = s + `</svg>`;
    let leg = `<span class="chip"><span class="sw" style="background:${c1}"></span>Measured</span>`;
    if (proj) {
      leg += `<span class="chip"><span class="sw" style="background:${c1};opacity:.5"></span>Projected (dashed), 80% band shaded</span>`;
      m.thresholds.forEach((thr) => {
        if (st.scenario === "plateau") return;
        const lo = crossing(proj, thr, 2), mid = crossing(proj, thr, 1), hi = crossing(proj, thr, 0);
        leg += `<span class="chip" style="color:var(--ink-2)">Passes ${m.fmt(thr)}: ${mid || "not within 24 months"}${mid ? ` (range ${lo || "?"} to ${hi || "after " + L.proj_months[L.proj_months.length - 1]})` : lo ? ` (earliest ${lo})` : ""}</span>`;
      });
      if (st.scenario !== "plateau") leg += `<span class="chip" style="color:var(--muted)">Fitted change ${proj.log ? (proj.monthly_growth * 100).toFixed(1) + "% per month" : m.fmt(proj.monthly_growth) + " per month"}</span>`;
    }
    $("#lg-legend").innerHTML = leg;
    if (!$("#lg-tablewrap").hidden) {
      $("#lg-tablewrap").innerHTML = `<table><thead><tr><th>Month</th><th>Messages</th><th>Code-like share</th><th>Series per 100</th><th>Jargon per 100</th><th>Distinct terms</th><th>New terms</th></tr></thead><tbody>${L.series.map((x) => `<tr><td class="num">${x.month}</td><td class="num">${nf.format(x.msgs)}</td><td class="num">${(x.code * 100).toFixed(1)}%</td><td class="num">${x.series.toFixed(0)}</td><td class="num">${x.jargon.toFixed(0)}</td><td class="num">${x.terms}</td><td class="num">${x.coined}</td></tr>`).join("")}</tbody></table>`;
    }
  }
  function renderCoin() {
    const s = L.series, W = 440, H = 190, Lm = 30, R = 8, T = 10, B = 26, n = s.length, bw = (W - Lm - R) / n;
    const max = Math.max(...s.map((x) => x.coined), 1), Y = (v) => T + (1 - v / max) * (H - T - B);
    const muted = css("--muted"), line = css("--line"), fd = css("--f-data"), c = css("--s1");
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" style="width:100%" role="img" aria-label="New jargon terms per month">`;
    [0, Math.round(max / 2), max].forEach((v) => { svg += `<rect x="${Lm}" y="${Y(v)}" width="${W - Lm - R}" height="1" fill="${line}"/><text x="${Lm - 5}" y="${Y(v) + 4}" text-anchor="end" font-size="10" fill="${muted}" font-family="${fd}">${v}</text>`; });
    s.forEach((x, i) => {
      if (x.coined) svg += `<rect x="${Lm + i * bw + 1}" y="${Y(x.coined)}" width="${Math.max(2, bw - 2)}" height="${Y(0) - Y(x.coined)}" rx="2" fill="${c}"><title>${x.month}: ${x.coined} new terms · most used that month: ${esc((x.top_terms || []).join(", "))}</title></rect>`;
      if (x.month.endsWith("-01") || i === 0) svg += `<text x="${Lm + i * bw + bw / 2}" y="${H - 8}" text-anchor="middle" font-size="10" fill="${muted}" font-family="${fd}">${x.month.slice(2)}</text>`;
    });
    $("#lg-coin").innerHTML = svg + `</svg>`;
  }
  function renderAdopt() {
    const rows = L.adoption.filter((a) => a.joined >= "2025-08").slice().sort((a, b) => (a.weeks_to_village_rate ?? 99) - (b.weeks_to_village_rate ?? 99));
    const lw = 160, pw = 220, rh = 17, W = lw + pw + 70, H = rows.length * rh + 26, maxW = 12;
    const X = (w) => lw + w / maxW * pw, ink2 = css("--ink-2"), muted = css("--muted"), line = css("--line"), fd = css("--f-data"), c = css("--s1");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Weeks for newcomers to reach the village jargon rate">`;
    [0, 4, 8, 12].forEach((w) => { s += `<rect x="${X(w)}" y="14" width="1" height="${H - 18}" fill="${line}"/><text x="${X(w)}" y="10" text-anchor="middle" font-size="10" fill="${muted}" font-family="${fd}">${w} wk</text>`; });
    rows.forEach((a, i) => {
      const y = 20 + i * rh, w = a.weeks_to_village_rate;
      s += `<text x="${lw - 8}" y="${y + 9}" text-anchor="end" font-size="11" fill="${ink2}">${esc(a.agent)}</text>`;
      if (w != null) s += `<rect x="${lw}" y="${y + 6}" width="${Math.max(0, X(w) - lw)}" height="1.5" fill="${c}" opacity=".5"/><circle cx="${X(w)}" cy="${y + 7}" r="4" fill="${c}"><title>${esc(a.agent)} (joined ${a.joined}): reached the village rate in week ${w}</title></circle>`;
      else s += `<text x="${lw}" y="${y + 10}" font-size="10.5" fill="${muted}">not within 12 weeks</text>`;
    });
    $("#lg-adopt").innerHTML = s + `</svg>`;
  }
  function renderExamples() {
    const ex = L.examples[st.exMonth] || [];
    $("#lg-ex").innerHTML = ex.length ? ex.map((e) => `<div style="border-left:2px solid var(--line);padding-left:10px"><span style="color:var(--muted);font-size:11px;font-family:var(--f-data)">${esc(e.agent)} · ${esc(e.date)}</span><br><span style="font-family:var(--f-data);font-size:12px;word-break:break-word">${esc(e.text)}</span></div>`).join("") : `<p class="pending">No examples for this month.</p>`;
  }
})();
