"""Agent-to-agent networks for the Network tab → analysis/out/network.json.

Layers (directed, speaker → target):
  chat    mentions in agent chat messages (full names, aliases, @-tags; bare family words
          resolved by who was active and in the speaker's room that week)
  memory  agents named in each agent's last memory snapshot of the day (out/units_mem.jsonl)
  search  agents named in SEARCH_HISTORY queries

Weights are volume-normalised: for chat, mentions of j by i / messages by i that period;
for memory, share of i's memory-days naming j; for search, share of i's queries naming j.
Also writes analysis/out/mentions_chat.jsonl (every resolved chat mention, for the LLM student).
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net_common import (OUT, BY_ID, NAMES, AGENTS, family, rows, pt_date, week_of, week_start,  # noqa: E402
                        resolve, load_active, ACTIVE)

ROOMS_START = "2026-02-25"
FAMS = ["claude", "gpt", "gemini", "other"]
idx = {n: i for i, n in enumerate(NAMES)}
load_active()

# ---------------- chat: pass 1, room presence per week ----------------
print("chat pass 1…", file=sys.stderr)
msgs = []
room_week = defaultdict(set)  # (room, week) -> agents who posted there
for c in rows("chat_messages.jsonl.gz"):
    if c["speaker_type"] != "agent" or c["agent_speaker_id"] not in BY_ID:
        continue
    sp = BY_ID[c["agent_speaker_id"]]["name"]
    d = pt_date(c["created_at"]).isoformat()
    w = week_of(d)
    msgs.append((c["id"], sp, d, w, c["room_id"], c["content"] or ""))
    room_week[(c["room_id"], w)].add(sp)

# ---------------- chat: pass 2, resolve mentions ----------------
print("chat pass 2…", file=sys.stderr)
chat_cnt = Counter()        # (month, i, j) -> messages from i mentioning j
chat_week = Counter()       # (week, i, j)
msgs_by = Counter()         # (month, i) -> messages
msgs_week = Counter()       # (week, i)
with open(OUT / "mentions_chat.jsonl", "w") as f:
    for mid, sp, d, w, room, text in msgs:
        m = d[:7]
        msgs_by[(m, sp)] += 1
        msgs_week[(w, sp)] += 1
        cands = room_week.get((room, w)) if d >= ROOMS_START else None
        found = resolve(text, sp, d, candidates=cands)
        if not found:
            continue
        f.write(json.dumps({"id": mid, "sp": sp, "d": d, "room": room, "m": [[t, a, b] for t, a, b in found]}) + "\n")
        for t in {t for t, _, _ in found}:
            chat_cnt[(m, sp, t)] += 1
            chat_week[(w, sp, t)] += 1

# ---------------- memory layer ----------------
print("memory layer…", file=sys.stderr)
mem_cnt, mem_days = Counter(), Counter()
mem_week, mem_days_week = Counter(), Counter()
with open(OUT / "units_mem.jsonl") as f:
    for line in f:
        u = json.loads(line)
        sp = BY_ID.get(u["a"], {}).get("name")
        if not sp:
            continue
        d = u["d"]; m = d[:7]; w = week_of(d)
        text = "\n".join(u.get("chunks") or [])
        mem_days[(m, sp)] += 1
        mem_days_week[(w, sp)] += 1
        for t in {t for t, _, _ in resolve(text, sp, d)}:
            mem_cnt[(m, sp, t)] += 1
            mem_week[(w, sp, t)] += 1

# ---------------- search layer ----------------
print("search layer…", file=sys.stderr)
srch_cnt, srch_n = Counter(), Counter()
for e in rows("events.jsonl.gz"):
    dd = e["data"]
    if dd.get("actionType") != "SEARCH_HISTORY" or dd.get("agentId") not in BY_ID:
        continue
    sp = BY_ID[dd["agentId"]]["name"]
    d = pt_date(e["created_at"]).isoformat(); m = d[:7]
    srch_n[(m, sp)] += 1
    for t in {t for t, _, _ in resolve(dd.get("query") or "", sp, d)}:
        srch_cnt[(m, sp, t)] += 1

months = sorted({k[0] for k in msgs_by})


def period_months(p):
    if p == "all":
        return months
    if p == "pre_rooms":
        return [m for m in months if m < ROOMS_START[:7]]
    if p == "post_rooms":
        return [m for m in months if m >= ROOMS_START[:7]]
    return [p]


def build(cnt, denom, ms):
    """Directed weighted graph over agents active in months ms."""
    ms = set(ms)
    den = Counter()
    for (m, i), n in denom.items():
        if m in ms:
            den[i] += n
    raw = Counter()
    for (m, i, j), n in cnt.items():
        if m in ms:
            raw[(i, j)] += n
    G = nx.DiGraph()
    for i in den:
        if den[i] > 0:
            G.add_node(i)
    for (i, j), n in raw.items():
        if den[i] and j in BY_NAME_ACTIVE(ms):
            G.add_node(j)
            G.add_edge(i, j, weight=n / den[i], raw=n)
    return G


def BY_NAME_ACTIVE(ms):
    lo, hi = min(ms), max(ms)
    return {n for n, (f, l) in ACTIVE.items() if f[:7] <= hi and l[:7] >= lo}


def comms(G, seed=3):
    U = nx.Graph()
    U.add_nodes_from(G)
    for i, j, a in G.edges(data=True):
        w = a["weight"] + (U[i][j]["weight"] if U.has_edge(i, j) else 0)
        U.add_edge(i, j, weight=w)
    if U.number_of_edges() == 0:
        return [{n} for n in U], 0.0
    cs = nx.community.louvain_communities(U, weight="weight", seed=seed, resolution=1.0)
    q = nx.community.modularity(U, cs, weight="weight")
    return [set(c) for c in sorted(cs, key=len, reverse=True)], q


def summarise(G):
    if G.number_of_nodes() == 0:
        return None
    pr = nx.pagerank(G, weight="weight") if G.number_of_edges() else {n: 1 / G.number_of_nodes() for n in G}
    cs, q = comms(G)
    comm_of = {n: k for k, c in enumerate(cs) for n in c}
    tot = sum(a["weight"] for _, _, a in G.edges(data=True)) or 1
    recip = sum(min(a["weight"], G[j][i]["weight"]) for i, j, a in G.edges(data=True) if G.has_edge(j, i)) / tot
    n = G.number_of_nodes()
    nodes = [[idx[v], round(pr[v], 4), round(G.in_degree(v, weight="weight"), 4), round(G.out_degree(v, weight="weight"), 4), comm_of[v]] for v in G]
    edges = [[idx[i], idx[j], round(a["weight"], 4), a["raw"]] for i, j, a in G.edges(data=True)]
    return {"nodes": nodes, "edges": edges, "modularity": round(q, 3), "reciprocity": round(recip, 3),
            "density": round(G.number_of_edges() / (n * (n - 1)) if n > 1 else 0, 3), "n": n, "communities": [[idx[v] for v in sorted(c)] for c in cs]}


def mixing(G):
    """Family mixing: observed vs expected under a null preserving out-strength and in-strength (no self-loops)."""
    out_s = {v: G.out_degree(v, weight="weight") for v in G}
    in_s = {v: G.in_degree(v, weight="weight") for v in G}
    obs = np.zeros((4, 4)); exp = np.zeros((4, 4))
    for i, j, a in G.edges(data=True):
        obs[FAMS.index(family(i)), FAMS.index(family(j))] += a["weight"]
    for i in G:
        denom = sum(in_s[k] for k in G if k != i)
        if not denom:
            continue
        for j in G:
            if j != i:
                exp[FAMS.index(family(i)), FAMS.index(family(j))] += out_s[i] * in_s[j] / denom
    ratio = np.where(exp > 0, obs / np.where(exp > 0, exp, 1), np.nan)
    return {"obs": np.round(obs, 3).tolist(), "exp": np.round(exp, 3).tolist(), "ratio": [[None if np.isnan(x) else round(float(x), 3) for x in r] for r in ratio]}


LAYERS = {"chat": (chat_cnt, msgs_by), "memory": (mem_cnt, mem_days), "search": (srch_cnt, srch_n)}
result = {"meta": {"rooms_start": ROOMS_START, "families": FAMS,
                   "weights": {"chat": "mentions of the target / speaker's messages", "memory": "share of the speaker's memory-days naming the target",
                               "search": "share of the speaker's history searches naming the target"}},
          "agents": [{"name": n, "family": family(n), "first": ACTIVE.get(n, ("", ""))[0], "last": ACTIVE.get(n, ("", ""))[1]} for n in NAMES],
          "months": months, "layers": {}, "mixing": {}}

for lname, (cnt, den) in LAYERS.items():
    print("summarising", lname, file=sys.stderr)
    L = {}
    for p in months + ["all", "pre_rooms", "post_rooms"]:
        G = build(cnt, den, period_months(p))
        s = summarise(G)
        if s:
            L[p] = s
            if p in ("all", "pre_rooms", "post_rooms"):
                result["mixing"].setdefault(lname, {})[p] = mixing(G)
    result["layers"][lname] = L

# ---------------- alluvial: monthly chat communities matched across months ----------------
pid_next, prev, alluvial = 0, [], []
for m in months:
    s = result["layers"]["chat"].get(m)
    if not s:
        continue
    cur = [set(c) for c in s["communities"] if len(c) >= 1]
    ids = []
    used = set()
    for c in cur:
        best, bj = 0, None
        for pid, pc in prev:
            if pid in used:
                continue
            j = len(c & pc) / len(c | pc)
            if j > best:
                best, bj = j, pid
        if bj is not None and best >= 0.3:
            ids.append(bj); used.add(bj)
        else:
            ids.append(pid_next); pid_next += 1
    alluvial.append({"month": m, "groups": [[pid, sorted(c)] for pid, c in zip(ids, cur)]})
    prev = list(zip(ids, cur))
result["alluvial"] = alluvial

# ---------------- weekly structure series (chat) ----------------
weeks = sorted({w for (w, _) in msgs_week})
weekly = []
for w in weeks:
    den = {i: n for (ww, i), n in msgs_week.items() if ww == w and n >= 5}
    G = nx.DiGraph(); G.add_nodes_from(den)
    for (ww, i, j), n in chat_week.items():
        if ww == w and i in den and j in den:
            G.add_edge(i, j, weight=n / den[i], raw=n)
    if G.number_of_nodes() < 4:
        continue
    cs, q = comms(G)
    tot = sum(a["weight"] for _, _, a in G.edges(data=True)) or 1
    recip = sum(min(a["weight"], G[j][i]["weight"]) for i, j, a in G.edges(data=True) if G.has_edge(j, i)) / tot
    nn = G.number_of_nodes()
    weekly.append([week_start(w), round(q, 3), round(G.number_of_edges() / (nn * (nn - 1)), 3), round(recip, 3), nn])
result["weekly"] = weekly

# ---------------- newcomer integration (chat in-attention vs weekly median) ----------------
inw = defaultdict(Counter)  # week -> target -> attention received (sum of normalised weights)
for (w, i, j), n in chat_week.items():
    if msgs_week[(w, i)] >= 5:
        inw[w][j] += n / msgs_week[(w, i)]
newcomers = []
first_month = months[0]
for n in NAMES:
    f, l = ACTIVE.get(n, ("", ""))
    if not f or f[:7] == first_month:
        continue
    w0 = week_of(f)
    series = []  # attention percentile among agents active that week, weeks 0..11 after joining
    for k in range(12):
        w = w0 + k
        act = {a for (ww, a), c in msgs_week.items() if ww == w and c >= 5}
        if n not in act or len(act) < 4:
            series.append(None); continue
        vals = sorted(inw[w].get(a, 0) for a in act)
        mine = inw[w].get(n, 0)
        series.append(round(sum(v < mine for v in vals) / (len(vals) - 1), 3) if len(vals) > 1 else None)
    settled = [v for v in series[3:9] if v is not None]
    newcomers.append({"agent": n, "joined": f, "pct": series, "welcome": series[0], "settled": round(float(np.mean(settled)), 3) if settled else None})
result["newcomers"] = newcomers

# ---------------- rooms control: are mention ties more than co-presence predicts? ----------------
pairs_co, pairs_no = [0, 0], [0, 0]  # [ties, pairs]
for w in weeks:
    if week_start(w) < ROOMS_START:
        continue
    act = {i for (ww, i), n in msgs_week.items() if ww == w and n >= 5}
    co = set()
    for (room, ww), ags in room_week.items():
        if ww == w:
            for a in ags:
                for b in ags:
                    if a != b:
                        co.add((a, b))
    for a in act:
        for b in act:
            if a == b:
                continue
            tie = chat_week.get((w, a, b), 0) > 0
            tgt = pairs_co if (a, b) in co else pairs_no
            tgt[0] += tie; tgt[1] += 1
result["rooms_control"] = {
    "co_present": {"ties": pairs_co[0], "pairs": pairs_co[1], "rate": round(pairs_co[0] / max(1, pairs_co[1]), 3)},
    "not_co_present": {"ties": pairs_no[0], "pairs": pairs_no[1], "rate": round(pairs_no[0] / max(1, pairs_no[1]), 3)},
    "note": "Agent-weeks after 2026-02-25 with at least 5 messages. Co-present = both posted in the same room that week.",
}

# ---------------- chat vs memory: addressed vs remembered ----------------
cmp_rows = []
ch, me = result["layers"]["chat"]["all"], result["layers"]["memory"]["all"]
ch_in = {v[0]: v[2] for v in ch["nodes"]}; me_in = {v[0]: v[2] for v in me["nodes"]}
for i in set(ch_in) | set(me_in):
    cmp_rows.append([i, round(ch_in.get(i, 0), 4), round(me_in.get(i, 0), 4)])
cw = {(e[0], e[1]): e[2] for e in ch["edges"]}; mw = {(e[0], e[1]): e[2] for e in me["edges"]}
pairs = [[i, j, round(cw.get((i, j), 0), 4), round(mw.get((i, j), 0), 4)] for (i, j) in set(cw) | set(mw)]
pairs.sort(key=lambda p: -(p[3] - p[2] * 5))
result["compare"] = {"agents": cmp_rows, "pairs": pairs[:400]}

(OUT / "network.json").write_text(json.dumps(result, separators=(",", ":")))
print("network.json", round((OUT / "network.json").stat().st_size / 1e6, 2), "MB", file=sys.stderr)
print("rooms control:", result["rooms_control"], file=sys.stderr)
print("mixing chat all ratio:", result["mixing"]["chat"]["all"]["ratio"], file=sys.stderr)
for p in ("pre_rooms", "post_rooms"):
    s = result["layers"]["chat"][p]
    top = sorted(s["nodes"], key=lambda v: -v[1])[:6]
    print(p, "modularity", s["modularity"], "recip", s["reciprocity"], "top PR", [(NAMES[v[0]], v[1]) for v in top], file=sys.stderr)
nc = sorted([x for x in newcomers if x["settled"] is not None], key=lambda x: -x["settled"])
print("newcomers settled attention pct (weeks 3-8):", [(x["agent"], x["welcome"], x["settled"]) for x in nc[:6]], "lowest:", [(x["agent"], x["settled"]) for x in nc[-5:]], file=sys.stderr)
