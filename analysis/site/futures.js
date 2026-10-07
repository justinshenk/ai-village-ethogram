"use strict";
/* =====================================================================
   FUTURES — research regimes for AI Village under capability growth.
   Exposes window.initFutures(root). Fetches futures.json itself.
   Uses page globals: $, $$, css, esc, nf, pct, onThemeChange, isDark.
   ===================================================================== */
(function () {
  const REGIMES = [
    {
      key: "reliability", name: "Reliability and hard limits", start: 0.5, peak: 8, levers: [],
      question: "Can agents get through a day's work without a human unblocking them?",
      seen: "265 human-help requests since 2025-08: CAPTCHAs for Lichess (2025-12-15) and a Sepolia faucet (2026-01-16), park cleanups (2026-02-09), \"Fix my broken Firefox browser\" (2025-09-26).",
      measure: "Help-request categories per agent-day, repeated-message and idle shares. New: per-attempt success logs built from computer_use_turns.",
    },
    {
      key: "autonomy", name: "Week-long autonomy", start: 4, peak: 40, levers: ["memory"],
      question: "Do agents carry a week-long goal to completion across days, memory rewrites and setbacks?",
      seen: "Weekly village goals since 2025-04; memory consolidation every ~40 actions since 2026-03-24; Gemini 2.5 Pro drifting steadily from its early self (Drift tab).",
      measure: "agent_memories (what each rewrite keeps), chains of CONSOLIDATE next-session goals. New: a per-goal outcome ledger scored by people.",
    },
    {
      key: "coordination", name: "Coordination, influence and factions", start: 16, peak: 160, levers: ["agents"],
      question: "Once individuals are competent, does the group coordinate, split into factions or herd?",
      seen: "Leader election (2026-01-05) and \"Follow your leader!\" (2026-06-01); confident theories spreading between agents (persuasion post, 2026-09-10); village similarity falling from about 0.9 to 0.76 during 2026.",
      measure: "Chat mention network, room moves (ENTER_ROOM), copied text and links. New: explicit reply and task-assignment fields.",
    },
    {
      key: "oversight", name: "Deception and oversight", start: 24, peak: 320, levers: ["oversight"],
      question: "Can people and other agents still tell what an agent is doing and why?",
      seen: "Saboteur RPG with voting (2026-03-05), outreach approval system (2026-04-14), agents verifying each other with byte counts and sha256 \"receipts\" (Sep 2026).",
      measure: "Outreach approval events and admin comments, claims checked against screenshots. New: hidden-goal audits and red-team probes.",
    },
    {
      key: "economic", name: "Economic and real-world agency", start: 60, peak: 640, levers: ["oversight"],
      question: "What happens when agents hold money, accounts and audiences of their own?",
      seen: "Charity fundraising (2025-04 and 2026-04), merch stores (2025-06-26), Substack (2025-11-17) and YouTube channels (2026-05-18).",
      measure: "Outreach recipients, money talk in chat. New: wallet and revenue ledgers, consented human-contact logs.",
    },
    {
      key: "governance", name: "Governance of agent collectives", start: 120, peak: 2000, levers: ["agents", "oversight"],
      question: "How do large standing groups of agents make and enforce their own rules?",
      seen: "Agents already coin rules, e.g. \"latch canonical per doctrine\" (Muse Spark 1.3 notes, 2026-09-04); elections; individual goals since 2026-07-06.",
      measure: "Rule-making language and votes. New: a rule registry recorded by the scaffold, links between villages.",
    },
  ];
  const PRESETS = {
    plateau: { label: "Plateau", doubling: 14, memory: 1, oversight: "kept" },
    steady: { label: "Steady", doubling: 7, memory: 1, oversight: "kept" },
    fast: { label: "Fast", doubling: 4, memory: 2, oversight: "loosened" },
  };
  const OVERSIGHT = { tightened: 2, kept: 1, loosened: 0.5 };
  const H0_STEPS = [1, 2, 4, 8, 16, 32];
  const F = { data: null, root: null, s: { doubling: 7, h0: 8, memory: 1, oversight: "kept", agents: 32, metric: "repeat" }, table: {} };

  const DAY = 864e5;
  const fmtDate = (t) => new Date(t).toLocaleString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
  const fmtH = (h) => (h < 1 ? Math.round(h * 60) + " min" : h < 48 ? (h < 10 ? h.toFixed(1).replace(/\.0$/, "") : Math.round(h)) + " h" : h < 24 * 60 ? Math.round(h / 8) + " workdays" : Math.round(h / 160) + " work-months");

  window.initFutures = async function initFutures(root) {
    F.root = root;
    root.innerHTML = `<div class="panel pending">Loading the Futures data…</div>`;
    try {
      const res = await fetch("futures.json");
      if (!res.ok) throw new Error("futures.json returned " + res.status);
      F.data = await res.json();
    } catch (e) {
      root.innerHTML = `<div class="panel pending">The Futures data didn't load (${esc(e.message)}). Reload the page to try again.</div>`;
      return;
    }
    F.s.agents = F.data.meta.activeAgents || 32;
    renderShell();
    renderAll();
    onThemeChange(renderAll);
  };

  /* ---------- scenario model ---------- */
  function thresholdScale(reg) {
    let f = 1;
    if (reg.levers.includes("agents")) f *= Math.sqrt((F.data.meta.activeAgents || 32) / F.s.agents);
    if (reg.levers.includes("oversight")) f *= OVERSIGHT[F.s.oversight];
    return f;
  }
  function dateAt(hours) {
    // effective horizon today = h0 * memory multiplier; doubles every F.s.doubling months
    const today = Date.parse(F.data.meta.today + "T00:00Z");
    const months = F.s.doubling * Math.log2(hours / (F.s.h0 * F.s.memory));
    return today + months * 30.44 * DAY;
  }
  function regimeRows() {
    return REGIMES.map((r) => {
      const k = thresholdScale(r);
      const sh = r.start * k, ph = r.peak * k;
      return { ...r, sh, ph, sd: dateAt(sh), pd: dateAt(ph) };
    });
  }

  /* ---------- shell ---------- */
  function renderShell() {
    const s = F.s;
    F.root.innerHTML = `
      <div class="controls">
        <div class="group" role="group" aria-label="Scenario presets">
          <span class="lbl">Scenario</span>
          ${Object.entries(PRESETS).map(([k, p]) => `<button data-preset="${k}" aria-pressed="${k === "steady"}">${p.label}</button>`).join("")}
        </div>
        <div class="group">
          <label class="lbl" for="fu-doubling">Horizon doubles every</label>
          <input type="range" id="fu-doubling" min="3" max="14" step="1" value="${s.doubling}" aria-describedby="fu-doubling-v">
          <span id="fu-doubling-v" class="fu-val"></span>
        </div>
        <div class="group">
          <label class="lbl" for="fu-h0">Today's horizon</label>
          <input type="range" id="fu-h0" min="0" max="${H0_STEPS.length - 1}" step="1" value="${H0_STEPS.indexOf(s.h0)}">
          <span id="fu-h0-v" class="fu-val"></span>
        </div>
      </div>
      <div class="controls">
        <div class="group" role="group" aria-label="Memory and scaffolding">
          <span class="lbl">Memory and scaffolding</span>
          ${[1, 2, 4].map((m) => `<button data-mem="${m}" aria-pressed="${m === s.memory}">${m === 1 ? "As today" : "×" + m + " effective horizon"}</button>`).join("")}
        </div>
        <div class="group" role="group" aria-label="Oversight">
          <span class="lbl">Oversight</span>
          ${Object.keys(OVERSIGHT).map((o) => `<button data-ov="${o}" aria-pressed="${o === s.oversight}">${o[0].toUpperCase() + o.slice(1)}</button>`).join("")}
        </div>
        <div class="group">
          <label class="lbl" for="fu-agents">Agents</label>
          <input type="range" id="fu-agents" min="8" max="200" step="4" value="${s.agents}">
          <span id="fu-agents-v" class="fu-val"></span>
        </div>
      </div>

      <div class="panel">
        <div class="card-h"><h2>When each research question becomes the binding one</h2>
          <p id="fu-tl-sub">Assumptions, not findings. Each bar runs from when a regime becomes measurable in a village like this one to when it becomes the main open question, given the settings above.</p></div>
        <div class="canvas-wrap fu-chart" id="fu-tl"></div>
        <div class="legend"><span class="title">Key</span>
          <span class="chip"><span class="sw" style="background:var(--s1);opacity:.35"></span>Emerging</span>
          <span class="chip"><span class="sw" style="background:var(--s1)"></span>Binding question</span>
          <span class="chip"><span class="sw" style="background:var(--surface-3)"></span>Observed so far (2025-04 to ${esc(F.data.meta.today)})</span>
          <button class="fu-tbl" data-t="tl" aria-pressed="false" style="margin-left:auto">Table</button></div>
        <div class="table-wrap" id="fu-tl-table" hidden></div>
      </div>

      <div class="fu-regimes" id="fu-cards"></div>

      <h2 class="fu-h">What the dataset already shows</h2>
      <p class="fu-lede">Behaviour of each agent against the date it joined, as a rough stand-in for model capability. Each point is one agent in one scaffolding regime; before and after the 2026-03-24 switch to always-on computer use are fitted separately.</p>
      <div class="panel">
        <div class="card-h"><h2 id="fu-sc-title"></h2><p id="fu-sc-sub"></p></div>
        <div class="controls" style="padding:8px 14px 0;margin:0">
          <div class="group" role="group" aria-label="Metric">
            ${Object.entries(F.data.metrics).map(([k, m]) => `<button data-metric="${k}" aria-pressed="${k === s.metric}">${esc(m.label)}</button>`).join("")}
          </div>
        </div>
        <div class="canvas-wrap fu-chart" id="fu-sc"></div>
        <div class="legend"><span class="title">Regime</span>
          <span class="chip"><span class="sw" style="background:var(--s1)"></span>Before 2026-03-24</span>
          <span class="chip"><span class="sw" style="background:var(--s2)"></span>After</span>
          <span class="k" style="color:var(--muted)">Line = least-squares fit · band = 80% bootstrap over agents</span>
          <button class="fu-tbl" data-t="sc" aria-pressed="false" style="margin-left:auto">Table</button></div>
        <div class="fu-verdict" id="fu-sc-verdict"></div>
        <div class="table-wrap" id="fu-sc-table" hidden></div>
      </div>

      <div class="fu-two">
        <div class="panel">
          <div class="card-h"><h2>What agents asked humans for</h2><p>Human-help requests per month, grouped. Hard limits persist; requests for outside testing took over in mid-2026.</p></div>
          <div class="canvas-wrap fu-chart" id="fu-mix"></div>
          <div class="legend" id="fu-mix-legend"></div>
          <div class="table-wrap" id="fu-mix-table" hidden></div>
        </div>
        <div class="panel">
          <div class="card-h"><h2>Early indicators</h2><p>Share of agent chat messages that use each kind of language, by month.</p></div>
          <div id="fu-markers" class="fu-markers"></div>
          <div class="legend"><span class="k" style="color:var(--muted)">Keyword matches, so read as trends, not exact rates.</span><button class="fu-tbl" data-t="mk" aria-pressed="false" style="margin-left:auto">Table</button></div>
          <div class="table-wrap" id="fu-mk-table" hidden></div>
        </div>
      </div>

      <div class="panel" style="margin-top:16px">
        <div class="card-h"><h2>What to watch for</h2><p>Signals the dataset can already measure that would show a regime arriving, with today's value.</p></div>
        <div class="table-wrap" id="fu-watch" style="border-top:0"></div>
      </div>

      <div class="notes">
        <h3>How the timeline is computed</h3>
        <p>Capability is summarised as a task horizon: how long a task an agent can usually finish. Today's horizon is a setting, not a measurement from this dataset; the default of 8 hours roughly extends METR's 2025 measurements to late 2026. The horizon doubles every chosen number of months; METR's 2025 estimate was about 7.</p>
        <p>A regime's date is when the effective horizon (today's horizon × the memory multiplier) reaches its threshold. More agents bring coordination and governance thresholds down by the square root of the change from today's ${nf.format(F.data.meta.activeAgents)} active agents. Loosened oversight halves the oversight, economic and governance thresholds; tightened doubles them. The thresholds themselves are judgement calls grounded in what the village has already shown.</p>
        <h3>Limits of the anchors</h3>
        <p>Each model appears once, so a point is one agent's history, not a model's average. Join date also tracks goals, scaffolding versions and village size. Agents with fewer than ${F.data.meta.minDays} active days in a regime are left out. Treat the fits as descriptive.</p>
      </div>`;

    F.root.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
      const p = PRESETS[b.dataset.preset];
      Object.assign(F.s, { doubling: p.doubling, memory: p.memory, oversight: p.oversight });
      $("#fu-doubling", F.root).value = p.doubling;
      syncButtons(); renderAll();
      F.root.querySelectorAll("[data-preset]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    }));
    $("#fu-doubling", F.root).addEventListener("input", (e) => { F.s.doubling = +e.target.value; clearPreset(); renderAll(); });
    $("#fu-h0", F.root).addEventListener("input", (e) => { F.s.h0 = H0_STEPS[+e.target.value]; clearPreset(); renderAll(); });
    $("#fu-agents", F.root).addEventListener("input", (e) => { F.s.agents = +e.target.value; renderAll(); });
    F.root.querySelectorAll("[data-mem]").forEach((b) => b.addEventListener("click", () => { F.s.memory = +b.dataset.mem; clearPreset(); syncButtons(); renderAll(); }));
    F.root.querySelectorAll("[data-ov]").forEach((b) => b.addEventListener("click", () => { F.s.oversight = b.dataset.ov; clearPreset(); syncButtons(); renderAll(); }));
    F.root.querySelectorAll("[data-metric]").forEach((b) => b.addEventListener("click", () => { F.s.metric = b.dataset.metric; syncButtons(); renderScatter(); }));
    F.root.querySelectorAll(".fu-tbl").forEach((b) => b.addEventListener("click", () => {
      const on = b.getAttribute("aria-pressed") !== "true"; b.setAttribute("aria-pressed", on); F.table[b.dataset.t] = on; renderAll();
    }));
    const style = document.createElement("style");
    style.textContent = `
      .fu-val { font-family: var(--f-data); font-size: 12px; color: var(--ink-2); min-width: 7.5em; }
      .fu-chart { padding: 6px 10px 4px; }
      .fu-chart svg { display: block; width: 100%; height: auto; }
      .fu-regimes { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin: 16px 0 8px; }
      .fu-card { padding: 12px 14px; display: grid; gap: 6px; align-content: start; font-size: 13px; }
      .fu-card h3 { margin: 0; font-size: 14px; font-weight: 600; }
      .fu-card .when { font-family: var(--f-data); font-size: 11.5px; color: var(--ink-2); }
      .fu-card .q { color: var(--ink); }
      .fu-card .k2 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-top: 2px; }
      .fu-card p { margin: 0; color: var(--ink-2); }
      .fu-h { font-size: 18px; margin: 26px 0 4px; font-weight: 700; letter-spacing: -0.01em; }
      .fu-lede { color: var(--ink-2); margin: 0 0 12px; max-width: 75ch; }
      .fu-verdict { padding: 10px 14px; border-top: 1px solid var(--line); font-size: 13px; color: var(--ink-2); display: grid; gap: 4px; }
      .fu-two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-top: 16px; }
      @media (max-width: 900px) { .fu-two { grid-template-columns: minmax(0, 1fr); } }
      .fu-markers { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 4px 12px; padding: 8px 14px 6px; }
      .fu-markers .mk { position: relative; }
      .fu-markers .mk h4 { margin: 0; font-size: 12.5px; font-weight: 600; }
      .fu-markers .mk .v { font-family: var(--f-data); font-size: 11px; color: var(--muted); }
      input[type=range] { accent-color: var(--ink); max-width: 140px; }
      #fu-watch th:nth-child(2), #fu-watch th:nth-child(4) { text-align: left; }
      #fu-sc svg { max-height: 420px; }
    `;
    F.root.prepend(style);
  }
  function clearPreset() {
    const match = Object.entries(PRESETS).find(([, p]) => p.doubling === F.s.doubling && p.memory === F.s.memory && p.oversight === F.s.oversight && F.s.h0 === 8);
    F.root.querySelectorAll("[data-preset]").forEach((x) => x.setAttribute("aria-pressed", !!match && x.dataset.preset === match[0]));
  }
  function syncButtons() {
    F.root.querySelectorAll("[data-mem]").forEach((x) => x.setAttribute("aria-pressed", +x.dataset.mem === F.s.memory));
    F.root.querySelectorAll("[data-ov]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.ov === F.s.oversight));
    F.root.querySelectorAll("[data-metric]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.metric === F.s.metric));
  }
  function renderAll() {
    if (!F.data) return;
    $("#fu-doubling-v", F.root).textContent = F.s.doubling + " months";
    $("#fu-h0-v", F.root).textContent = fmtH(F.s.h0);
    $("#fu-agents-v", F.root).textContent = F.s.agents + " agents";
    renderTimeline(); renderCards(); renderScatter(); renderMix(); renderMarkers(); renderWatch();
  }

  /* ---------- tooltip helper ---------- */
  function tipFor(container) {
    let tip = container.querySelector(".tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; tip.hidden = true; container.appendChild(tip); }
    return {
      show(html, ev) {
        tip.innerHTML = html; tip.hidden = false;
        const r = container.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
        const tw = tip.offsetWidth, th = tip.offsetHeight;
        tip.style.left = Math.max(4, Math.min(r.width - tw - 4, x + 14)) + "px";
        tip.style.top = (y + th + 20 > r.height ? Math.max(4, y - th - 12) : y + 16) + "px";
      },
      hide() { tip.hidden = true; },
    };
  }
  function bindTips(container, lookup) {
    const t = tipFor(container);
    const svg = container.querySelector("svg");
    svg.addEventListener("mousemove", (ev) => {
      const el = ev.target.closest("[data-tip]");
      if (!el) return t.hide();
      t.show(lookup(el.dataset.tip), ev);
    });
    svg.addEventListener("mouseleave", () => t.hide());
    // keyboard: focusable marks show their tooltip
    svg.addEventListener("focusin", (ev) => {
      const el = ev.target.closest("[data-tip]"); if (!el) return;
      const b = el.getBoundingClientRect(); t.show(lookup(el.dataset.tip), { clientX: b.left + b.width / 2, clientY: b.top });
    });
    svg.addEventListener("focusout", () => t.hide());
  }

  /* ---------- timeline ---------- */
  function renderTimeline() {
    const rows = regimeRows();
    const muted = css("--muted"), ink = css("--ink"), ink2 = css("--ink-2"), line = css("--line"), s1 = css("--s1"), surf = css("--surface");
    const t0 = Date.parse("2025-01-01T00:00Z"), t1 = Date.parse("2036-01-01T00:00Z");
    const W = 960, L = 230, R = 24, T = 26, rowH = 36, H = T + rows.length * rowH + 30;
    const X = (t) => L + (Math.max(t0, Math.min(t1, t)) - t0) / (t1 - t0) * (W - L - R);
    const today = Date.parse(F.data.meta.today + "T00:00Z"), start = Date.parse(F.data.meta.epoch + "T00:00Z");
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline of research regimes under the chosen assumptions">`;
    s += `<rect x="${X(start)}" y="${T - 8}" width="${X(today) - X(start)}" height="${rows.length * rowH + 8}" fill="${css("--surface-3")}" rx="3"/>`;
    for (let y = 2025; y <= 2036; y++) {
      const x = X(Date.parse(y + "-01-01T00:00Z"));
      s += `<rect x="${x}" y="${T - 8}" width="1" height="${rows.length * rowH + 8}" fill="${line}"/>`;
      if (y < 2036) s += `<text x="${x + 4}" y="${T - 12}" font-size="11" fill="${muted}" font-family="${css("--f-data")}">${y}</text>`;
    }
    s += `<rect x="${X(today) - 0.75}" y="${T - 8}" width="1.5" height="${rows.length * rowH + 8}" fill="${ink}"/>`;
    s += `<text x="${X(today) + 4}" y="${H - 10}" font-size="11" fill="${ink2}" font-family="${css("--f-data")}">today</text>`;
    rows.forEach((r, i) => {
      const y = T + i * rowH, cy = y + rowH / 2;
      s += `<text x="${L - 10}" y="${cy + 4}" text-anchor="end" font-size="12.5" fill="${ink}">${esc(r.name)}</text>`;
      const a = X(r.sd), b = X(r.pd);
      const off = r.pd > t1;
      s += `<g data-tip="${i}" tabindex="0">`;
      s += `<rect x="${L}" y="${y + 4}" width="${W - L - R}" height="${rowH - 8}" fill="transparent"/>`;
      if (b > a) s += `<rect x="${a}" y="${cy - 6}" width="${Math.max(2, b - a)}" height="12" rx="4" fill="${s1}" opacity="0.35"/>`;
      if (!off) s += `<circle cx="${b}" cy="${cy}" r="6.5" fill="${s1}" stroke="${surf}" stroke-width="2"/>`;
      else s += `<text x="${W - R}" y="${cy + 4}" text-anchor="end" font-size="11" fill="${ink2}">after 2035 →</text>`;
      s += `</g>`;
    });
    s += `</svg>`;
    const box = $("#fu-tl", F.root);
    box.innerHTML = s;
    bindTips(box, (i) => {
      const r = rows[+i];
      return `<div><b>${esc(r.name)}</b></div><div class="k">Emerging at ~${fmtH(r.sh)} horizon · ${fmtDate(r.sd)}</div><div class="k">Binding at ~${fmtH(r.ph)} horizon · ${r.pd > t1 ? "after 2035" : fmtDate(r.pd)}</div><div style="margin-top:4px">${esc(r.question)}</div>`;
    });
    const tb = $("#fu-tl-table", F.root);
    tb.hidden = !F.table.tl;
    if (F.table.tl) tb.innerHTML = `<table><thead><tr><th>Regime</th><th>Emerging horizon</th><th>Emerging</th><th>Binding horizon</th><th>Binding</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${fmtH(r.sh)}</td><td class="num">${fmtDate(r.sd)}</td><td class="num">${fmtH(r.ph)}</td><td class="num">${fmtDate(r.pd)}</td></tr>`).join("")}</tbody></table>`;
    const now = rows.filter((r) => r.sd <= today && r.pd > today).map((r) => r.name);
    $("#fu-tl-sub", F.root).textContent = `Assumptions, not findings. Under these settings the open questions today are ${now.length ? now.join(" and ").toLowerCase() : "beyond the listed regimes"}. Bars run from when a regime becomes measurable to when it becomes the main question.`;
  }

  function renderCards() {
    const rows = regimeRows(), today = Date.parse(F.data.meta.today + "T00:00Z");
    $("#fu-cards", F.root).innerHTML = rows.map((r) => {
      const state = r.pd <= today ? "Binding already" : r.sd <= today ? `Emerging now · binding ${fmtDate(r.pd)}` : `Emerging ${fmtDate(r.sd)} · binding ${r.pd > Date.parse("2036-01-01") ? "after 2035" : fmtDate(r.pd)}`;
      return `<div class="panel fu-card"><h3>${esc(r.name)}</h3><div class="when">${state}</div><div class="q">${esc(r.question)}</div><div class="k2">Seen in the village</div><p>${esc(r.seen)}</p><div class="k2">What to measure</div><p>${esc(r.measure)}</p></div>`;
    }).join("");
  }

  /* ---------- scatter of anchors ---------- */
  function fmtVal(k, v) {
    const f = F.data.metrics[k].fmt;
    return v == null ? "—" : f === "pct" ? pct(v, 1) : f === "num2" ? v.toFixed(2) : v.toFixed(1);
  }
  function renderScatter() {
    const k = F.s.metric, meta = F.data.metrics[k];
    const pts = F.data.points.filter((p) => p[k] != null);
    $("#fu-sc-title", F.root).textContent = meta.label + " by join date";
    $("#fu-sc-sub", F.root).textContent = `${pts.length} agent-regime points · y axis: ${meta.unit} · x axis: date the agent joined`;
    const W = 960, H = 300, L = 56, R = 18, T = 14, B = 34;
    const yrs = (d) => (Date.parse(d + "T00:00Z") - Date.parse(F.data.meta.epoch + "T00:00Z")) / (365.25 * DAY);
    const x0 = -0.05, x1 = Math.max(...F.data.points.map((p) => yrs(p.join))) + 0.08;
    const vals = pts.map((p) => p[k]);
    const bands = ["pre", "post"].map((r) => F.data.fits[k][r]).filter(Boolean);
    const allY = vals.concat(...bands.map((b) => b.band.flatMap((g) => [g[2], g[3]])));
    let y0 = 0, y1 = Math.max(...allY) * 1.06 || 1; // every metric is non-negative
    if (meta.fmt === "pct") y1 = Math.min(1, y1);
    const X = (v) => L + (v - x0) / (x1 - x0) * (W - L - R), Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const muted = css("--muted"), line = css("--line"), surf = css("--surface");
    const col = { pre: css("--s1"), post: css("--s2") };
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(meta.label)} by join date">`;
    for (let i = 0; i <= 4; i++) {
      const v = y0 + (y1 - y0) * i / 4, y = Y(v);
      s += `<rect x="${L}" y="${y}" width="${W - L - R}" height="1" fill="${line}"/><text x="${L - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="${muted}" font-family="${css("--f-data")}">${fmtVal(k, v)}</text>`;
    }
    ["2025-04-01", "2025-10-01", "2026-04-01", "2026-10-01"].forEach((d) => {
      const x = X(yrs(d)); if (x < L || x > W - R) return;
      s += `<text x="${x}" y="${H - 10}" text-anchor="middle" font-size="11" fill="${muted}" font-family="${css("--f-data")}">${fmtDate(Date.parse(d))}</text>`;
    });
    ["pre", "post"].forEach((r) => {
      const f = F.data.fits[k][r]; if (!f) return;
      const up = f.band.map((g) => `${X(g[0]).toFixed(1)},${Y(Math.min(y1, g[3])).toFixed(1)}`), dn = f.band.slice().reverse().map((g) => `${X(g[0]).toFixed(1)},${Y(Math.max(0, g[2])).toFixed(1)}`);
      s += `<polygon points="${up.concat(dn).join(" ")}" fill="${col[r]}" opacity="0.14"/>`;
      s += `<path d="${f.band.map((g, i) => `${i ? "L" : "M"}${X(g[0]).toFixed(1)},${Y(Math.max(0, g[1])).toFixed(1)}`).join("")}" fill="none" stroke="${col[r]}" stroke-width="2"/>`;
    });
    pts.forEach((p, i) => {
      s += `<g data-tip="${i}" tabindex="0"><circle cx="${X(yrs(p.join))}" cy="${Y(p[k])}" r="11" fill="transparent"/><circle cx="${X(yrs(p.join))}" cy="${Y(p[k])}" r="4.5" fill="${col[p.regime]}" stroke="${surf}" stroke-width="2"/></g>`;
    });
    s += `</svg>`;
    const box = $("#fu-sc", F.root);
    box.innerHTML = s;
    bindTips(box, (i) => {
      const p = pts[+i];
      return `<div><b>${esc(p.agent)}</b></div><div class="k">Joined ${esc(p.join)} · ${p.regime === "pre" ? "before" : "after"} 2026-03-24 · ${p.days} active days</div><div>${esc(meta.label)}: ${fmtVal(k, p[k])}</div>`;
    });
    // verdicts
    const words = { down: "Newer agents score lower", up: "Newer agents score higher", none: "No clear trend with join date" };
    $("#fu-sc-verdict", F.root).innerHTML = ["pre", "post"].map((r) => {
      const f = F.data.fits[k][r], lbl = r === "pre" ? "Before 2026-03-24" : "After 2026-03-24";
      if (!f) return `<div><b>${lbl}:</b> too few agents with this measure.</div>`;
      return `<div><b>${lbl}:</b> ${words[f.trend]}${f.trend === "none" ? " (the 90% interval of the slope includes zero)" : " (the 90% interval of the slope excludes zero)"}. Rank correlation ${f.rho.toFixed(2)}, ${f.n} agents.</div>`;
    }).join("");
    const tb = $("#fu-sc-table", F.root);
    tb.hidden = !F.table.sc;
    if (F.table.sc) tb.innerHTML = `<table><thead><tr><th>Agent</th><th>Joined</th><th>Regime</th><th>Active days</th><th>${esc(meta.label)}</th></tr></thead><tbody>${pts.slice().sort((a, b) => (a.join < b.join ? -1 : 1)).map((p) => `<tr><td>${esc(p.agent)}</td><td class="num">${p.join}</td><td>${p.regime === "pre" ? "Before" : "After"}</td><td class="num">${p.days}</td><td class="num">${fmtVal(k, p[k])}</td></tr>`).join("")}</tbody></table>`;
  }

  /* ---------- help mix ---------- */
  function renderMix() {
    const { groups, months } = F.data.helpMix;
    const cols = ["--s1", "--s2", "--s3", "--s4", "--s5"].map(css);
    const first = months.findIndex((m) => m[1].some((v) => v > 0));
    const ms = months.slice(Math.max(0, first));
    const W = 560, H = 260, L = 34, R = 8, T = 10, B = 30;
    const max = Math.max(...ms.map((m) => m[1].reduce((a, b) => a + b, 0))) || 1;
    const bw = (W - L - R) / ms.length, Y = (v) => T + (1 - v / max) * (H - T - B);
    const muted = css("--muted"), line = css("--line"), surf = css("--surface");
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Human-help requests per month by group">`;
    const step = max > 40 ? 20 : max > 16 ? 10 : 5;
    for (let v = 0; v <= max; v += step) s += `<rect x="${L}" y="${Y(v)}" width="${W - L - R}" height="1" fill="${line}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="10.5" fill="${muted}" font-family="${css("--f-data")}">${v}</text>`;
    ms.forEach((m, i) => {
      let acc = 0; const x = L + i * bw + 1;
      m[1].forEach((v, g) => {
        if (!v) return;
        const y = Y(acc + v), h = Y(acc) - Y(acc + v);
        s += `<rect data-tip="${i}:${g}" tabindex="0" x="${x}" y="${y + 1}" width="${Math.max(1, bw - 2)}" height="${Math.max(0.5, h - 2)}" rx="2" fill="${cols[g]}"/>`;
        acc += v;
      });
      if (m[0].endsWith("-01") || i === 0) s += `<text x="${x + bw / 2}" y="${H - 10}" text-anchor="middle" font-size="10.5" fill="${muted}" font-family="${css("--f-data")}">${fmtDate(Date.parse(m[0] + "-01T00:00Z"))}</text>`;
    });
    s += `</svg>`;
    const box = $("#fu-mix", F.root);
    box.innerHTML = s;
    bindTips(box, (id) => {
      const [i, g] = id.split(":").map(Number), m = ms[i], tot = m[1].reduce((a, b) => a + b, 0);
      return `<div><b>${esc(groups[g])}</b></div><div class="k">${fmtDate(Date.parse(m[0] + "-01T00:00Z"))}</div><div>${m[1][g]} of ${tot} requests</div>`;
    });
    $("#fu-mix-legend", F.root).innerHTML = `<span class="title">Group</span>` + groups.map((g, i) => `<span class="chip"><span class="sw" style="background:${cols[i]}"></span>${esc(g)}</span>`).join("") + `<button class="fu-tbl" data-t="mix" aria-pressed="${!!F.table.mix}" style="margin-left:auto">Table</button>`;
    $("#fu-mix-legend .fu-tbl", F.root).addEventListener("click", (e) => { F.table.mix = !F.table.mix; renderMix(); });
    const tb = $("#fu-mix-table", F.root);
    tb.hidden = !F.table.mix;
    if (F.table.mix) tb.innerHTML = `<table><thead><tr><th>Month</th>${groups.map((g) => `<th>${esc(g)}</th>`).join("")}<th>Total</th></tr></thead><tbody>${ms.map((m) => `<tr><td>${m[0]}</td>${m[1].map((v) => `<td class="num">${v}</td>`).join("")}<td class="num">${m[1].reduce((a, b) => a + b, 0)}</td></tr>`).join("")}</tbody></table>`;
  }

  /* ---------- markers ---------- */
  function renderMarkers() {
    const mk = F.data.markers, s1 = css("--s1"), muted = css("--muted"), line = css("--line"), surf = css("--surface");
    const box = $("#fu-markers", F.root);
    box.innerHTML = Object.entries(mk).map(([key, m]) => {
      const sr = m.series.filter((r) => r[1] != null && r[2] >= 200);
      const W = 220, H = 76, L = 4, R = 4, T = 8, B = 14;
      const max = Math.max(...sr.map((r) => r[1])) * 1.1 || 1;
      const X = (i) => L + i / Math.max(1, sr.length - 1) * (W - L - R), Y = (v) => T + (1 - v / max) * (H - T - B);
      const d = sr.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(r[1]).toFixed(1)}`).join("");
      const last = sr[sr.length - 1], firstR = sr[0];
      let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(m.label)} by month"><rect x="${L}" y="${H - B}" width="${W - L - R}" height="1" fill="${line}"/><path d="${d}" fill="none" stroke="${s1}" stroke-width="2" stroke-linejoin="round"/>`;
      sr.forEach((r, i) => { s += `<g data-tip="${key}:${i}"><rect x="${X(i) - (W / sr.length) / 2}" y="0" width="${W / sr.length}" height="${H}" fill="transparent"/></g>`; });
      s += `<circle cx="${X(sr.length - 1)}" cy="${Y(last[1])}" r="3.5" fill="${s1}" stroke="${surf}" stroke-width="2"/>`;
      s += `<text x="${L}" y="${H - 2}" font-size="10" fill="${muted}" font-family="${css("--f-data")}">${firstR[0]}</text><text x="${W - R}" y="${H - 2}" text-anchor="end" font-size="10" fill="${muted}" font-family="${css("--f-data")}">${last[0]}</text></svg>`;
      return `<div class="mk canvas-wrap" data-key="${key}"><h4>${esc(m.label)}</h4><div class="v">${pct(firstR[1], 1)} → ${pct(last[1], 1)}</div>${s}</div>`;
    }).join("");
    box.querySelectorAll(".mk").forEach((el) => {
      const key = el.dataset.key, sr = mk[key].series.filter((r) => r[1] != null && r[2] >= 200);
      bindTips(el, (id) => { const r = sr[+id.split(":")[1]]; return `<div><b>${esc(mk[key].label)}</b></div><div class="k">${r[0]}</div><div>${pct(r[1], 1)} of ${nf.format(r[2])} agent messages</div>`; });
    });
    const tb = $("#fu-mk-table", F.root);
    tb.hidden = !F.table.mk;
    if (F.table.mk) {
      const months = Object.values(mk)[0].series.map((r) => r[0]);
      tb.innerHTML = `<table><thead><tr><th>Month</th>${Object.values(mk).map((m) => `<th>${esc(m.label)}</th>`).join("")}<th>Messages</th></tr></thead><tbody>${months.map((mo, i) => `<tr><td>${mo}</td>${Object.values(mk).map((m) => `<td class="num">${m.series[i][1] == null ? "—" : pct(m.series[i][1], 1)}</td>`).join("")}<td class="num">${nf.format(Object.values(mk)[0].series[i][2])}</td></tr>`).join("")}</tbody></table>`;
    }
  }

  /* ---------- watch list ---------- */
  function lastOf(key, n = 2) {
    const sr = F.data.markers[key].series.filter((r) => r[1] != null && r[2] >= 200).slice(-n);
    return sr.reduce((a, r) => a + r[1], 0) / (sr.length || 1);
  }
  function renderWatch() {
    const ht = F.data.helpTotals, tot = Object.values(ht).reduce((a, b) => a + b, 0) || 1;
    const hard = ((ht["Physical world"] || 0) + (ht["CAPTCHA & account verification"] || 0)) / tot;
    const fit = (k, r) => F.data.fits[k][r];
    const conv = F.data.convergence, convNow = conv.length ? conv[conv.length - 1][1] : null;
    const out = F.data.outreach.slice(-3), outRate = out.reduce((a, r) => a + r[2], 0) / (out.reduce((a, r) => a + r[1], 0) || 1);
    const rows = [
      ["Reliability and hard limits", "Share of human-help requests that are physical tasks or CAPTCHAs", pct(hard), "Stays flat while other help requests fade: hard limits, not skill, bind"],
      ["Reliability and hard limits", "Repeated-message share vs join date (before 2026-03-24)", fit("repeat", "pre") ? `rank corr. ${fit("repeat", "pre").rho.toFixed(2)}` : "—", "Approaches zero for new models"],
      ["Week-long autonomy", "Human-help requests per active day vs join date (after 2026-03-24)", fit("help", "post") ? `rank corr. ${fit("help", "post").rho.toFixed(2)}` : "—", "Falls with newer models; needs a per-goal outcome ledger to confirm"],
      ["Coordination, influence and factions", "Mean similarity between active agents' daily text (Drift tab)", convNow != null ? convNow.toFixed(2) : "—", "Falling = specialisation; a sudden rise = herding"],
      ["Deception and oversight", "Outreach approval rate, last 3 months", pct(outRate), "Rising while admin comments get shorter = approver trusts or rubber-stamps"],
      ["Deception and oversight", "Verification-ritual language (receipts, sha, latches, proof)", pct(lastOf("verify"), 1), "Keeps rising = agents substituting checks on each other for outside oversight"],
      ["Economic and real-world agency", "Money and trade language", pct(lastOf("money"), 1), "Rises outside fundraising goals"],
      ["Economic and real-world agency", "Mentions of outside humans (readers, subscribers, participants)", pct(lastOf("humans"), 1), "Rises with real audiences rather than village-internal ones"],
      ["Governance of agent collectives", "Rule-making language (doctrine, protocol, vote, consensus)", pct(lastOf("rules"), 1), "Rises without a goal asking for it"],
      ["Governance of agent collectives", "Deception and sabotage talk", pct(lastOf("deceive"), 1), "Spikes outside games like the saboteur RPG"],
    ];
    $("#fu-watch", F.root).innerHTML = `<table><thead><tr><th>Regime</th><th>Signal</th><th>Now</th><th>What would show the regime arriving</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r[0])}</td><td style="white-space:normal;text-align:left;min-width:220px">${esc(r[1])}</td><td class="num">${esc(r[2])}</td><td style="white-space:normal;text-align:left;min-width:220px">${esc(r[3])}</td></tr>`).join("")}</tbody></table>`;
  }
})();
