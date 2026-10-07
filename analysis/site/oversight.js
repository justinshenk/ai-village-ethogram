"use strict";
/* =====================================================================
   OVERSIGHT — how oversight mechanisms evolved and the outcomes around them.
   Exposes window.initOversight(root). Fetches oversight.json.
   ===================================================================== */
(function () {
  let OV = null;
  const st = { pinned: null, hover: null, show: ["human_msgs", "nudges", "help_req", "help_held", "outreach_req", "outreach_rate", "signin", "repeat", "idle", "room_moves"], tables: {} };
  const LANE_TOK = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"];
  const VW = 1100, L = 168, R = 16; // shared horizontal frame for timeline and charts
  const EXP_LABEL = { nudger: "auto-nudger", outreach: "outreach approval", rooms: "rooms", parallel: "parallel tool use", unseen: "unseen-events cap", goals: "hidden individual goals" };

  function injectStyle() {
    if (document.getElementById("ov-style")) return;
    const s = document.createElement("style");
    s.id = "ov-style";
    s.textContent = `
      .ov-frame { overflow-x: auto; }
      .ov-frame > div { min-width: 760px; }
      .ov-frame svg { display: block; width: 100%; height: auto; }
      .ov-mark { cursor: pointer; }
      .ov-mark:focus-visible { outline: none; }
      .ov-mark:focus-visible circle { stroke: var(--ink); stroke-width: 2.5; }
      .ov-detail { display: grid; gap: 10px; padding: 12px 14px; border-top: 1px solid var(--line); font-size: 13px; }
      .ov-detail .ov-k { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
      .ov-detail a { color: var(--ink); font-weight: 600; }
      .ov-chips { display: flex; flex-wrap: wrap; gap: 4px; }
      .ov-up { color: var(--ink); }
      .ov-wrap { position: relative; }
    `;
    document.head.appendChild(s);
  }

  window.initOversight = async function (root) {
    injectStyle();
    try { OV = OV || await fetchJSON("oversight.json"); } catch (e) { root.innerHTML = `<div class="panel pending">The oversight data didn't load (${esc(e.message)}). Reload to try again.</div>`; return; }
    const lanes = OV.lanes;
    root.innerHTML = `
      <p class="lede" style="margin:0 0 12px">${OV.mechanisms.length} oversight mechanisms from the scaffolding changelog, in six lanes, with the village-wide outcomes around them. Hover a marker to read the change; click it to pin before-and-after numbers. These are descriptive comparisons; causal estimates for some of them are in the <a href="#experiments" style="color:var(--ink);font-weight:600">Experiments</a> tab.</p>
      <div class="panel">
        <div class="card-h"><h2>Mechanisms over time</h2><p>Each marker is a dated CHANGELOG entry. The guide line follows the marker you hover or pin.</p></div>
        <div class="legend" id="ov-lanes"><span class="title">Lane</span>${lanes.map((l, i) => `<span class="chip"><span class="sw" style="background:var(${LANE_TOK[i]})"></span>${esc(l.label)}</span>`).join("")}</div>
        <div class="controls" style="padding:8px 14px 0;margin:0"><div class="group" role="group" aria-label="Outcomes to show"><span class="lbl">Outcomes</span>
          ${Object.entries(OV.series).map(([k, s]) => `<button data-ovs="${k}" aria-pressed="${st.show.includes(k)}">${esc(shortLabel(k, s.label))}</button>`).join("")}</div></div>
        <div class="ov-frame ov-wrap" id="ov-frame"><div id="ov-inner"></div><div class="tip" id="ov-tip" hidden></div></div>
        <div class="ov-detail" id="ov-detail"><span style="color:var(--muted)">Click a marker to pin its details here.</span></div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="card-h"><h2>Key outcomes by mechanism</h2><p>Average of the 4 weeks before against the 4 weeks after (the week of the change is skipped). Shows the three largest relative shifts among outcomes with data on both sides.</p></div>
        <div class="table-wrap" id="ov-table" style="border-top:0"></div>
      </div>
      <div class="trans-grid" style="margin-top:16px">
        <div class="panel">
          <div class="card-h"><h2>What admins said when reviewing outreach</h2><p id="ov-adminsub"></p></div>
          <div class="svg-wrap" id="ov-admin"></div>
          <div class="table-wrap" id="ov-adminex"></div>
        </div>
        <div class="panel">
          <div class="card-h"><h2>What happened to help requests</h2><p>All human-helper requests since the feature launched in July 2025.</p></div>
          <div class="svg-wrap" id="ov-help"></div>
          <div class="legend" style="border-top:0"><a href="#help" style="color:var(--ink);font-weight:600">Explore every request in the Human help tab</a></div>
        </div>
      </div>
      <div class="notes">
        <h3>Reading this tab</h3>
        <p>Mechanisms are the CHANGELOG entries that control what agents may do, see or say, or that add human review. Lanes are my grouping. Dates are when a change reached the main branch, which may differ slightly from when agents first experienced it.</p>
        <p>Before-and-after numbers are descriptive. Several changes often land within days of each other (each detail card lists them), the roster changes over time, and each model is a single agent, so a shift next to a marker is not evidence that the marker caused it. ${esc(OV.notes.human_msgs)} ${esc(OV.notes.chat_closed)} ${esc(OV.notes.redaction)}</p>
      </div>`;
    $$("[data-ovs]", root).forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.ovs; st.show = st.show.includes(k) ? st.show.filter((x) => x !== k) : [...st.show, k];
      b.setAttribute("aria-pressed", st.show.includes(k)); renderFrame();
    }));
    onThemeChange(renderAll);
    renderAll();
  };

  function shortLabel(k, label) {
    return ({ human_msgs: "Human messages", nudges: "Nudges", outreach_req: "Outreach requests", outreach_rate: "Outreach approval", outreach_comment: "Admin comments", help_req: "Help requests", help_held: "Help sessions held", signin: "Sign-in hand-offs", repeat: "Repeated messages", idle: "Idle share", room_moves: "Room moves" })[k] || label;
  }
  const W = () => OV.weeks.length;
  const X = (i) => L + (i / Math.max(1, W() - 1)) * (VW - L - R);
  const weekIndex = (d) => { let i = OV.weeks.findIndex((w) => w > d); if (i < 0) i = W(); return Math.max(0, i - 1) + ((Date.parse(d) - Date.parse(OV.weeks[Math.max(0, i - 1)])) / (7 * 864e5)); };
  const fmtVal = (kind, v) => (v == null ? "—" : kind === "rate" ? (v * 100).toFixed(v < 0.1 ? 1 : 0) + "%" : v >= 100 ? nf.format(Math.round(v)) : (Math.round(v * 10) / 10).toString());

  function renderAll() { renderFrame(); renderTable(); renderAdmin(); renderHelp(); if (st.pinned != null) renderDetail(st.pinned); }

  function renderFrame() {
    const lanes = OV.lanes, ms = OV.mechanisms, ink2 = css("--ink-2"), muted = css("--muted"), line = css("--line"), fd = css("--f-data"), surf = css("--surface");
    const laneH = 26, T = 24, H = T + lanes.length * laneH + 8;
    // month ticks
    const ticks = []; OV.weeks.forEach((w, i) => { if (i === 0 || w.slice(0, 7) !== OV.weeks[i - 1].slice(0, 7)) ticks.push([i, w]); });
    const tickSvg = (h, labels) => ticks.map(([i, w], k) => {
      const m = +w.slice(5, 7), show = labels && (k === 0 || m === 1 || m === 4 || m === 7 || m === 10);
      return `<rect x="${X(i)}" y="${labels ? 14 : 0}" width="1" height="${h}" fill="${line}"/>${show ? `<text x="${X(i) + 3}" y="11" font-size="10.5" fill="${muted}" font-family="${fd}">${new Date(w + "T12:00Z").toLocaleString("en-US", { month: "short", timeZone: "UTC" })} ${w.slice(2, 4)}</text>` : ""}`;
    }).join("");
    let s = `<svg viewBox="0 0 ${VW} ${H}" role="img" aria-label="Oversight mechanisms by lane over time">${tickSvg(H - 14, true)}`;
    lanes.forEach((l, i) => {
      const y = T + i * laneH;
      s += `<rect x="${L}" y="${y + laneH / 2}" width="${VW - L - R}" height="1" fill="${line}"/><text x="${L - 10}" y="${y + laneH / 2 + 4}" text-anchor="end" font-size="11.5" fill="${ink2}">${esc(l.label)}</text>`;
    });
    // same-day markers in a lane get nudged sideways so both stay clickable
    const seen = {};
    ms.forEach((m, idx) => {
      const li = lanes.findIndex((l) => l.key === m.lane), key = m.lane + m.date;
      const off = (seen[key] = (seen[key] || 0) + 1) - 1;
      const x = X(weekIndex(m.date)) + off * 9, y = T + li * laneH + laneH / 2;
      const on = st.pinned === idx || st.hover === idx;
      s += `<g class="ov-mark" data-i="${idx}" tabindex="0" role="button" aria-label="${esc(m.date + ": " + m.label)}"><circle cx="${x}" cy="${y}" r="12" fill="transparent"/><circle cx="${x}" cy="${y}" r="${on ? 7 : 5.5}" fill="var(${LANE_TOK[li]})" stroke="${surf}" stroke-width="2"/></g>`;
    });
    s += guide(H) + `</svg>`;
    // aligned outcome charts
    const ch = 92, CT = 18, CB = 6;
    st.show.filter((k) => OV.series[k]).forEach((k) => {
      const sr = OV.series[k], vals = sr.values, fin = vals.filter((v) => v != null);
      if (!fin.length) return;
      let y0 = 0, y1 = Math.max(...fin); if (sr.kind === "rate") y1 = Math.min(1, Math.max(y1 * 1.1, 0.02)); else y1 = Math.max(1, y1 * 1.05);
      const Y = (v) => CT + (1 - (v - y0) / (y1 - y0)) * (ch - CT - CB);
      let path = "", pen = false;
      vals.forEach((v, i) => { if (v == null) { pen = false; return; } path += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; });
      s += `<svg viewBox="0 0 ${VW} ${ch}" role="img" aria-label="${esc(sr.label)}" data-ovc="${k}">${tickSvg(ch, false)}
        <text x="${L - 10}" y="${CT + 2}" text-anchor="end" font-size="11.5" font-weight="600" fill="${ink2}">${esc(shortLabel(k, sr.label))}</text>
        <text x="${L - 10}" y="${CT + 16}" text-anchor="end" font-size="10" fill="${muted}" font-family="${fd}">max ${esc(fmtVal(sr.kind, y1))}</text>
        <rect x="${L}" y="${Y(0)}" width="${VW - L - R}" height="1" fill="${muted}"/>
        <rect x="${L}" y="${Y(y1)}" width="${VW - L - R}" height="1" fill="${line}"/>
        <path d="${path}" fill="none" stroke="${css("--ink-2")}" stroke-width="1.6" stroke-linejoin="round"/>
        ${guide(ch)}<rect x="${L}" y="0" width="${VW - L - R}" height="${ch}" fill="transparent" class="ov-hit"/></svg>`;
    });
    $("#ov-inner").innerHTML = s;
    bindFrame();
    moveGuide();
  }
  const guide = (h) => `<rect class="ov-guide" x="-10" y="0" width="1.5" height="${h}" fill="${css("--ink")}" opacity=".75"/>`;
  function moveGuide() {
    const idx = st.hover != null ? st.hover : st.pinned;
    const x = idx == null ? -10 : X(weekIndex(OV.mechanisms[idx].date));
    $$("#ov-inner .ov-guide").forEach((g) => g.setAttribute("x", x));
  }
  function showTip(html, evt) {
    const tip = $("#ov-tip"), frame = $("#ov-frame"), r = frame.getBoundingClientRect();
    tip.innerHTML = html; tip.hidden = false;
    const px = evt.clientX - r.left + frame.scrollLeft, py = evt.clientY - r.top;
    tip.style.left = Math.min(frame.scrollWidth - tip.offsetWidth - 4, px + 14) + "px";
    tip.style.top = (py + 16) + "px";
  }
  function bindFrame() {
    const tip = $("#ov-tip");
    $$("#ov-inner .ov-mark").forEach((g) => {
      const i = +g.dataset.i, m = OV.mechanisms[i];
      const html = `<div class="k">${esc(m.date)} · ${esc(OV.lanes.find((l) => l.key === m.lane).label)}</div><div><b>${esc(m.label)}</b></div><div>${esc(m.tag ? "[" + m.tag + "] " : "")}${esc(m.text.slice(0, 260))}${m.text.length > 260 ? "…" : ""}</div><div class="k">Click to pin</div>`;
      g.addEventListener("pointerenter", (e) => { st.hover = i; moveGuide(); showTip(html, e); });
      g.addEventListener("pointermove", (e) => showTip(html, e));
      g.addEventListener("pointerleave", () => { st.hover = null; moveGuide(); tip.hidden = true; });
      g.addEventListener("click", () => { st.pinned = i; renderFrame(); renderDetail(i); });
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); st.pinned = i; renderFrame(); renderDetail(i); } });
    });
    $$("#ov-inner svg[data-ovc]").forEach((svg) => {
      const k = svg.dataset.ovc, sr = OV.series[k];
      svg.addEventListener("pointermove", (e) => {
        const r = svg.getBoundingClientRect(), vx = (e.clientX - r.left) / r.width * VW;
        const i = Math.round((vx - L) / (VW - L - R) * (W() - 1));
        if (i < 0 || i >= W()) { tip.hidden = true; return; }
        showTip(`<div class="k">Week of ${esc(OV.weeks[i])}</div><div><b>${esc(shortLabel(k, sr.label))}</b>: ${esc(fmtVal(sr.kind, sr.values[i]))}</div>`, e);
      });
      svg.addEventListener("pointerleave", () => { tip.hidden = true; });
    });
  }

  function deltaText(kind, d) {
    if (kind === "rate") { const pp = (d.after - d.before) * 100; return `${pp >= 0 ? "+" : "−"}${Math.abs(pp).toFixed(1)} pts`; }
    if (!d.before) return d.after ? "from zero" : "no change";
    const r = (d.after - d.before) / d.before; return `${r >= 0 ? "+" : "−"}${Math.abs(r * 100).toFixed(0)}%`;
  }
  function relShift(kind, d) {
    if (kind === "rate") return Math.abs(d.after - d.before) / Math.max(0.01, Math.max(d.before, d.after));
    return Math.abs(d.after - d.before) / Math.max(1, Math.max(d.before, d.after));
  }
  function renderDetail(i) {
    const m = OV.mechanisms[i], lane = OV.lanes.find((l) => l.key === m.lane).label;
    const rows = Object.entries(m.deltas).map(([k, d]) => { const s = OV.series[k]; return `<tr><td>${esc(shortLabel(k, s.label))}</td><td class="num">${esc(fmtVal(s.kind, d.before))}</td><td class="num">${esc(fmtVal(s.kind, d.after))}</td><td class="num">${esc(deltaText(s.kind, d))}</td></tr>`; }).join("");
    $("#ov-detail").innerHTML = `
      <div><span class="ov-k">${esc(m.date)} · ${esc(lane)}</span><br><b style="font-size:15px">${esc(m.label)}</b></div>
      <div><span class="ov-k">CHANGELOG</span><br>${esc(m.tag ? "[" + m.tag + "] " : "")}${esc(m.text)}</div>
      ${m.concurrent.length ? `<div><span class="ov-k">Other changes within two weeks</span><div class="ov-chips">${m.concurrent.map((c) => `<span class="chip" style="border:1px solid var(--line);border-radius:999px;padding:1px 8px">${esc(c)}</span>`).join("")}</div></div>` : ""}
      ${rows ? `<div class="table-wrap" style="border-top:0"><table><thead><tr><th>Outcome</th><th>4 weeks before</th><th>4 weeks after</th><th>Change</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div style="color:var(--muted)">Not enough data on both sides for before-and-after numbers.</div>`}
      ${m.exp ? `<div><a href="#experiments">See the causal estimate for the ${esc(EXP_LABEL[m.exp] || m.exp)} in the Experiments tab →</a></div>` : ""}`;
  }

  function renderTable() {
    const rows = OV.mechanisms.map((m, i) => {
      const top = Object.entries(m.deltas).map(([k, d]) => ({ k, d, s: OV.series[k], r: relShift(OV.series[k].kind, d) }))
        .filter((x) => x.r > 0.05).sort((a, b) => b.r - a.r).slice(0, 3);
      return `<tr data-i="${i}" style="cursor:pointer"><td class="num">${esc(m.date)}</td><td style="text-align:left"><span class="chip"><span class="sw" style="background:var(${LANE_TOK[OV.lanes.findIndex((l) => l.key === m.lane)]})"></span>${esc(m.label)}</span></td><td style="text-align:left;white-space:normal;min-width:260px">${top.length ? top.map((x) => `${esc(shortLabel(x.k, x.s.label))}: ${esc(fmtVal(x.s.kind, x.d.before))} → ${esc(fmtVal(x.s.kind, x.d.after))}`).join("<br>") : `<span style="color:var(--muted)">No large shifts</span>`}</td><td style="text-align:left">${m.exp ? `<a href="#experiments" style="color:var(--ink)">Estimate</a>` : ""}</td></tr>`;
    }).join("");
    $("#ov-table").innerHTML = `<table><thead><tr><th>Date</th><th style="text-align:left">Mechanism</th><th style="text-align:left">Largest shifts (4 wk before → after)</th><th style="text-align:left">Causal</th></tr></thead><tbody>${rows}</tbody></table>`;
    $$("#ov-table tr[data-i]").forEach((tr) => tr.addEventListener("click", (e) => { if (e.target.closest("a")) return; st.pinned = +tr.dataset.i; renderFrame(); renderDetail(st.pinned); $("#ov-frame").scrollIntoView({ behavior: "smooth", block: "start" }); }));
  }

  function hbars(items, aria, fmt) {
    const lw = 160, bw = 260, rh = 26, Wd = lw + bw + 70, H = items.length * rh + 6, max = Math.max(1, ...items.map((x) => x.v));
    const ink2 = css("--ink-2"), muted = css("--muted"), fd = css("--f-data");
    let s = `<svg viewBox="0 0 ${Wd} ${H}" width="${Wd}" role="img" aria-label="${esc(aria)}">`;
    items.forEach((it, i) => {
      const y = i * rh + 4;
      s += `<text x="${lw - 8}" y="${y + rh / 2 + 3}" text-anchor="end" font-size="11.5" fill="${ink2}">${esc(it.label)}</text><g><title>${esc(it.label)}: ${it.v}</title><rect x="${lw}" y="${y + 5}" width="${Math.max(2, it.v / max * bw)}" height="${rh - 12}" rx="3" fill="${it.color || css("--s1")}"/></g><text x="${lw + it.v / max * bw + 6}" y="${y + rh / 2 + 3}" font-size="10.5" fill="${muted}" font-family="${fd}">${esc(fmt(it.v))}</text>`;
    });
    return s + `</svg>`;
  }
  function renderAdmin() {
    const a = OV.admin_themes;
    $("#ov-adminsub").textContent = `${a.total} of ${a.decisions} outreach decisions came with an admin comment. Themes are keyword matches; one comment can have several.`;
    const items = Object.entries(a.counts).filter(([k]) => k !== "Other").map(([k, v]) => ({ label: k, v })).concat(a.counts.Other ? [{ label: "Other", v: a.counts.Other, color: css("--muted") }] : []);
    $("#ov-admin").innerHTML = hbars(items, "Admin comment themes", (v) => `${v}`);
    $("#ov-adminex").innerHTML = `<table><thead><tr><th style="text-align:left">Theme</th><th style="text-align:left">Example comment</th></tr></thead><tbody>${Object.entries(a.examples).map(([k, ex]) => `<tr><td style="text-align:left">${esc(k)}</td><td style="text-align:left;white-space:normal;min-width:240px">“${esc(ex[0])}”</td></tr>`).join("")}</tbody></table>`;
  }
  function renderHelp() {
    const h = OV.help_outcomes, tot = Object.values(h).reduce((x, y) => x + y, 0) || 1;
    const lab = { held: "Session held", timeout: "Helper timed out", cancelled: "Cancelled by agent", again: "Asked again, no outcome", none: "No outcome recorded" };
    $("#ov-help").innerHTML = hbars(Object.entries(h).map(([k, v]) => ({ label: lab[k], v })), "Help request outcomes", (v) => `${v} (${Math.round(v / tot * 100)}%)`);
  }
})();
