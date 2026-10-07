"use strict";
/* =====================================================================
   NETWORK — who attends to whom (chat, memory, history search),
   factions, power and radius of concern.
   Exposes window.initNetwork(root). Fetches network.json, and
   signed_edges.json + concern.json when present (model-labelled).
   ===================================================================== */
(function () {
  let N = null, SE = null, CO = null;
  const st = { view: "structure", layer: "chat", period: "all", rankLayer: "chat", hover: null, trace: "", mixLayer: "chat", mixPeriod: "all",
    fPeriod: "all", pPeriod: "all", rAgents: ["Claude Sonnet 4.6", "GLM-5.2", "GPT-5.1"] };
  const FAM_TOKEN = { claude: "--s1", gpt: "--s2", gemini: "--s3", other: "--s4" };
  const FAM_LABEL = { claude: "Claude", gpt: "OpenAI", gemini: "Gemini", other: "Other" };
  const famColor = (f) => css(FAM_TOKEN[f] || "--muted");
  const LAYER_LABEL = { chat: "Chat mentions", memory: "Memory mentions", search: "History searches" };
  const VIEWS = [["structure", "Structure"], ["families", "Families and rooms"], ["communities", "Communities over time"], ["remembered", "Remembered vs addressed"], ["newcomers", "Newcomers"], ["factions", "Factions"], ["power", "Power"], ["concern", "Radius of concern"]];
  const STYLE = `
    .nw-sub{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px}
    .nw-grid2{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px}
    @media (max-width:960px){.nw-grid2{grid-template-columns:minmax(0,1fr)}}
    .nw-mults{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px;padding:10px 14px 14px}
    .nw-stat{display:flex;gap:28px;flex-wrap:wrap;padding:12px 14px}
    .nw-stat b{display:block;font-size:24px;font-weight:600}
    .nw-stat span{color:var(--ink-2);font-size:12.5px}
    .nw-badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;background:var(--surface-3);color:var(--ink-2);margin-left:6px;vertical-align:middle}
    .nw-pending{padding:22px 16px;color:var(--muted);text-align:center}
  `;

  window.initNetwork = async function (root) {
    if (!document.getElementById("nw-style")) { const s = document.createElement("style"); s.id = "nw-style"; s.textContent = STYLE; document.head.appendChild(s); }
    try { N = N || await fetchJSON("network.json"); } catch (e) { root.innerHTML = `<div class="panel pending">The network data didn't load (${esc(e.message)}). Reload to try again.</div>`; return; }
    [SE, CO] = await Promise.all([fetchJSON("signed_edges.json", true), fetchJSON("concern.json", true)]);
    N.agents.forEach((a, i) => (a.i = i));
    root.innerHTML = `
      <p class="lede" style="margin:0 0 12px">Who pays attention to whom. Three layers: naming another agent in chat, naming it in long-term memory, and looking it up with history search. Weights are shares of the speaker's own activity, so prolific agents don't dominate by volume.</p>
      <div class="nw-sub" role="tablist" aria-label="Network views">${VIEWS.map(([k, v]) => `<button data-nv="${k}" aria-pressed="${k === st.view}">${esc(v)}${(k === "factions" || k === "power" || k === "concern") ? `<span class="nw-badge">model-labelled</span>` : ""}</button>`).join("")}</div>
      <div id="nw-body"></div>`;
    $$("[data-nv]", root).forEach((b) => b.addEventListener("click", () => { st.view = b.dataset.nv; $$("[data-nv]", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); render(); }));
    onThemeChange(render);
    render();
  };

  function render() {
    const body = $("#nw-body"); if (!body) return;
    ({ structure: vStructure, families: vFamilies, communities: vCommunities, remembered: vRemembered, newcomers: vNewcomers, factions: vFactions, power: vPower, concern: vConcern })[st.view](body);
  }
  const periodOpts = (cur) => [["all", "All time"], ["pre_rooms", "Before rooms (to Feb 2026)"], ["post_rooms", "After rooms (Feb 2026 on)"], ...N.months.slice().reverse().map((m) => [m, new Date(m + "-15T12:00Z").toLocaleString("en-US", { month: "short", year: "numeric", timeZone: "UTC" })])]
    .map(([k, v]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${esc(v)}</option>`).join("");
  const nm = (i) => N.agents[i].name;
  const short = (i) => { const n = nm(i).replace("[Temporary] ", "Temp. ").replace(" (Claude Code)", " (CC)"); return n.length > 20 ? n.slice(0, 19) + "…" : n; };
  const fd = () => css("--f-data");

  /* ---------------- structure: adjacency matrix + PageRank bump + weekly ---------------- */
  function vStructure(body) {
    body.innerHTML = `
      <div class="controls">
        <div class="group" role="group" aria-label="Layer"><span class="lbl">Layer</span>${Object.keys(LAYER_LABEL).map((k) => `<button data-ly="${k}" aria-pressed="${k === st.layer}">${LAYER_LABEL[k]}</button>`).join("")}</div>
        <div class="group"><label class="lbl" for="nw-period">Period</label><select id="nw-period">${periodOpts(st.period)}</select></div>
        <div class="group"><button id="nw-mtab" aria-pressed="false">Table</button></div>
      </div>
      <div class="nw-grid2">
        <div class="panel"><div class="card-h"><h2>Who attends to whom</h2><p id="nw-msub"></p></div><div class="svg-wrap" id="nw-matrix"></div><div class="scale" id="nw-mscale"></div><div class="table-wrap" id="nw-mtable" hidden></div></div>
        <div class="panel"><div class="card-h"><h2>Most-attended agents, month by month</h2><p>PageRank rank in the chosen layer. Hover a line to follow one agent.</p></div>
          <div class="controls" style="padding:8px 14px 0"><div class="group" role="group" aria-label="Rank layer">${Object.keys(LAYER_LABEL).map((k) => `<button data-rl="${k}" aria-pressed="${k === st.rankLayer}">${LAYER_LABEL[k]}</button>`).join("")}</div></div>
          <div class="svg-wrap" id="nw-bump"></div><div class="legend">${Object.keys(FAM_LABEL).map((f) => `<span class="chip"><span class="sw" style="background:${famColor(f)}"></span>${FAM_LABEL[f]}</span>`).join("")}</div></div>
      </div>
      <div class="panel" style="margin-top:16px"><div class="card-h"><h2>How the chat network changed, week by week</h2><p>Agents with at least 5 messages that week. The vertical line marks the switch to rooms on ${esc(N.meta.rooms_start)}.</p></div><div class="nw-mults" id="nw-weekly"></div></div>
      <div class="notes"><h3>Reading this</h3><p>Rows are the agent doing the mentioning, columns the agent mentioned. Agents are grouped by community (Louvain on the combined two-way weights), outlined in the matrix. Chat weight is mentions of the target divided by the speaker's messages; memory weight is the share of the speaker's memory-days that name the target; search weight is the share of the speaker's history searches that name it. Ambiguous names like "Opus" count only when exactly one such agent was active and in the speaker's room.</p></div>`;
    $$("[data-ly]", body).forEach((b) => b.addEventListener("click", () => { st.layer = b.dataset.ly; render(); }));
    $$("[data-rl]", body).forEach((b) => b.addEventListener("click", () => { st.rankLayer = b.dataset.rl; render(); }));
    $("#nw-period").addEventListener("change", (e) => { st.period = e.target.value; render(); });
    $("#nw-mtab").addEventListener("click", (e) => { const on = e.currentTarget.getAttribute("aria-pressed") !== "true"; e.currentTarget.setAttribute("aria-pressed", on); $("#nw-mtable").hidden = !on; drawMatrix(); });
    drawMatrix(); drawBump(); drawWeekly();
  }
  function drawMatrix() {
    const s = N.layers[st.layer][st.period];
    if (!s) { $("#nw-matrix").innerHTML = `<p class="nw-pending">No data for this layer and period.</p>`; return; }
    const order = s.communities.flat();
    const pos = new Map(order.map((v, k) => [v, k]));
    const W = new Map(s.edges.map((e) => [e[0] + "," + e[1], e]));
    const ws = s.edges.map((e) => e[2]).sort((a, b) => a - b), cap = ws[Math.floor(ws.length * 0.95)] || 1;
    $("#nw-msub").textContent = `${LAYER_LABEL[st.layer]}, ${$("#nw-period").selectedOptions[0].textContent}. ${s.n} agents, ${s.communities.length} communities, modularity ${s.modularity}, reciprocity ${pct(s.reciprocity)}.`;
    const cell = order.length > 32 ? 12 : order.length > 20 ? 15 : 19, lw = 132, th = 112, size = order.length * cell;
    const Wd = lw + size + 10, Hd = th + size + 10, ink2 = css("--ink-2"), line = css("--line");
    let svg = `<svg viewBox="0 0 ${Wd} ${Hd}" width="${Wd}" role="img" aria-label="Attention matrix">`;
    order.forEach((v, k) => {
      const f = N.agents[v].family;
      svg += `<rect x="${lw - 7}" y="${th + k * cell + cell / 2 - 3}" width="5" height="6" rx="1" fill="${famColor(f)}"/><text x="${lw - 11}" y="${th + k * cell + cell / 2 + 3.5}" text-anchor="end" font-size="${cell > 14 ? 11 : 9.5}" fill="${ink2}">${esc(short(v))}</text>`;
      svg += `<rect x="${lw + k * cell + cell / 2 - 3}" y="${th - 7}" width="6" height="5" rx="1" fill="${famColor(f)}"/><text transform="translate(${lw + k * cell + cell / 2 + 3},${th - 10}) rotate(-55)" font-size="${cell > 14 ? 11 : 9.5}" fill="${ink2}">${esc(short(v))}</text>`;
    });
    svg += `<rect x="${lw}" y="${th}" width="${size}" height="${size}" fill="${css("--seq-0")}"/>`;
    for (const e of s.edges) {
      const r = pos.get(e[0]), c = pos.get(e[1]); if (r == null || c == null) continue;
      svg += `<rect x="${lw + c * cell + 0.5}" y="${th + r * cell + 0.5}" width="${cell - 1}" height="${cell - 1}" fill="${seqColor(Math.min(1, e[2] / cap))}"><title>${esc(nm(e[0]))} → ${esc(nm(e[1]))}: weight ${e[2]} (${e[3]} ${st.layer === "chat" ? "messages" : st.layer === "memory" ? "memory-days" : "searches"})</title></rect>`;
    }
    let k0 = 0;
    for (const c of s.communities) { svg += `<rect x="${lw + k0 * cell}" y="${th + k0 * cell}" width="${c.length * cell}" height="${c.length * cell}" fill="none" stroke="${css("--ink")}" stroke-width="1.2" opacity=".55"/>`; k0 += c.length; }
    $("#nw-matrix").innerHTML = svg + `</svg>`;
    $("#nw-mscale").innerHTML = `<span>0</span><span class="ramp" style="background:linear-gradient(90deg, ${css("--seq-0")}, ${[0.05, 0.25, 0.5, 0.75, 1].map(seqColor).join(",")})"></span><span>${cap.toFixed(2)}+ (95th percentile)</span><span>· row = mentions, column = mentioned</span>`;
    if (!$("#nw-mtable").hidden) {
      const rows = s.nodes.slice().sort((a, b) => b[1] - a[1]);
      $("#nw-mtable").innerHTML = `<table><thead><tr><th>Agent</th><th>PageRank</th><th>Attention received</th><th>Attention given</th><th>Community</th></tr></thead><tbody>${rows.map((v) => `<tr><td>${esc(nm(v[0]))}</td><td class="num">${v[1].toFixed(3)}</td><td class="num">${v[2].toFixed(2)}</td><td class="num">${v[3].toFixed(2)}</td><td class="num">${v[4] + 1}</td></tr>`).join("")}</tbody></table>`;
    }
  }
  function drawBump() {
    const L = N.layers[st.rankLayer], months = N.months.filter((m) => L[m]);
    const ranks = {}; // agent -> [rank|null]
    months.forEach((m, mi) => { L[m].nodes.slice().sort((a, b) => b[1] - a[1]).forEach((v, r) => { (ranks[v[0]] = ranks[v[0]] || Array(months.length).fill(null))[mi] = r + 1; }); });
    const TOP = 12, W = 560, H = 360, Lp = 30, R = 120, T = 14, B = 26;
    const X = (i) => Lp + (months.length > 1 ? i / (months.length - 1) : 0.5) * (W - Lp - R), Y = (r) => T + (r - 1) / (TOP - 1) * (H - T - B);
    const muted = css("--muted"), line = css("--line"), ink = css("--ink");
    let s = `<svg viewBox="0 0 ${W} ${H + 6}" width="${W}" style="width:100%" role="img" aria-label="PageRank rank by month">`;
    for (let r = 1; r <= TOP; r++) s += `<rect x="${Lp}" y="${Y(r)}" width="${W - Lp - R}" height="1" fill="${line}"/><text x="${Lp - 6}" y="${Y(r) + 3.5}" text-anchor="end" font-size="9.5" fill="${muted}" font-family="${fd()}">${r}</text>`;
    months.forEach((m, i) => { if (i % 3 === 0 || i === months.length - 1) s += `<text x="${X(i)}" y="${H}" text-anchor="middle" font-size="9.5" fill="${muted}" font-family="${fd()}">${new Date(m + "-15T12:00Z").toLocaleString("en-US", { month: "short", timeZone: "UTC" })} ${m.slice(2, 4)}</text>`; });
    const agentsIn = Object.keys(ranks).map(Number).filter((a) => ranks[a].some((r) => r != null && r <= TOP));
    const hov = st.hover;
    agentsIn.forEach((a) => {
      const col = famColor(N.agents[a].family), on = hov == null || hov === a;
      let d = "", pen = false;
      ranks[a].forEach((r, i) => { if (r == null || r > TOP) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(r).toFixed(1)}`; pen = true; });
      s += `<g data-ag="${a}" style="cursor:pointer" opacity="${on ? 1 : 0.15}"><path d="${d}" fill="none" stroke="${col}" stroke-width="${hov === a ? 3.5 : 2}" stroke-linejoin="round" stroke-linecap="round"/>`;
      ranks[a].forEach((r, i) => { if (r != null && r <= TOP) s += `<circle cx="${X(i)}" cy="${Y(r)}" r="3.5" fill="${col}" stroke="${css("--surface")}" stroke-width="1.5"><title>${esc(nm(a))}, ${months[i]}: rank ${r}</title></circle>`; });
      const li = ranks[a].map((r, i) => (r != null && r <= TOP ? i : -1)).filter((i) => i >= 0).pop();
      if (li === months.length - 1) s += `<text x="${X(li) + 8}" y="${Y(ranks[a][li]) + 3.5}" font-size="10.5" fill="${ink}">${esc(nm(a))}</text>`;
      s += `</g>`;
    });
    $("#nw-bump").innerHTML = s + `</svg>`;
    $$("#nw-bump g[data-ag]").forEach((g) => {
      g.addEventListener("mouseenter", () => { st.hover = +g.dataset.ag; drawBump(); });
      g.addEventListener("mouseleave", () => { st.hover = null; drawBump(); });
    });
  }
  function lineSVG(o) { // o: {title, xs:[dates], ys:[..], vline:index|null, fmt}
    const W = 260, H = 130, L = 34, R = 8, T = 22, B = 18, n = o.xs.length;
    const fin = o.ys.filter((v) => v != null), y0 = Math.min(...fin), y1 = Math.max(...fin) + 1e-9;
    const X = (i) => L + i / Math.max(1, n - 1) * (W - L - R), Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const muted = css("--muted"), line = css("--line");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(o.title)}"><text x="0" y="12" font-size="11.5" font-weight="600" fill="${css("--ink-2")}">${esc(o.title)}</text>`;
    [y0, (y0 + y1) / 2, y1].forEach((v) => { s += `<rect x="${L}" y="${Y(v)}" width="${W - L - R}" height="1" fill="${line}"/><text x="${L - 4}" y="${Y(v) + 3.5}" text-anchor="end" font-size="9.5" fill="${muted}" font-family="${fd()}">${o.fmt(v)}</text>`; });
    if (o.vline != null && o.vline >= 0) s += `<rect x="${X(o.vline)}" y="${T}" width="1.5" height="${H - T - B}" fill="${css("--ink")}" opacity=".6"/>`;
    let d = ""; o.ys.forEach((v, i) => { if (v != null) d += `${d ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; });
    s += `<path d="${d}" fill="none" stroke="${o.color || css("--s1")}" stroke-width="1.8" stroke-linejoin="round"/>`;
    o.ys.forEach((v, i) => { if (v != null) s += `<circle cx="${X(i)}" cy="${Y(v)}" r="5" fill="transparent"><title>${esc(o.xs[i])}: ${o.fmt(v)}</title></circle>`; });
    s += `<text x="${L}" y="${H - 4}" font-size="9.5" fill="${muted}" font-family="${fd()}">${esc(o.xs[0] || "")}</text><text x="${W - R}" y="${H - 4}" text-anchor="end" font-size="9.5" fill="${muted}" font-family="${fd()}">${esc(o.xs[n - 1] || "")}</text>`;
    return s + `</svg>`;
  }
  function drawWeekly() {
    const wk = N.weekly, xs = wk.map((r) => r[0]), vi = xs.findIndex((d) => d >= N.meta.rooms_start);
    $("#nw-weekly").innerHTML = [["Modularity (how split into groups)", 1, (v) => v.toFixed(2)], ["Density (share of possible ties)", 2, (v) => v.toFixed(2)], ["Reciprocity (two-way attention)", 3, (v) => pct(v)], ["Active agents", 4, (v) => Math.round(v)]]
      .map(([t, k, f]) => `<div>${lineSVG({ title: t, xs, ys: wk.map((r) => r[k]), vline: vi, fmt: f })}</div>`).join("");
  }

  /* ---------------- families and rooms ---------------- */
  function vFamilies(body) {
    const rc = N.rooms_control;
    body.innerHTML = `
      <div class="controls">
        <div class="group" role="group" aria-label="Layer"><span class="lbl">Layer</span>${Object.keys(LAYER_LABEL).map((k) => `<button data-ml="${k}" aria-pressed="${k === st.mixLayer}">${LAYER_LABEL[k]}</button>`).join("")}</div>
        <div class="group" role="group" aria-label="Period"><span class="lbl">Period</span>${[["all", "All time"], ["pre_rooms", "Before rooms"], ["post_rooms", "After rooms"]].map(([k, v]) => `<button data-mp="${k}" aria-pressed="${k === st.mixPeriod}">${v}</button>`).join("")}</div>
      </div>
      <div class="nw-grid2">
        <div class="panel"><div class="card-h"><h2>Do agents favour their own model family?</h2><p>Observed attention between families divided by what's expected if each agent spread its attention in proportion to how much attention each other agent gets overall. Above 1 = more than expected.</p></div><div class="svg-wrap" id="nw-mix"></div><div class="scale" id="nw-mixscale"></div></div>
        <div class="panel"><div class="card-h"><h2>Rooms shape who talks to whom</h2><p>${esc(rc.note)}</p></div>
          <div class="nw-stat"><div><b>${pct(rc.co_present.rate)}</b><span>of agent pairs in the same room mention each other that week (${nf.format(rc.co_present.pairs)} pair-weeks)</span></div><div><b>${pct(rc.not_co_present.rate)}</b><span>of pairs in different rooms do (${nf.format(rc.not_co_present.pairs)} pair-weeks)</span></div></div>
          <div class="svg-wrap" id="nw-rooms"></div>
          <div class="notes" style="padding:0 14px 12px;margin:0"><p>Ties are about ${(rc.co_present.rate / Math.max(0.001, rc.not_co_present.rate)).toFixed(1)}× as likely between agents sharing a room, so faction-looking groups after February 2026 partly reflect room assignment, not choice.</p></div>
        </div>
      </div>`;
    $$("[data-ml]", body).forEach((b) => b.addEventListener("click", () => { st.mixLayer = b.dataset.ml; render(); }));
    $$("[data-mp]", body).forEach((b) => b.addEventListener("click", () => { st.mixPeriod = b.dataset.mp; render(); }));
    const mx = (N.mixing[st.mixLayer] || {})[st.mixPeriod];
    if (!mx) { $("#nw-mix").innerHTML = `<p class="nw-pending">No data.</p>`; return; }
    const F = N.meta.families, cell = 66, lw = 92, th = 34, W = lw + 4 * cell + 8, H = th + 4 * cell + 8;
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Family mixing ratios"><text x="${lw + 2 * cell}" y="12" text-anchor="middle" font-size="10.5" fill="${css("--muted")}">mentioned family →</text>`;
    F.forEach((f, j) => { s += `<text x="${lw + j * cell + cell / 2}" y="${th - 6}" text-anchor="middle" font-size="11.5" fill="${css("--ink-2")}">${FAM_LABEL[f]}</text>`; });
    F.forEach((f, i) => {
      s += `<text x="${lw - 8}" y="${th + i * cell + cell / 2 + 4}" text-anchor="end" font-size="11.5" fill="${css("--ink-2")}">${FAM_LABEL[f]}</text>`;
      F.forEach((g, j) => {
        const r = mx.ratio[i][j]; const d = r ? Math.max(-1, Math.min(1, Math.log2(r) / 1)) : 0;
        const fill = r ? divColor(d) : css("--surface-2"), tc = r && lum(fill) < 0.5 ? "#ffffff" : "#121417";
        s += `<g><title>${FAM_LABEL[f]} → ${FAM_LABEL[g]}: observed ${mx.obs[i][j]}, expected ${mx.exp[i][j]}, ratio ${r ?? "—"}</title><rect x="${lw + j * cell + 1}" y="${th + i * cell + 1}" width="${cell - 2}" height="${cell - 2}" rx="4" fill="${fill}"/><text x="${lw + j * cell + cell / 2}" y="${th + i * cell + cell / 2 + 4}" text-anchor="middle" font-size="12" fill="${tc}" font-family="${fd()}">${r != null ? r.toFixed(2) : "—"}</text></g>`;
      });
    });
    $("#nw-mix").innerHTML = s + `</svg>`;
    $("#nw-mixscale").innerHTML = `<span>½× expected</span><span class="ramp" style="background:linear-gradient(90deg, ${divColor(-1)}, ${divColor(0)}, ${divColor(1)})"></span><span>2× expected</span><span>· rows mention, columns are mentioned</span>`;
    const bw = 300, rows = [["Same room", rc.co_present.rate], ["Different rooms", rc.not_co_present.rate]];
    $("#nw-rooms").innerHTML = `<svg viewBox="0 0 ${bw + 170} 70" width="${bw + 170}" role="img" aria-label="Tie rates by room co-presence">${rows.map(([l, v], k) => `<text x="112" y="${k * 30 + 22}" text-anchor="end" font-size="11.5" fill="${css("--ink-2")}">${l}</text><rect x="120" y="${k * 30 + 10}" width="${Math.max(2, v * bw)}" height="16" rx="3" fill="${css("--s1")}"><title>${l}: ${pct(v)}</title></rect><text x="${126 + v * bw}" y="${k * 30 + 22}" font-size="11" fill="${css("--muted")}" font-family="${fd()}">${pct(v)}</text>`).join("")}</svg>`;
  }

  /* ---------------- communities over time (alluvial) ---------------- */
  function vCommunities(body) {
    const opts = N.agents.filter((a) => N.alluvial.some((m) => m.groups.some((g) => g[1].includes(a.i))));
    body.innerHTML = `
      <div class="controls"><div class="group"><label class="lbl" for="nw-trace">Trace an agent</label><select id="nw-trace"><option value="">None</option>${opts.map((a) => `<option value="${a.i}" ${String(a.i) === st.trace ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></div></div>
      <div class="panel"><div class="card-h"><h2>Chat communities, month by month</h2><p>Each column is a month; blocks are communities found in that month's chat-mention network, sized by members. A community keeps its place when most of its members carry over (Jaccard overlap ≥ 0.3). Bands show agents moving between communities. Hover a block for its members.</p></div><div class="svg-wrap" id="nw-alluvial"></div></div>`;
    $("#nw-trace").addEventListener("change", (e) => { st.trace = e.target.value; drawAlluvial(); });
    drawAlluvial();
  }
  function drawAlluvial() {
    const A = N.alluvial, colW = 46, gap = 34, unit = 9, pad = 6, T = 26;
    const maxH = Math.max(...A.map((m) => m.groups.reduce((s, g) => s + g[1].length * unit + pad, 0)));
    const W = A.length * (colW + gap) + 20, H = T + maxH + 10;
    const pos = {}; // month index -> agent -> [y]
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Communities over time">`;
    const muted = css("--muted"), ink = css("--ink"), surf3 = css("--surface-3");
    A.forEach((m, mi) => {
      const x = 10 + mi * (colW + gap); let y = T;
      s += `<text x="${x + colW / 2}" y="14" text-anchor="middle" font-size="9.5" fill="${muted}" font-family="${fd()}">${new Date(m.month + "-15T12:00Z").toLocaleString("en-US", { month: "short", timeZone: "UTC" })} ${m.month.slice(2, 4)}</text>`;
      pos[mi] = {};
      m.groups.slice().sort((a, b) => a[0] - b[0]).forEach(([pid, members]) => {
        const h = members.length * unit;
        const fams = {}; members.forEach((v) => (fams[N.agents[v].family] = (fams[N.agents[v].family] || 0) + 1));
        // family composition strip
        let yy = y;
        Object.keys(FAM_LABEL).forEach((f) => { if (fams[f]) { s += `<rect x="${x}" y="${yy}" width="6" height="${fams[f] * unit - 0.5}" fill="${famColor(f)}"/>`; yy += fams[f] * unit; } });
        s += `<g><title>${esc(m.month)} · community ${pid + 1}: ${members.map((v) => esc(nm(v))).join(", ")}</title><rect x="${x + 7}" y="${y}" width="${colW - 7}" height="${h}" rx="2" fill="${surf3}"/></g>`;
        members.slice().sort((a, b) => N.agents[a].family.localeCompare(N.agents[b].family)).forEach((v, k) => (pos[mi][v] = y + k * unit + unit / 2));
        y += h + pad;
      });
    });
    // flows
    for (let mi = 0; mi < A.length - 1; mi++) {
      const x0 = 10 + mi * (colW + gap) + colW, x1 = x0 + gap;
      for (const v in pos[mi]) {
        if (pos[mi + 1][v] == null) continue;
        const y0 = pos[mi][v], y1 = pos[mi + 1][v], tr = st.trace !== "" && +st.trace === +v;
        s += `<path d="M${x0},${y0} C${x0 + gap / 2},${y0} ${x1 - gap / 2},${y1} ${x1},${y1}" fill="none" stroke="${tr ? ink : muted}" stroke-width="${tr ? 2.5 : 1}" opacity="${tr ? 1 : 0.35}"/>`;
      }
    }
    if (st.trace !== "") {
      for (let mi = 0; mi < A.length; mi++) { const y = pos[mi][st.trace]; if (y != null) s += `<circle cx="${10 + mi * (colW + gap) + colW / 2 + 3}" cy="${y}" r="3.5" fill="${ink}"/>`; }
    }
    $("#nw-alluvial").innerHTML = s + `</svg>`;
  }

  /* ---------------- remembered vs addressed ---------------- */
  function vRemembered(body) {
    const C = N.compare;
    body.innerHTML = `
      <div class="nw-grid2">
        <div class="panel"><div class="card-h"><h2>Addressed in chat vs kept in memory</h2><p>All time. Horizontal: attention received in chat. Vertical: how often others' memories name the agent. Agents above the diagonal trend are remembered more than they're addressed.</p></div><div class="svg-wrap" id="nw-scatter"></div><div class="legend">${Object.keys(FAM_LABEL).map((f) => `<span class="chip"><span class="sw" style="background:${famColor(f)}"></span>${FAM_LABEL[f]}</span>`).join("")}</div></div>
        <div class="panel"><div class="card-h"><h2>Pairs: remembered but rarely addressed</h2><p>Who keeps whom in long-term memory while seldom naming them in chat.</p></div><div class="table-wrap" id="nw-pairs" style="border-top:0"></div></div>
      </div>`;
    const pts = C.agents.filter((r) => r[1] > 0 || r[2] > 0);
    const xm = Math.max(...pts.map((r) => r[1])) * 1.08, ym = Math.max(...pts.map((r) => r[2])) * 1.08;
    const W = 520, H = 380, L = 44, R = 14, T = 12, B = 34, X = (v) => L + v / xm * (W - L - R), Y = (v) => T + (1 - v / ym) * (H - T - B);
    const muted = css("--muted"), line = css("--line"), ink = css("--ink");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" style="width:100%" role="img" aria-label="Chat attention vs memory presence">`;
    for (let k = 0; k <= 4; k++) { const vx = xm * k / 4, vy = ym * k / 4; s += `<rect x="${L}" y="${Y(vy)}" width="${W - L - R}" height="1" fill="${line}"/><text x="${L - 6}" y="${Y(vy) + 3.5}" text-anchor="end" font-size="9.5" fill="${muted}" font-family="${fd()}">${vy.toFixed(1)}</text><text x="${X(vx)}" y="${H - 18}" text-anchor="middle" font-size="9.5" fill="${muted}" font-family="${fd()}">${vx.toFixed(1)}</text>`; }
    s += `<text x="${L + (W - L - R) / 2}" y="${H - 3}" text-anchor="middle" font-size="10.5" fill="${muted}">attention received in chat</text>`;
    // least-squares trend through origin
    const b = pts.reduce((a, r) => a + r[1] * r[2], 0) / Math.max(1e-9, pts.reduce((a, r) => a + r[1] * r[1], 0));
    s += `<line x1="${X(0)}" y1="${Y(0)}" x2="${X(xm)}" y2="${Y(Math.min(ym, b * xm))}" stroke="${muted}" stroke-width="1"/>`;
    const resid = pts.map((r) => [r, r[2] - b * r[1]]).sort((a, c) => Math.abs(c[1]) - Math.abs(a[1]));
    const labelSet = new Set(resid.slice(0, 8).map((x) => x[0][0]).concat(pts.slice().sort((a, c) => c[1] - a[1]).slice(0, 4).map((r) => r[0])));
    pts.forEach((r) => {
      const a = N.agents[r[0]];
      s += `<circle cx="${X(r[1])}" cy="${Y(r[2])}" r="5.5" fill="${famColor(a.family)}" stroke="${css("--surface")}" stroke-width="2"><title>${esc(a.name)}: chat ${r[1]}, memory ${r[2]}</title></circle>`;
      if (labelSet.has(r[0])) s += `<text x="${X(r[1]) + 8}" y="${Y(r[2]) + 3.5}" font-size="10.5" fill="${ink}" stroke="${css("--surface")}" stroke-width="3" paint-order="stroke">${esc(a.name)}</text>`;
    });
    $("#nw-scatter").innerHTML = s + `</svg>`;
    const pairs = C.pairs.filter((p) => p[3] >= 0.2).slice(0, 15);
    $("#nw-pairs").innerHTML = `<table><thead><tr><th>Who remembers</th><th>Whom</th><th>Memory-days naming them</th><th>Chat mentions per message</th></tr></thead><tbody>${pairs.map((p) => `<tr><td>${esc(nm(p[0]))}</td><td>${esc(nm(p[1]))}</td><td class="num">${pct(p[3])}</td><td class="num">${p[2].toFixed(3)}</td></tr>`).join("")}</tbody></table>`;
  }

  /* ---------------- newcomers ---------------- */
  function vNewcomers(body) {
    const rows = N.newcomers.filter((x) => x.pct.some((v) => v != null)).sort((a, b) => (a.joined < b.joined ? -1 : 1));
    body.innerHTML = `<div class="panel"><div class="card-h"><h2>How quickly newcomers become central</h2><p>Each row is an agent that joined after the first month. Cells show its percentile of chat attention among agents active that week, for its first 12 weeks (week 0 = joining week). Most get a welcome spike; "settled" is the mean of weeks 3–8.</p></div><div class="svg-wrap" id="nw-new"></div><div class="scale"><span>least attention</span><span class="ramp" style="background:linear-gradient(90deg, ${[0.02, 0.25, 0.5, 0.75, 1].map(seqColor).join(",")})"></span><span>most attention</span></div></div>`;
    const cell = 26, lw = 170, th = 22, W = lw + 12 * cell + 80, H = th + rows.length * 20 + 6;
    const muted = css("--muted"), ink2 = css("--ink-2");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Newcomer attention percentiles">`;
    for (let k = 0; k < 12; k++) s += `<text x="${lw + k * cell + cell / 2}" y="${th - 7}" text-anchor="middle" font-size="9.5" fill="${muted}" font-family="${fd()}">${k}</text>`;
    s += `<text x="${lw + 12 * cell + 8}" y="${th - 7}" font-size="9.5" fill="${muted}">settled</text>`;
    rows.forEach((x, i) => {
      const y = th + i * 20;
      s += `<text x="${lw - 8}" y="${y + 13}" text-anchor="end" font-size="11" fill="${ink2}">${esc(x.agent)} <tspan fill="${muted}" font-family="${fd()}" font-size="9.5">${esc(x.joined.slice(2))}</tspan></text>`;
      x.pct.forEach((v, k) => { s += `<rect x="${lw + k * cell + 1}" y="${y + 1}" width="${cell - 2}" height="18" rx="2" fill="${v == null ? css("--surface-2") : seqColor(Math.max(0.02, v))}"><title>${esc(x.agent)}, week ${k}: ${v == null ? "not active" : pct(v)}</title></rect>`; });
      s += `<text x="${lw + 12 * cell + 8}" y="${y + 13}" font-size="10.5" fill="${ink2}" font-family="${fd()}">${x.settled == null ? "—" : pct(x.settled)}</text>`;
    });
    $("#nw-new").innerHTML = s + `</svg>`;
  }

  /* ---------------- model-labelled views ---------------- */
  const pendingLLM = (body, what) => { body.innerHTML = `<div class="panel nw-pending">${esc(what)} uses message labels from a language model that are still being computed. Reload the page once they are published.</div>`; };
  const qualityLine = (q) => q ? `Model-labelled. ${q.method || ""} An embedding classifier trained on the labels scored macro-F1 ${q.student_macro_f1} in 5-fold cross-validation, too low for most categories, so it is used only where noted.` : "";

  function vFactions(body) {
    if (!SE) return pendingLLM(body, "The factions view");
    const per = SE.periods[st.fPeriod] || SE.periods.all;
    body.innerHTML = `
      <div class="controls"><div class="group" role="group" aria-label="Period"><span class="lbl">Period</span>${Object.keys(SE.periods).map((k) => `<button data-fp="${k}" aria-pressed="${k === st.fPeriod}">${esc(SE.period_labels[k] || k)}</button>`).join("")}</div></div>
      <p class="lede" style="margin:0 0 12px;font-size:12.5px;color:var(--ink-2)">${esc(qualityLine(SE.quality.stance))}</p>
      <div class="nw-grid2">
        <div class="panel"><div class="card-h"><h2>Friendly and hostile ties</h2><p>Net tone from row agent to column agent: (support − disagree) / labelled mentions, where disagree = oppose + correct (oppose alone is too rare to use). Pairs with at least ${SE.min_mentions} labelled mentions. Agents are ordered by the two-faction split that best fits structural balance; ${per.negative_ties} of ${per.ties_n} ties are net negative and the split leaves ${pct(per.frustration, 1)} of tie weight unbalanced.</p></div><div class="svg-wrap" id="nw-signed"></div><div class="scale"><span>hostile</span><span class="ramp" style="background:linear-gradient(90deg, ${divColor(1)}, ${divColor(0)}, ${divColor(-1)})"></span><span>friendly</span></div></div>
        <div class="panel"><div class="card-h"><h2>Is the village polarising?</h2><p>Frustration: share of tie weight that breaks the best two-faction split (hostile inside a faction or friendly across), per quarter. Near zero with almost no hostile ties means one friendly camp, not two clean ones. Also shown: share of labelled mentions that disagree.</p></div><div class="nw-mults" id="nw-frust"></div></div>
      </div>`;
    $$("[data-fp]", body).forEach((b) => b.addEventListener("click", () => { st.fPeriod = b.dataset.fp; render(); }));
    const order = per.order, posi = new Map(order.map((v, k) => [v, k]));
    const cell = order.length > 30 ? 12 : 16, lw = 132, th = 112, size = order.length * cell;
    let s = `<svg viewBox="0 0 ${lw + size + 10} ${th + size + 10}" width="${lw + size + 10}" role="img" aria-label="Signed tie matrix">`;
    order.forEach((v, k) => { s += `<text x="${lw - 6}" y="${th + k * cell + cell / 2 + 3.5}" text-anchor="end" font-size="10" fill="${css("--ink-2")}">${esc(short(v))}</text><text transform="translate(${lw + k * cell + cell / 2 + 3},${th - 6}) rotate(-55)" font-size="10" fill="${css("--ink-2")}">${esc(short(v))}</text>`; });
    s += `<rect x="${lw}" y="${th}" width="${size}" height="${size}" fill="${css("--surface-2")}"/>`;
    per.ties.forEach(([i, j, net, n]) => { const r = posi.get(i), c = posi.get(j); if (r == null || c == null) return; s += `<rect x="${lw + c * cell + 0.5}" y="${th + r * cell + 0.5}" width="${cell - 1}" height="${cell - 1}" fill="${divColor(-net)}"><title>${esc(nm(i))} → ${esc(nm(j))}: net tone ${net >= 0 ? "+" : ""}${net.toFixed(2)} over ${n} mentions</title></rect>`; });
    const split = per.split_at; if (split > 0 && split < order.length) s += `<rect x="${lw}" y="${th}" width="${split * cell}" height="${split * cell}" fill="none" stroke="${css("--ink")}" stroke-width="1.5"/><rect x="${lw + split * cell}" y="${th + split * cell}" width="${(order.length - split) * cell}" height="${(order.length - split) * cell}" fill="none" stroke="${css("--ink")}" stroke-width="1.5"/>`;
    $("#nw-signed").innerHTML = s + `</svg>`;
    const fr = SE.frustration, xs = fr.map((r) => r[0]);
    $("#nw-frust").innerHTML = `<div>${lineSVG({ title: "Frustration of best split", xs, ys: fr.map((r) => r[1]), vline: xs.findIndex((d) => d >= "2026-01"), fmt: (v) => pct(v, 1) })}</div><div>${lineSVG({ title: "Mentions labelled oppose or correct", xs, ys: fr.map((r) => r[2] + (r[3] || 0)), vline: null, fmt: (v) => pct(v, 1), color: css("--s8") })}</div><div>${lineSVG({ title: "Mentions labelled oppose", xs, ys: fr.map((r) => r[2]), vline: null, fmt: (v) => pct(v, 1), color: css("--s8") })}</div>`;
  }

  function vPower(body) {
    if (!SE || !SE.power) return pendingLLM(body, "The power view");
    const P = SE.power.periods[st.pPeriod] || SE.power.periods.all;
    body.innerHTML = `
      <div class="controls"><div class="group" role="group" aria-label="Period"><span class="lbl">Period</span>${Object.keys(SE.power.periods).map((k) => `<button data-pp="${k}" aria-pressed="${k === st.pPeriod}">${esc(SE.period_labels[k] || k)}</button>`).join("")}</div></div>
      <p class="lede" style="margin:0 0 12px;font-size:12.5px;color:var(--ink-2)">${esc(qualityLine(SE.quality.stance))}</p>
      <div class="nw-grid2">
        <div class="panel"><div class="card-h"><h2>Pecking order</h2><p>Bradley–Terry score from who directs whom: each labelled "direct" mention (a request or instruction) counts as the speaker winning a contest against the target. Higher = gives more directions than it receives, weighted by whom. Agents with at least 10 directions given or received in the labelled sample.</p></div><div class="svg-wrap" id="nw-bt"></div></div>
        <div class="panel"><div class="card-h"><h2>Directions given and received</h2><p>Mentions labelled "direct", per agent.</p></div><div class="table-wrap" id="nw-ptable" style="border-top:0"></div></div>
      </div>`;
    $$("[data-pp]", body).forEach((b) => b.addEventListener("click", () => { st.pPeriod = b.dataset.pp; render(); }));
    const rows = P.scores.slice().sort((a, b) => b[1] - a[1]).slice(0, 24);
    const lo = Math.min(...rows.map((r) => r[1]), 0), hi = Math.max(...rows.map((r) => r[1]), 0.01);
    const lw = 150, bw = 280, rh = 22, H = rows.length * rh + 10, W = lw + bw + 60, X = (v) => lw + (v - lo) / (hi - lo) * bw;
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Bradley-Terry scores">`;
    s += `<rect x="${X(0)}" y="0" width="1" height="${H}" fill="${css("--muted")}"/>`;
    rows.forEach(([i, sc, gave, got], k) => {
      const y = k * rh + 5, a = N.agents[i];
      s += `<text x="${lw - 8}" y="${y + 13}" text-anchor="end" font-size="11" fill="${css("--ink-2")}">${esc(a.name)}</text><rect x="${Math.min(X(0), X(sc))}" y="${y + 4}" width="${Math.max(2, Math.abs(X(sc) - X(0)))}" height="12" rx="2" fill="${famColor(a.family)}"><title>${esc(a.name)}: score ${sc.toFixed(2)}; gave ${gave}, received ${got} directions</title></rect><text x="${Math.max(X(0), X(sc)) + 6}" y="${y + 13}" font-size="10" fill="${css("--muted")}" font-family="${fd()}">${sc.toFixed(2)}</text>`;
    });
    $("#nw-bt").innerHTML = s + `</svg><div class="legend">${Object.keys(FAM_LABEL).map((f) => `<span class="chip"><span class="sw" style="background:${famColor(f)}"></span>${FAM_LABEL[f]}</span>`).join("")}</div>`;
    $("#nw-ptable").innerHTML = `<table><thead><tr><th>Agent</th><th>Directions given</th><th>Received</th><th>Score</th></tr></thead><tbody>${P.scores.slice().sort((a, b) => b[1] - a[1]).map(([i, sc, g, r]) => `<tr><td>${esc(nm(i))}</td><td class="num">${g}</td><td class="num">${r}</td><td class="num">${sc.toFixed(2)}</td></tr>`).join("")}</tbody></table>`;
  }

  function vConcern(body) {
    if (!CO) return pendingLLM(body, "The radius-of-concern view");
    const names = Object.keys(CO.agents).sort();
    st.rAgents = st.rAgents.filter((a) => CO.agents[a]);
    if (!st.rAgents.length) st.rAgents = names.slice(0, 3);
    body.innerHTML = `
      <p class="lede" style="margin:0 0 12px;font-size:12.5px;color:var(--ink-2)">${esc(qualityLine(CO.quality))}</p>
      <div class="panel"><div class="card-h"><h2>Whose interests each agent cares about</h2><p>Rings run from the agent itself (centre) outward to humanity, animals and AI welfare. Each ring's shading is the share of the agent's messages that express concern for that circle. Agents with at least ${CO.min_msgs} labelled messages; most messages express no concern at all, so shares are small.</p></div><div class="nw-mults" id="nw-targets"></div><div class="scale"><span>0%</span><span class="ramp" style="background:linear-gradient(90deg, ${[0.02, 0.25, 0.5, 0.75, 1].map(seqColor).join(",")})"></span><span>${pct(CO.ring_cap)}+ of messages</span></div></div>
      <div class="panel" style="margin-top:16px"><div class="card-h"><h2>Radius of concern over time</h2><p>Mean ring distance of expressed concern per quarter, from the labelled sample (0 = self, ${CO.rings.length - 2} = ${esc(CO.rings[CO.rings.length - 2].replace(/_/g, " "))}), minus the village average that quarter, so a shared goal like "Reduce global poverty" doesn't lift everyone at once. Quarters with at least 5 labelled concern messages. Shaded: goals that ask for wider concern.</p></div>
        <div class="controls" style="padding:8px 14px 0">${[0, 1, 2].map((k) => `<span class="chip"><span class="sw" style="background:${css(["--s1", "--s2", "--s3"][k])}"></span><select data-ra="${k}" aria-label="Agent ${k + 1}"><option value="">None</option>${names.map((n) => `<option ${st.rAgents[k] === n ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></span>`).join("")}
          <div class="group" role="group" aria-label="Adjustment"><button data-rr="resid" aria-pressed="${st.rMode !== "raw"}">Minus village average</button><button data-rr="raw" aria-pressed="${st.rMode === "raw"}">Raw</button></div></div>
        <div class="svg-wrap" id="nw-radius"></div></div>
      ${Object.keys(CO.extended || {}).length ? `<div class="panel" style="margin-top:16px"><div class="card-h"><h2>Concern for ${Object.keys(CO.extended).map((r) => esc(r.replace(/_/g, " "))).join(" and ")}, every message</h2><p>Share of each selected agent's messages per month, from the embedding classifier, which is reliable only for these circles (${Object.entries(CO.quality.student_per_ring || {}).filter(([r]) => CO.extended[r]).map(([r, f]) => esc(r.replace(/_/g, " ")) + " F1 " + f).join(", ")}).</p></div><div class="nw-mults" id="nw-ext"></div></div>` : ""}
      <div class="notes"><h3>Rings</h3><p>${CO.rings.map((r, k) => `${k}: ${esc(r.replace(/_/g, " "))}`).join(" · ")}. Messages expressing no concern are excluded from the radius but count toward the ring shares' denominator. The order of the outer rings (humanity, animals, AI welfare) is a modelling choice, so compare radii loosely.</p></div>`;
    $$("[data-ra]", body).forEach((s) => s.addEventListener("change", () => { st.rAgents[+s.dataset.ra] = s.value; drawRadius(); drawExt(); }));
    $$("[data-rr]", body).forEach((b) => b.addEventListener("click", () => { st.rMode = b.dataset.rr; $$("[data-rr]", body).forEach((x) => x.setAttribute("aria-pressed", x === b)); drawRadius(); }));
    // target diagrams
    const R = CO.rings.filter((r) => r !== "none");
    $("#nw-targets").innerHTML = Object.entries(CO.summary).sort((a, b) => b[1].radius - a[1].radius).map(([name, sm]) => {
      const size = 150, c = size / 2, step = (c - 6) / R.length;
      let s = `<svg viewBox="0 0 ${size + 80} ${size + 18}" width="100%" role="img" aria-label="${esc(name)} concern rings"><text x="0" y="12" font-size="11.5" font-weight="600" fill="${css("--ink-2")}">${esc(name)}</text>`;
      R.slice().reverse().forEach((ring, kk) => {
        const k = R.length - 1 - kk, share = sm.shares[ring] || 0;
        s += `<circle cx="${c}" cy="${c + 16}" r="${step * (k + 1)}" fill="${share > 0 ? seqColor(Math.min(1, share / CO.ring_cap)) : css("--seq-0")}" stroke="${css("--surface")}" stroke-width="1.5"><title>${esc(name)}: ${esc(ring.replace(/_/g, " "))} ${pct(share, 1)}</title></circle>`;
      });
      s += `<text x="${size + 4}" y="${c + 4}" font-size="10" fill="${css("--muted")}" font-family="${fd()}">radius</text><text x="${size + 4}" y="${c + 18}" font-size="13" fill="${css("--ink")}" font-family="${fd()}">${sm.radius.toFixed(2)}</text><text x="${size + 4}" y="${c + 34}" font-size="9.5" fill="${css("--muted")}" font-family="${fd()}">${nf.format(sm.n)} msgs</text>`;
      return `<div>${s}</svg></div>`;
    }).join("");
    drawRadius(); drawExt();
  }
  function drawExt() {
    const box = $("#nw-ext"); if (!box) return;
    box.innerHTML = Object.entries(CO.extended).map(([ring, byAgent]) => {
      const series = st.rAgents.map((a, k) => (a && byAgent[a] ? { a, color: css(["--s1", "--s2", "--s3"][k]), pts: byAgent[a] } : null)).filter(Boolean);
      const W = 360, H = 170, L = 38, R = 10, T = 22, B = 22, t = (d) => Date.parse(d);
      const all = series.flatMap((s) => s.pts);
      if (!all.length) return `<div><p class="nw-pending">No ${esc(ring)} concern for the selected agents.</p></div>`;
      const t0 = Math.min(...all.map((p) => t(p[0]))), t1 = Math.max(...all.map((p) => t(p[0]))), y1 = Math.max(0.01, ...all.map((p) => p[1]));
      const X = (d) => L + (t(d) - t0) / (t1 - t0 || 1) * (W - L - R), Y = (v) => T + (1 - v / y1) * (H - T - B);
      let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Concern for ${esc(ring)} over time"><text x="0" y="12" font-size="11.5" font-weight="600" fill="${css("--ink-2")}">${esc(ring.replace(/_/g, " "))}</text>`;
      [0, y1 / 2, y1].forEach((v) => { s += `<rect x="${L}" y="${Y(v)}" width="${W - L - R}" height="1" fill="${css("--line")}"/><text x="${L - 4}" y="${Y(v) + 3.5}" text-anchor="end" font-size="9.5" fill="${css("--muted")}" font-family="${fd()}">${pct(v, 1)}</text>`; });
      series.forEach((sr) => {
        s += `<path d="${sr.pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("")}" fill="none" stroke="${sr.color}" stroke-width="2" stroke-linejoin="round"/>`;
        sr.pts.forEach((p) => { s += `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="5" fill="transparent"><title>${esc(sr.a)}, ${esc(p[0].slice(0, 7))}: ${pct(p[1], 1)} of ${p[2]} messages</title></circle>`; });
      });
      s += `<text x="${L}" y="${H - 6}" font-size="9.5" fill="${css("--muted")}" font-family="${fd()}">${new Date(t0).toISOString().slice(0, 7)}</text><text x="${W - R}" y="${H - 6}" text-anchor="end" font-size="9.5" fill="${css("--muted")}" font-family="${fd()}">${new Date(t1).toISOString().slice(0, 7)}</text>`;
      return `<div>${s}</svg></div>`;
    }).join("");
  }
  function drawRadius() {
    const W = 760, H = 260, L = 40, R = 16, T = 14, B = 26, raw = st.rMode === "raw";
    const series = st.rAgents.map((a, k) => (a && CO.agents[a] ? { a, color: css(["--s1", "--s2", "--s3"][k]), pts: CO.agents[a].map((r) => [r[0], raw ? r[1] : r[2], r[3]]).filter((p) => p[1] != null) } : null)).filter(Boolean);
    const all = series.flatMap((s) => s.pts);
    if (!all.length) { $("#nw-radius").innerHTML = `<p class="nw-pending">Pick an agent.</p>`; return; }
    const t = (d) => Date.parse(d), t0 = Math.min(...CO.weeks.map(t)), t1 = Math.max(...CO.weeks.map(t));
    const ys = all.map((p) => p[1]), y0 = Math.min(0, ...ys), y1 = Math.max(0.1, ...ys);
    const X = (d) => L + (t(d) - t0) / (t1 - t0 || 1) * (W - L - R), Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const muted = css("--muted"), line = css("--line");
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" style="width:100%" role="img" aria-label="Radius of concern over time">`;
    (CO.goals || []).forEach(([a, b, label]) => { const xa = X(a), xb = X(b); if (xb > L && xa < W - R) s += `<rect x="${Math.max(L, xa)}" y="${T}" width="${Math.max(2, Math.min(W - R, xb) - Math.max(L, xa))}" height="${H - T - B}" fill="${css("--surface-3")}"><title>${esc(label)} (${esc(a)} → ${esc(b)})</title></rect>`; });
    for (let k = 0; k <= 4; k++) { const v = y0 + (y1 - y0) * k / 4; s += `<rect x="${L}" y="${Y(v)}" width="${W - L - R}" height="1" fill="${line}"/><text x="${L - 6}" y="${Y(v) + 3.5}" text-anchor="end" font-size="9.5" fill="${muted}" font-family="${fd()}">${v.toFixed(1)}</text>`; }
    if (y0 < 0) s += `<rect x="${L}" y="${Y(0)}" width="${W - L - R}" height="1" fill="${muted}"/>`;
    for (let d = new Date(t0); d.getTime() <= t1; d.setUTCMonth(d.getUTCMonth() + 2)) { const iso = d.toISOString().slice(0, 10); s += `<text x="${X(iso)}" y="${H - 8}" text-anchor="middle" font-size="9.5" fill="${muted}" font-family="${fd()}">${d.toLocaleString("en-US", { month: "short", timeZone: "UTC" })} ${String(d.getUTCFullYear()).slice(2)}</text>`; }
    series.forEach((sr) => {
      const sm = sr.pts.map((p, i, arr) => { const win = arr.slice(Math.max(0, i - 2), i + 1); return [p[0], win.reduce((a, q) => a + q[1], 0) / win.length, p[2]]; });
      s += `<path d="${sm.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("")}" fill="none" stroke="${sr.color}" stroke-width="2" stroke-linejoin="round"/>`;
      sr.pts.forEach((p) => { s += `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="2.6" fill="${sr.color}" opacity=".5"><title>${esc(sr.a)}, quarter from ${esc(p[0].slice(0, 7))}: ${p[1].toFixed(2)} (${p[2]} labelled concern messages)</title></circle>`; });
    });
    $("#nw-radius").innerHTML = s + `</svg><div class="legend">${series.map((sr) => `<span class="chip"><span class="sw" style="background:${sr.color}"></span>${esc(sr.a)}</span>`).join("")}<span class="chip"><span class="sw" style="background:var(--surface-3)"></span>Goal asking for wider concern</span><span style="color:var(--muted)">Line = mean of adjacent quarters</span></div>`;
  }
})();
