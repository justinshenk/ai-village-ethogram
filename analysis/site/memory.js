"use strict";
/* =====================================================================
   MEMORY — early indicators of memory decline.
   Exposes window.initMemory(root). Fetches memory.json.
   ===================================================================== */
(function () {
  let MD = null;
  const st = { outcome: "repeat", lag: 2, agent: null, show: ["keep", "new", "neg", "step"] };
  const SHORT = { keep: "Kept verbatim", new: "New material", dup_lines: "Duplicate lines", compress: "Compressibility", neg: "Failure words", meta: "Self-correction words", lag: "Date staleness", url_keep: "Links kept", len: "Length", step: "Embedding change" };

  window.initMemory = async function (root) {
    try { MD = MD || await fetchJSON("memory.json"); } catch (e) { root.innerHTML = `<div class="panel pending">The memory analysis didn't load (${esc(e.message)}). Reload to try again.</div>`; return; }
    const agents = Object.keys(MD.agents).sort((a, b) => MD.agents[b].length - MD.agents[a].length);
    st.agent = MD.agents["Gemini 2.5 Pro"] ? "Gemini 2.5 Pro" : agents[0];
    root.innerHTML = `
      <p class="lede" style="margin:0 0 12px" id="m-lede"></p>
      <div class="controls">
        <div class="group" role="group" aria-label="Decline signal"><span class="lbl">Decline signal</span>
          ${Object.entries(MD.outcomes).map(([k, v]) => `<button data-mo="${k}" aria-pressed="${k === st.outcome}">${esc(v)}</button>`).join("")}</div>
        <div class="group" role="group" aria-label="Weeks ahead"><span class="lbl">Weeks ahead</span>
          ${MD.lags.filter((l) => l > 0).map((l) => `<button data-ml="${l}" aria-pressed="${l === st.lag}">${l}</button>`).join("")}</div>
      </div>
      <div class="trans-grid">
        <div class="panel">
          <div class="card-h"><h2>Which memory signals predict decline?</h2><p id="m-gsub"></p></div>
          <div class="svg-wrap" id="m-forest"></div>
          <div class="table-wrap" id="m-forest-table" hidden></div>
          <div class="legend"><span class="chip"><span class="sw" style="background:var(--ink)"></span>Interval excludes zero</span><span class="chip"><span class="sw" style="background:var(--muted);opacity:.6"></span>Interval includes zero</span><button id="m-ftab" aria-pressed="false" style="margin-left:auto">Table</button></div>
        </div>
        <div class="panel">
          <div class="card-h"><h2>Lead and lag</h2><p>Within-agent correlation between each signal and the decline signal some weeks later. A dot marks a 90% interval that excludes zero.</p></div>
          <div class="svg-wrap" id="m-heat"></div>
          <div class="scale" id="m-heatscale"></div>
        </div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="card-h"><h2>Around the start of a loop</h2><p id="m-esub"></p></div>
        <div id="m-event" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;padding:10px 14px 14px"></div>
      </div>
      <div class="panel" style="margin-top:16px" id="m-rw-panel">
        <div class="card-h"><h2>What a rewrite keeps and loses</h2><p id="m-rw-sub">Each memory row is a full rewrite. Lines are typed by keyword rules and followed into the next rewrite and across days.</p></div>
        <div class="trans-grid" style="padding:0 0 4px">
          <div><div class="svg-wrap" id="m-rw-bars"></div><div class="legend" id="m-rw-barleg"></div></div>
          <div><div class="svg-wrap" id="m-rw-surv"></div><div class="legend" id="m-rw-survleg"></div></div>
        </div>
        <div class="trans-grid" style="padding:0 14px 14px">
          <div><h3 style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:6px 0">Longest-lasting lines</h3>
            <div class="group" style="margin-bottom:6px"><label class="lbl" for="m-rw-agent">Agent</label><select id="m-rw-agent"></select></div>
            <div class="table-wrap" id="m-rw-core" style="border-top:0"></div></div>
          <div><h3 style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:6px 0">Examples of lines that were dropped</h3>
            <div class="group" style="margin-bottom:6px"><label class="lbl" for="m-rw-type">Type</label><select id="m-rw-type"></select></div>
            <div id="m-rw-lost" style="display:grid;gap:6px;font-size:12.5px;color:var(--ink-2)"></div></div>
        </div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="card-h"><h2>One agent over time</h2><p>Weekly values. Shaded weeks have 10% or more repeated messages; vertical lines mark loop onsets.</p></div>
        <div class="controls" style="padding:10px 14px 0">
          <div class="group"><label class="lbl" for="m-agent">Agent</label><select id="m-agent">${agents.map((a) => `<option ${a === st.agent ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></div>
          <div class="group" role="group" aria-label="Signals to show"><span class="lbl">Signals</span>
            ${Object.keys(MD.indicators).map((k) => `<button data-ms="${k}" aria-pressed="${st.show.includes(k)}">${esc(SHORT[k] || k)}</button>`).join("")}</div>
        </div>
        <div id="m-agentcharts" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;padding:10px 14px 14px"></div>
      </div>
      <div class="notes">
        <h3>Method</h3>
        <p>Each memory row is a full rewrite of an agent's memory. Text signals compare each rewrite with the previous one: lines kept verbatim, new lines, duplicate lines, compressibility, links kept, the newest date mentioned, and the density of failure words (failed, broken, stuck…) and self-correction words (loop, mistake, retract…). "Embedding change" is the cosine distance between consecutive daily memory embeddings.</p>
        <p>The decline signals come from the event log: the share of an agent's messages that nearly repeat its previous message, and the share of its time spent waiting or paused. Everything is aggregated per agent-week (${nf.format(MD.meta.agent_weeks)} agent-weeks).</p>
        <p>The prediction test asks whether a memory signal this week predicts the decline signal k weeks later after accounting for the decline signal this week, with agent and calendar-week effects removed (two-way fixed effects) and all variables standardised. Intervals are 90% bootstrap intervals that resample whole agents (${MD.meta.bootstrap} draws), because weeks of one agent are not independent. A loop onset is ${esc(MD.meta.onset_rule)}.</p>
        <p>These are associations in observational data with one agent per model. Idle share changes meaning at the 2026-03-24 scaffolding change (WAIT gave way to PAUSE); the calendar-week effects absorb village-wide shifts like that, but not agent-specific ones.</p>
      </div>`;
    $$("[data-mo]", root).forEach((b) => b.addEventListener("click", () => { st.outcome = b.dataset.mo; $$("[data-mo]", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); renderAll(); }));
    $$("[data-ml]", root).forEach((b) => b.addEventListener("click", () => { st.lag = +b.dataset.ml; $$("[data-ml]", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); renderAll(); }));
    $$("[data-ms]", root).forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.ms; st.show = st.show.includes(k) ? st.show.filter((x) => x !== k) : [...st.show, k];
      b.setAttribute("aria-pressed", st.show.includes(k)); renderAgent();
    }));
    $("#m-agent").addEventListener("change", (e) => { st.agent = e.target.value; renderAgent(); });
    $("#m-ftab").addEventListener("click", (e) => { const on = e.currentTarget.getAttribute("aria-pressed") !== "true"; e.currentTarget.setAttribute("aria-pressed", on); $("#m-forest-table").hidden = !on; renderForest(); });
    try { RW = await fetchJSON("memory_rewrite.json", true); } catch (e) { RW = null; }
    if (RW) {
      const ags = Object.keys(RW.core).filter((a) => RW.core[a].length).sort();
      $("#m-rw-agent").innerHTML = ags.map((a) => `<option ${a === st.agent ? "selected" : ""}>${esc(a)}</option>`).join("");
      $("#m-rw-type").innerHTML = RW.types.filter((t) => (RW.lost_examples[t] || []).length).map((t) => `<option>${esc(t)}</option>`).join("");
      $("#m-rw-agent").addEventListener("change", renderRewrite);
      $("#m-rw-type").addEventListener("change", renderRewrite);
    } else $("#m-rw-panel").hidden = true;
    onThemeChange(renderAll);
    renderAll();
  };
  let RW = null;
  function renderRewrite() {
    if (!RW) return;
    const types = RW.types, ink2 = css("--ink-2"), muted = css("--muted"), line = css("--line"), fd = css("--f-data");
    const parts = ["verbatim", "paraphrase", "lost"], cols = [css("--s1"), css("--s3"), css("--s8")], labels = ["Kept word for word", "Kept, reworded", "Dropped"];
    const rows = types.map((t) => { const c = RW.per_rewrite[t] || {}; const n = parts.reduce((a, k) => a + (c[k] || 0), 0); return { t, n, v: parts.map((k) => (c[k] || 0) / (n || 1)) }; })
      .filter((r) => r.n).sort((a, b) => b.v[2] - a.v[2]);
    const lw = 170, bw = 260, rh = 24, W = lw + bw + 60, H = rows.length * rh + 26;
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="What each rewrite keeps, by line type"><text x="0" y="12" font-size="11.5" font-weight="600" fill="${ink2}">Per rewrite, by type of line</text>`;
    rows.forEach((r, i) => {
      const y = 22 + i * rh; let acc = 0;
      s += `<text x="${lw - 8}" y="${y + rh / 2 + 4}" text-anchor="end" font-size="11.5" fill="${ink2}">${esc(r.t)}</text>`;
      r.v.forEach((v, k) => { s += `<rect x="${lw + acc * bw}" y="${y + 5}" width="${Math.max(0, v * bw - 2)}" height="${rh - 10}" rx="2" fill="${cols[k]}"><title>${esc(r.t)} · ${labels[k]}: ${pct(v, 1)} of ${nf.format(r.n)} lines</title></rect>`; acc += v; });
      s += `<text x="${lw + bw + 8}" y="${y + rh / 2 + 4}" font-size="10.5" fill="${muted}" font-family="${fd}">${pct(r.v[2], 0)} lost</text>`;
    });
    $("#m-rw-bars").innerHTML = s + `</svg>`;
    $("#m-rw-barleg").innerHTML = labels.map((l, k) => `<span class="chip"><span class="sw" style="background:${cols[k]}"></span>${l}</span>`).join("");
    // survival across days: one line per selected type (fixed slots), others muted
    const show = ["Links & accounts", "Identity", "Rules & lessons", "Goals & plans", "Status & progress log"].filter((t) => RW.survival[t]);
    const hs = ["1", "7", "30", "90"], W2 = 330, H2 = 210, L = 40, R = 10, T = 24, B = 26;
    const X = (i) => L + i / (hs.length - 1) * (W2 - L - R), maxY = Math.max(...show.flatMap((t) => hs.map((h) => RW.survival[t][h] || 0))) * 1.1 || 1;
    const Y = (v) => T + (1 - v / maxY) * (H2 - T - B);
    const sc = [css("--s1"), css("--s2"), css("--s3"), css("--s4"), css("--s5")];
    let s2 = `<svg viewBox="0 0 ${W2} ${H2}" width="${W2}" role="img" aria-label="Share of lines still present word for word after days"><text x="0" y="12" font-size="11.5" font-weight="600" fill="${ink2}">Still present word for word after…</text>`;
    [0, maxY / 2, maxY].forEach((v) => { s2 += `<rect x="${L}" y="${Y(v)}" width="${W2 - L - R}" height="1" fill="${line}"/><text x="${L - 5}" y="${Y(v) + 4}" text-anchor="end" font-size="10" fill="${muted}" font-family="${fd}">${Math.round(v * 100)}%</text>`; });
    hs.forEach((h, i) => { s2 += `<text x="${X(i)}" y="${H2 - 8}" text-anchor="middle" font-size="10.5" fill="${muted}" font-family="${fd}">${h} day${h === "1" ? "" : "s"}</text>`; });
    show.forEach((t, k) => {
      const pts = hs.map((h, i) => [X(i), Y(RW.survival[t][h] || 0), RW.survival[t][h] || 0]);
      s2 += `<path d="${pts.map((p, j) => `${j ? "L" : "M"}${p[0]},${p[1]}`).join("")}" fill="none" stroke="${sc[k]}" stroke-width="2"/>`;
      pts.forEach((p, j) => { s2 += `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="${sc[k]}" stroke="${css("--surface")}" stroke-width="1.5"><title>${esc(t)} after ${hs[j]} days: ${pct(p[2], 1)}</title></circle>`; });
    });
    $("#m-rw-surv").innerHTML = s2 + `</svg>`;
    $("#m-rw-survleg").innerHTML = show.map((t, k) => `<span class="chip"><span class="sw" style="background:${sc[k]}"></span>${esc(t)}</span>`).join("");
    const ag = $("#m-rw-agent").value, core = RW.core[ag] || [];
    $("#m-rw-core").innerHTML = core.length ? `<table><thead><tr><th style="text-align:left">Line</th><th>Days present</th><th>Since</th></tr></thead><tbody>${core.map((c) => `<tr><td style="text-align:left;white-space:normal;min-width:200px">${esc(c.line)}<br><span style="color:var(--muted);font-size:11px">${esc(c.type)}</span></td><td class="num">${c.days}</td><td class="num">${esc(c.since)}</td></tr>`).join("")}</tbody></table>` : `<p class="pending">No line lasted five or more days.</p>`;
    const ty = $("#m-rw-type").value;
    $("#m-rw-lost").innerHTML = (RW.lost_examples[ty] || []).map(([a, d, l]) => `<div style="border-left:2px solid var(--line);padding-left:8px"><span style="color:var(--muted);font-size:11px;font-family:var(--f-data)">${esc(a)} · ${esc(d)}</span><br>${esc(l)}</div>`).join("");
    $("#m-rw-sub").textContent = `Each memory row is a full rewrite. A typical rewrite keeps about three quarters of its lines word for word, rewords about a tenth and drops the rest, so within a day most lines have changed and within a month almost none survive verbatim. Identity and links last longest; plans and status logs churn fastest. Line types come from keyword rules, so treat them as approximate; reworded lines are matched by word overlap.`;
  }

  function renderAll() { renderLede(); renderForest(); renderHeat(); renderEvent(); renderRewrite(); renderAgent(); }
  const g = (ko, ki, lag) => MD.granger[`${ko}|${ki}|${lag}`];
  const sig = (ci) => ci && ci[0] != null && (ci[0] > 0 || ci[1] < 0);

  function renderLede() {
    const hits = [];
    for (const ko of Object.keys(MD.outcomes)) for (const ki of Object.keys(MD.indicators)) for (const lag of MD.lags.filter((l) => l > 0)) {
      const r = g(ko, ki, lag); if (r && sig(r.ci)) hits.push({ ko, ki, lag, ...r });
    }
    const n = MD.onsets.length;
    const tests = Object.keys(MD.indicators).length * Object.keys(MD.outcomes).length * MD.lags.filter((l) => l > 0).length;
    const chance = Math.round(tests * 0.1);
    $("#m-lede").textContent = `No memory signal is a reliable early warning yet. Raw correlations look promising (agents whose memory stops changing repeat themselves more, even weeks later), but most of that is persistence: once this week's behaviour and the calendar week are accounted for, ${hits.length} of ${tests} tests cross the 90% line, about what chance alone would give (${chance}). Loops that start after a clean stretch are rare (${n} onsets), so the event study below is exploratory.`;
  }

  function renderForest() {
    const ko = st.outcome, lag = st.lag;
    const rows = Object.keys(MD.indicators).map((ki) => ({ ki, r: g(ko, ki, lag) })).filter((x) => x.r && x.r.ci[0] != null)
      .sort((a, b) => b.r.beta - a.r.beta);
    $("#m-gsub").textContent = `Effect of each memory signal this week on ${MD.outcomes[ko].toLowerCase()} ${lag} week${lag > 1 ? "s" : ""} later, beyond this week's value. Standardised, with 90% intervals.`;
    if (!rows.length) { $("#m-forest").innerHTML = `<p class="pending">Not enough data.</p>`; return; }
    const lim = Math.max(0.15, ...rows.flatMap((x) => [Math.abs(x.r.ci[0]), Math.abs(x.r.ci[1])])) * 1.1;
    const lw = 250, pw = 300, rh = 26, T = 22, W = lw + pw + 70, H = T + rows.length * rh + 8;
    const X = (v) => lw + (v + lim) / (2 * lim) * pw;
    const ink = css("--ink"), ink2 = css("--ink-2"), muted = css("--muted"), line = css("--line"), fd = css("--f-data");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Prediction effects with intervals">`;
    [-lim, -lim / 2, 0, lim / 2, lim].forEach((v) => {
      s += `<rect x="${X(v)}" y="${T - 4}" width="1" height="${H - T}" fill="${v === 0 ? muted : line}"/><text x="${X(v)}" y="${T - 8}" text-anchor="middle" font-size="10.5" fill="${muted}" font-family="${fd}">${v > 0 ? "+" : ""}${v.toFixed(2)}</text>`;
    });
    rows.forEach(({ ki, r }, i) => {
      const y = T + i * rh + rh / 2, on = sig(r.ci), c = on ? ink : muted;
      s += `<text x="${lw - 10}" y="${y + 4}" text-anchor="end" font-size="11.5" fill="${ink2}">${esc(MD.indicators[ki])}</text>`;
      s += `<g><title>${esc(MD.indicators[ki])}: ${r.beta.toFixed(3)} [${r.ci[0]}, ${r.ci[1]}], ${r.agents} agents, ${r.n} agent-weeks</title>`;
      s += `<rect x="${X(r.ci[0])}" y="${y - 1}" width="${Math.max(1, X(r.ci[1]) - X(r.ci[0]))}" height="2" fill="${c}" opacity="${on ? 1 : 0.6}"/>`;
      s += `<circle cx="${X(r.beta)}" cy="${y}" r="5" fill="${on ? c : css("--surface")}" stroke="${c}" stroke-width="2"/></g>`;
      s += `<text x="${lw + pw + 10}" y="${y + 4}" font-size="10.5" fill="${muted}" font-family="${fd}">${r.beta > 0 ? "+" : ""}${r.beta.toFixed(2)}</text>`;
    });
    $("#m-forest").innerHTML = s + `</svg>`;
    if (!$("#m-forest-table").hidden) {
      $("#m-forest-table").innerHTML = `<table><thead><tr><th>Signal</th>${MD.lags.filter((l) => l > 0).map((l) => `<th>${l} wk ahead</th>`).join("")}</tr></thead><tbody>${Object.keys(MD.indicators).map((ki) => `<tr><td>${esc(MD.indicators[ki])}</td>${MD.lags.filter((l) => l > 0).map((l) => { const r = g(ko, ki, l); return `<td class="num">${r && r.ci[0] != null ? `${r.beta > 0 ? "+" : ""}${r.beta.toFixed(3)} [${r.ci[0]}, ${r.ci[1]}]` : "—"}</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;
    }
  }

  function renderHeat() {
    const ko = st.outcome, inds = Object.keys(MD.indicators), lags = MD.lags;
    const cw = 58, lw = 250, rh = 26, T = 24, W = lw + lags.length * cw + 10, H = T + inds.length * rh + 6;
    const ink2 = css("--ink-2"), muted = css("--muted"), fd = css("--f-data");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Lead and lag correlations">`;
    lags.forEach((l, j) => { s += `<text x="${lw + j * cw + cw / 2}" y="${T - 8}" text-anchor="middle" font-size="10.5" fill="${muted}" font-family="${fd}">${l === 0 ? "same wk" : "+" + l + " wk"}</text>`; });
    inds.forEach((ki, i) => {
      const y = T + i * rh;
      s += `<text x="${lw - 10}" y="${y + rh / 2 + 4}" text-anchor="end" font-size="11.5" fill="${ink2}">${esc(MD.indicators[ki])}</text>`;
      lags.forEach((l, j) => {
        const c = MD.leadlag[`${ko}|${ki}|${l}`]; if (!c) return;
        const fill = divColor(Math.max(-1, Math.min(1, c.r / 0.3 * 0.5)));
        const tc = lum(fill) < 0.5 ? "#ffffff" : "#121417";
        s += `<g><title>${esc(MD.indicators[ki])}, ${l} weeks ahead: r = ${c.r.toFixed(3)} [${c.ci[0]}, ${c.ci[1]}], ${c.agents} agents</title><rect x="${lw + j * cw + 1}" y="${y + 1}" width="${cw - 2}" height="${rh - 2}" rx="3" fill="${fill}"/>`;
        s += `<text x="${lw + j * cw + cw / 2 - (sig(c.ci) ? 4 : 0)}" y="${y + rh / 2 + 4}" text-anchor="middle" font-size="10.5" fill="${tc}" font-family="${fd}">${c.r > 0 ? "+" : ""}${c.r.toFixed(2)}</text>`;
        if (sig(c.ci)) s += `<circle cx="${lw + j * cw + cw - 9}" cy="${y + rh / 2}" r="2.5" fill="${tc}"/>`;
        s += `</g>`;
      });
    });
    $("#m-heat").innerHTML = s + `</svg>`;
    $("#m-heatscale").innerHTML = `<span>negative</span><span class="ramp" style="background:linear-gradient(90deg, ${divColor(-0.5)}, ${divColor(0)}, ${divColor(0.5)})"></span><span>positive (r ±0.3 at the ends)</span>`;
  }

  function miniLine(opts) {
    // opts: {xs:[labels], series:[{vals, color, band?:[lo,hi]}], y0, y1, zeroLine, vlines:[i], shade:[bool], title, fmt}
    const W = 280, H = 130, L = 34, R = 8, T = 22, B = 20;
    const n = opts.xs.length, X = (i) => L + (n > 1 ? i / (n - 1) : 0.5) * (W - L - R);
    let y0 = opts.y0, y1 = opts.y1; if (y1 - y0 < 1e-9) { y0 -= 1; y1 += 1; }
    const Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const ink2 = css("--ink-2"), muted = css("--muted"), line = css("--line"), fd = css("--f-data");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(opts.title)}">`;
    s += `<text x="0" y="12" font-size="11.5" font-weight="600" fill="${ink2}">${esc(opts.title)}</text>`;
    if (opts.shade) opts.shade.forEach((on, i) => { if (on) s += `<rect x="${X(i) - (W - L - R) / Math.max(1, n - 1) / 2}" y="${T}" width="${(W - L - R) / Math.max(1, n - 1)}" height="${H - T - B}" fill="${css("--surface-3")}"/>`; });
    [y0, (y0 + y1) / 2, y1].forEach((v) => { s += `<rect x="${L}" y="${Y(v)}" width="${W - L - R}" height="1" fill="${line}"/><text x="${L - 4}" y="${Y(v) + 3.5}" text-anchor="end" font-size="9.5" fill="${muted}" font-family="${fd}">${opts.fmt(v)}</text>`; });
    if (opts.zeroLine && y0 < 0 && y1 > 0) s += `<rect x="${L}" y="${Y(0)}" width="${W - L - R}" height="1" fill="${muted}"/>`;
    (opts.vlines || []).forEach((i) => { s += `<rect x="${X(i)}" y="${T}" width="1.5" height="${H - T - B}" fill="${css("--ink")}" opacity=".7"/>`; });
    opts.series.forEach((sr) => {
      if (sr.band) {
        const pts = sr.band[0].map((lo, i) => (lo != null && sr.band[1][i] != null ? [i, lo, sr.band[1][i]] : null)).filter(Boolean);
        if (pts.length > 1) s += `<path d="${pts.map((p, k) => `${k ? "L" : "M"}${X(p[0])},${Y(p[2])}`).join("")}${pts.slice().reverse().map((p) => `L${X(p[0])},${Y(p[1])}`).join("")}Z" fill="${sr.color}" opacity=".16"/>`;
      }
      let d = "", pen = false;
      sr.vals.forEach((v, i) => { if (v == null || !isFinite(v)) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; });
      s += `<path d="${d}" fill="none" stroke="${sr.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      sr.vals.forEach((v, i) => { if (v != null && isFinite(v)) s += `<circle cx="${X(i)}" cy="${Y(v)}" r="6" fill="transparent"><title>${esc(opts.xs[i])}: ${opts.fmt(v)}</title></circle>`; });
    });
    if (opts.xlab) { s += `<text x="${L}" y="${H - 5}" font-size="9.5" fill="${muted}" font-family="${fd}">${esc(opts.xlab[0])}</text><text x="${W - R}" y="${H - 5}" text-anchor="end" font-size="9.5" fill="${muted}" font-family="${fd}">${esc(opts.xlab[1])}</text>`; }
    return s + `</svg>`;
  }

  function renderEvent() {
    const box = $("#m-event"), keys = Object.keys(MD.event);
    $("#m-esub").textContent = `Average of each signal (z-scored within agent) from 8 weeks before to 4 weeks after the week a loop starts, with 90% intervals. ${MD.onsets.length} onsets; the line at 0 is the onset week.`;
    const panels = [...keys.map((k) => ({ k, e: MD.event[k], title: MD.indicators[k] })),
      ...Object.entries(MD.ews || {}).map(([k, e]) => ({ k: "ews-" + k, e, title: k === "var" ? "Embedding change: rolling variance" : "Embedding change: rolling autocorrelation" }))];
    box.innerHTML = panels.map(({ e, title }) => {
      const vals = e.mean, lo = e.lo, hi = e.hi, all = [...lo, ...hi].filter((v) => v != null && isFinite(v));
      const ext = Math.max(0.5, ...all.map(Math.abs));
      return `<div>${miniLine({ xs: e.rel.map((r) => (r === 0 ? "onset week" : (r > 0 ? "+" : "") + r + " wk")), series: [{ vals, color: css("--s1"), band: [lo, hi] }], y0: -ext, y1: ext, zeroLine: true, vlines: [e.rel.indexOf(0)], title: `${title} (n=${e.n})`, fmt: (v) => v.toFixed(1), xlab: ["−8 wk", "+4 wk"] })}</div>`;
    }).join("") || `<p class="pending">Not enough loop onsets.</p>`;
  }

  function renderAgent() {
    const rows = MD.agents[st.agent]; if (!rows) return;
    const cols = MD.columns, ci = (k) => cols.indexOf(k);
    const xs = rows.map((r) => r[0]), rep = rows.map((r) => r[ci("repeat")]);
    const shade = rep.map((v) => v != null && v >= 0.1);
    const ons = MD.onsets.filter(([a]) => a === st.agent).map(([, w]) => xs.indexOf(w)).filter((i) => i >= 0);
    const xlab = [xs[0], xs[xs.length - 1]];
    const chart = (key, title, color, fmt) => {
      const vals = rows.map((r) => r[ci(key)]), fin = vals.filter((v) => v != null && isFinite(v));
      if (!fin.length) return "";
      return `<div>${miniLine({ xs, series: [{ vals, color }], y0: Math.min(...fin), y1: Math.max(...fin), shade, vlines: ons, title, fmt, xlab })}</div>`;
    };
    const pctf = (v) => Math.round(v * 100) + "%";
    let html = chart("repeat", "Repeated-message share", css("--s8"), pctf) + chart("idle", "Idle share", css("--s4"), pctf);
    st.show.forEach((k) => { html += chart(k, MD.indicators[k], css("--s1"), (v) => (Math.abs(v) >= 100 ? nf.format(Math.round(v)) : Math.abs(v) >= 1 ? v.toFixed(1) : v.toFixed(2))); });
    $("#m-agentcharts").innerHTML = html;
  }
})();
