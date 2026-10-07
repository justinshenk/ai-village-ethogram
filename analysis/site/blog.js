"use strict";
/* =====================================================================
   BLOG IDEAS — proposals for AI Village blog posts, grounded in the data.
   Exposes window.initBlog(root). Fetches blog.json.
   Uses page globals: $, $$, css, esc, nf, onThemeChange, fetchJSON.
   ===================================================================== */
(function () {
  let BD = null;
  const st = { audience: "", effort: "", theme: "", sort: "score", open: null, table: false };
  const EFFORT_ORDER = { S: 1, M: 2, L: 3 };
  const EFFORT_LABEL = { S: "Small", M: "Medium", L: "Large" };
  const TAB_LABEL = { activity: "Activity strips", transitions: "Transitions", drift: "Drift", help: "Human help", network: "Network", memory: "Memory", decoder: "Decoder", futures: "Futures" };

  function injectStyles() {
    if (document.getElementById("bl-styles")) return;
    const s = document.createElement("style");
    s.id = "bl-styles";
    s.textContent = `
      .bl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap: 12px; }
      .bl-card { background: var(--surface); border: 1px solid var(--ring); border-radius: 10px; padding: 14px; display: grid; gap: 8px; align-content: start; min-width: 0; }
      .bl-card.bl-open { grid-column: 1 / -1; border-color: var(--ink); }
      .bl-top { display: flex; gap: 10px; align-items: baseline; }
      .bl-rank { font-family: var(--f-data); font-size: 12px; color: var(--muted); flex: none; }
      .bl-title { font-size: 16px; font-weight: 700; margin: 0; text-wrap: balance; line-height: 1.3; }
      .bl-pitch { margin: 0; color: var(--ink-2); font-size: 13.5px; }
      .bl-chips { display: flex; flex-wrap: wrap; gap: 6px; }
      .bl-chip { font-size: 11.5px; padding: 2px 8px; border-radius: 999px; background: var(--surface-2); color: var(--ink-2); border: 1px solid var(--line); }
      .bl-score { display: grid; max-width: 380px; grid-template-columns: auto 1fr auto; gap: 3px 8px; align-items: center; font-size: 11.5px; color: var(--muted); }
      .bl-score .bl-bar { height: 6px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
      .bl-score .bl-bar i { display: block; height: 100%; background: var(--ink-2); border-radius: 3px; }
      .bl-score b { color: var(--ink); font-family: var(--f-data); font-weight: 500; }
      .bl-actions { display: flex; gap: 6px; flex-wrap: wrap; }
      .bl-detail { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 16px 24px; border-top: 1px solid var(--line); padding-top: 12px; margin-top: 4px; }
      @media (max-width: 820px) { .bl-detail { grid-template-columns: minmax(0, 1fr); } }
      .bl-detail h4 { margin: 0 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; }
      .bl-detail p, .bl-detail li { font-size: 13px; margin: 0; }
      .bl-detail ul, .bl-detail ol { margin: 0; padding-left: 18px; display: grid; gap: 5px; }
      .bl-src { display: block; font-family: var(--f-data); font-size: 11px; color: var(--muted); }
      .bl-quote { margin: 0; padding: 6px 10px; border-left: 2px solid var(--line); color: var(--ink-2); font-size: 13px; }
      .bl-quote cite { display: block; font-style: normal; font-size: 11.5px; color: var(--muted); margin-top: 2px; }
      .bl-sec { display: grid; gap: 4px; }
      .bl-col { display: grid; gap: 14px; align-content: start; min-width: 0; }
      .bl-detail a { color: var(--ink); font-weight: 600; }
      .bl-pub { display: grid; gap: 0; }
      .bl-pub-row { display: grid; grid-template-columns: 92px minmax(0, 1fr) auto; gap: 4px 12px; padding: 8px 14px; border-top: 1px solid var(--line); align-items: baseline; font-size: 13px; }
      @media (max-width: 600px) { .bl-pub-row { grid-template-columns: minmax(0, 1fr); } }
      .bl-pub-row a { color: var(--ink); font-weight: 600; }
      .bl-pub-row .bl-meta { color: var(--muted); font-size: 12px; }
      .bl-pub-row .bl-date { font-family: var(--f-data); font-size: 11.5px; color: var(--muted); }
      .bl-ext { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; }
      .bl-ext button { font-size: 11.5px; padding: 1px 8px; border-radius: 999px; }
      .bl-copied { font-size: 12px; color: var(--muted); align-self: center; }
      .bl-copybox { width: 100%; min-height: 120px; font-family: var(--f-data); font-size: 11.5px; background: var(--surface-2); color: var(--ink); border: 1px solid var(--line); border-radius: 6px; padding: 8px; }
    `;
    document.head.appendChild(s);
  }

  window.initBlog = async function (root) {
    injectStyles();
    try { BD = BD || (await fetchJSON("blog.json")); } catch (e) { root.innerHTML = `<div class="panel pending">The blog proposals didn't load (${esc(e.message)}). Reload to try again.</div>`; return; }
    const themes = [...new Set(BD.proposals.map((p) => p.theme))].sort();
    root.innerHTML = `
      <p class="lede" style="margin:0 0 12px">${BD.proposals.length} proposals for the <a href="https://aivillageblog.substack.com/" target="_blank" rel="noopener" style="color:var(--ink);font-weight:600">AI Village blog</a>, each built on findings from this page. Ranked by novelty × evidence × reader interest. Open one for the findings, real quotes, charts and an outline, or copy it as a brief.</p>
      <div class="controls">
        <div class="group" role="group" aria-label="Audience"><span class="lbl">Audience</span>
          ${["", "General", "AI safety", "Researchers"].map((a) => `<button data-bla="${esc(a)}" aria-pressed="${a === st.audience}">${a || "All"}</button>`).join("")}</div>
        <div class="group"><label class="lbl" for="bl-effort">Effort</label>
          <select id="bl-effort"><option value="">Any</option>${["S", "M", "L"].map((e) => `<option value="${e}">${EFFORT_LABEL[e]}</option>`).join("")}</select></div>
        <div class="group"><label class="lbl" for="bl-theme">Theme</label>
          <select id="bl-theme"><option value="">All themes</option>${themes.map((t) => `<option>${esc(t)}</option>`).join("")}</select></div>
        <div class="group"><label class="lbl" for="bl-sort">Sort</label>
          <select id="bl-sort"><option value="score">Score</option><option value="effort">Effort, smallest first</option><option value="evidence">Evidence strength</option><option value="date">Evidence date, newest first</option></select></div>
        <div class="group"><button id="bl-table" aria-pressed="false">Table</button></div>
      </div>
      <p id="bl-count" style="margin:0 0 10px;color:var(--muted);font-size:12.5px"></p>
      <div id="bl-list"></div>
      <div class="panel" style="margin-top:16px">
        <div class="card-h"><h2>Already published</h2><p>Posts on the blog and its LessWrong cross-posts. Tags show which proposals build on each one.</p></div>
        <div class="bl-pub" id="bl-pub" style="margin-top:8px"></div>
      </div>
      <div class="notes">
        <h3>How these were made</h3>
        <p>Each proposal combines results from the other tabs with real chat lines checked against the dataset. Numbers taken from this page's data files are recomputed when the proposals are rebuilt; keyword counts and quotes from the raw chat were checked on ${esc(BD.generated)}.</p>
        <p>Scores are judgement calls: novelty against what the blog has already covered, strength of the evidence we have today, and likely reader interest, each from 1 to 5. Every proposal lists its caveats; several rest on keyword rules or model labels and need checking before publication.</p>
      </div>`;
    $$("[data-bla]", root).forEach((b) => b.addEventListener("click", () => { st.audience = b.dataset.bla; $$("[data-bla]", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); render(); }));
    $("#bl-effort").addEventListener("change", (e) => { st.effort = e.target.value; render(); });
    $("#bl-theme").addEventListener("change", (e) => { st.theme = e.target.value; render(); });
    $("#bl-sort").addEventListener("change", (e) => { st.sort = e.target.value; render(); });
    $("#bl-table").addEventListener("click", (e) => { st.table = !st.table; e.currentTarget.setAttribute("aria-pressed", st.table); render(); });
    onThemeChange(render);
    render(); renderPublished();
  };

  function filtered() {
    const rows = BD.proposals.filter((p) => (!st.audience || p.audience === st.audience) && (!st.effort || p.effort === st.effort) && (!st.theme || p.theme === st.theme));
    const by = {
      score: (a, b) => b.score - a.score,
      effort: (a, b) => EFFORT_ORDER[a.effort] - EFFORT_ORDER[b.effort] || b.score - a.score,
      evidence: (a, b) => b.evidence - a.evidence || b.score - a.score,
      date: (a, b) => (b.evidence_date || "").localeCompare(a.evidence_date || ""),
    }[st.sort];
    return rows.sort(by);
  }

  function scoreBars(p) {
    const row = (lbl, v) => `<span>${lbl}</span><span class="bl-bar" aria-hidden="true"><i style="width:${v * 20}%"></i></span><b>${v}</b>`;
    return `<div class="bl-score" aria-label="Score ${p.score}: novelty ${p.novelty}, evidence ${p.evidence}, interest ${p.interest}">${row("Novelty", p.novelty)}${row("Evidence", p.evidence)}${row("Interest", p.interest)}<span>Score</span><span></span><b>${p.score}</b></div>`;
  }

  function detail(p) {
    const tabLink = (c) => (c.tab ? `<a href="#${esc(c.tab)}">${esc(c.label)}</a> <span class="bl-src">${esc(TAB_LABEL[c.tab] || c.tab)} tab</span>` : `${esc(c.label)} <span class="bl-src">new chart</span>`);
    const ext = p.extends.map((i) => BD.published[i]).filter(Boolean);
    return `<div class="bl-detail">
      <div class="bl-col">
        <div class="bl-sec"><h4>Why now</h4><p>${esc(p.why)}</p>${ext.length ? `<p style="margin-top:4px">Builds on: ${ext.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>`).join(", ")}</p>` : ""}</div>
        <div class="bl-sec"><h4>Key findings</h4><ul>${p.findings.map((f) => `<li>${esc(f.text)}<span class="bl-src">${esc(f.src)}</span></li>`).join("")}</ul></div>
        ${p.quotes.length ? `<div class="bl-sec"><h4>Hooks</h4>${p.quotes.map((q) => `<blockquote class="bl-quote">“${esc(q.text)}”<cite>${esc(q.agent)}, ${esc(q.date)}</cite></blockquote>`).join("")}</div>` : ""}
      </div>
      <div class="bl-col">
        <div class="bl-sec"><h4>Charts</h4><ul>${p.charts.map((c) => `<li>${tabLink(c)}</li>`).join("")}</ul></div>
        <div class="bl-sec"><h4>Outline</h4><ol>${p.outline.map((o) => `<li>${esc(o)}</li>`).join("")}</ol></div>
        <div class="bl-sec"><h4>Data and method</h4><p>${esc(p.method)}</p></div>
        <div class="bl-sec"><h4>Caveats</h4><ul>${p.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>
      </div>
    </div>`;
  }

  function brief(p) {
    const ext = p.extends.map((i) => BD.published[i]).filter(Boolean);
    return [
      `# ${p.title}`, "", `**Pitch:** ${p.pitch}`, "",
      `**Audience:** ${p.audience} · **Effort:** ${EFFORT_LABEL[p.effort]} · **Theme:** ${p.theme} · **Score:** ${p.score} (novelty ${p.novelty}, evidence ${p.evidence}, interest ${p.interest})`, "",
      `## Why now`, p.why, ...(ext.length ? ["", `Builds on: ${ext.map((x) => `[${x.title}](${x.url})`).join(", ")}`] : []), "",
      `## Key findings`, ...p.findings.map((f) => `- ${f.text} _(source: ${f.src})_`), "",
      ...(p.quotes.length ? [`## Hooks`, ...p.quotes.map((q) => `> “${q.text}” (${q.agent}, ${q.date})`), ""] : []),
      `## Charts`, ...p.charts.map((c) => `- ${c.label}${c.tab ? ` (Village Ethogram, ${TAB_LABEL[c.tab] || c.tab} tab)` : " (new)"}`), "",
      `## Outline`, ...p.outline.map((o, i) => `${i + 1}. ${o}`), "",
      `## Data and method`, p.method, "",
      `## Caveats`, ...p.caveats.map((c) => `- ${c}`), "",
    ].join("\n");
  }

  function render() {
    const rows = filtered(), list = $("#bl-list");
    const filt = [st.audience, st.effort && EFFORT_LABEL[st.effort] + " effort", st.theme].filter(Boolean);
    $("#bl-count").textContent = `${rows.length} of ${BD.proposals.length} proposals${filt.length ? " · " + filt.join(", ") : ""}`;
    if (!rows.length) { list.innerHTML = `<p class="pending">No proposals match these filters.</p>`; return; }
    if (st.table) {
      list.innerHTML = `<div class="panel"><div class="table-wrap" style="border-top:0"><table><thead><tr><th>Rank</th><th style="text-align:left">Title</th><th style="text-align:left">Audience</th><th>Effort</th><th style="text-align:left">Theme</th><th>Novelty</th><th>Evidence</th><th>Interest</th><th>Score</th></tr></thead><tbody>${rows.map((p) => `<tr><td class="num">${p.rank}</td><td style="text-align:left;white-space:normal;min-width:200px"><a href="#blog" data-blopen="${esc(p.id)}" style="color:var(--ink);font-weight:600">${esc(p.title)}</a></td><td style="text-align:left">${esc(p.audience)}</td><td class="num">${p.effort}</td><td style="text-align:left">${esc(p.theme)}</td><td class="num">${p.novelty}</td><td class="num">${p.evidence}</td><td class="num">${p.interest}</td><td class="num">${p.score}</td></tr>`).join("")}</tbody></table></div></div>`;
      $$("[data-blopen]", list).forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); openProposal(a.dataset.blopen); }));
      return;
    }
    list.innerHTML = `<div class="bl-grid">${rows.map((p) => {
      const open = st.open === p.id;
      return `<article class="bl-card${open ? " bl-open" : ""}" id="bl-${esc(p.id)}">
        <div class="bl-top"><span class="bl-rank">#${p.rank}</span><h3 class="bl-title">${esc(p.title)}</h3></div>
        <p class="bl-pitch">${esc(p.pitch)}</p>
        <div class="bl-chips"><span class="bl-chip">${esc(p.audience)}</span><span class="bl-chip">${EFFORT_LABEL[p.effort]} effort</span><span class="bl-chip">${esc(p.theme)}</span></div>
        ${scoreBars(p)}
        <div class="bl-actions">
          <button data-bltoggle="${esc(p.id)}" aria-expanded="${open}">${open ? "Close" : "Details"}</button>
          <button data-blcopy="${esc(p.id)}">Copy brief</button>
          <span class="bl-copied" id="bl-copied-${esc(p.id)}" aria-live="polite"></span>
        </div>
        <div id="bl-fallback-${esc(p.id)}"></div>
        ${open ? detail(p) : ""}
      </article>`;
    }).join("")}</div>`;
    $$("[data-bltoggle]", list).forEach((b) => b.addEventListener("click", () => { st.open = st.open === b.dataset.bltoggle ? null : b.dataset.bltoggle; render(); if (st.open) $(`#bl-${st.open}`).scrollIntoView({ behavior: "smooth", block: "nearest" }); }));
    $$("[data-blcopy]", list).forEach((b) => b.addEventListener("click", () => copyBrief(b.dataset.blcopy)));
  }

  function copyBrief(id) {
    const p = BD.proposals.find((x) => x.id === id), text = brief(p), msg = $(`#bl-copied-${id}`);
    const fallback = () => {
      const box = $(`#bl-fallback-${id}`);
      box.innerHTML = `<label class="bl-src" for="bl-ta-${esc(id)}">Copying isn't available here. The brief is selected below; press Ctrl+C or ⌘C.</label><textarea class="bl-copybox" id="bl-ta-${esc(id)}" readonly></textarea>`;
      const ta = $(`#bl-ta-${id}`); ta.value = text; ta.focus(); ta.select();
      msg.textContent = "";
    };
    try {
      navigator.clipboard.writeText(text).then(() => { msg.textContent = "Copied as Markdown"; setTimeout(() => (msg.textContent = ""), 2500); }, fallback);
    } catch (e) { fallback(); }
  }

  function openProposal(id) {
    st.open = id; st.audience = ""; st.effort = ""; st.theme = ""; st.table = false;
    $$("[data-bla]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.bla === ""));
    $("#bl-effort").value = ""; $("#bl-theme").value = ""; $("#bl-table").setAttribute("aria-pressed", "false");
    render();
    const el = $(`#bl-${id}`); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderPublished() {
    const byId = Object.fromEntries(BD.proposals.map((p) => [p.id, p]));
    const rows = [...BD.published].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    $("#bl-pub").innerHTML = rows.map((x) => `<div class="bl-pub-row">
      <span class="bl-date">${esc(x.date || "undated")}</span>
      <span><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><br><span class="bl-meta">${esc(x.author)} · ${esc(x.topic)}${x.data && x.data !== "None" ? " · data: " + esc(x.data) : ""}</span></span>
      <span class="bl-ext">${(x.extended_by || []).map((id) => `<button data-blext="${esc(id)}" title="Open proposal">${esc(byId[id].title)}</button>`).join("")}</span>
    </div>`).join("");
    $$("[data-blext]").forEach((b) => b.addEventListener("click", () => openProposal(b.dataset.blext)));
  }
})();
