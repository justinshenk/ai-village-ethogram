"""Early indicators of memory decline → analysis/out/memory.json.

Weekly panel per agent:
  indicators  from out/memory_health.json (per-rewrite text metrics) and out/emb_mem.npy (embedding step size)
  outcomes    from out/strips.json: repeated-message share and idle (wait + pause) share

Analyses
  leadlag   within-agent correlation of indicator(w) with outcome(w+k)
  granger   outcome(w+k) ~ outcome(w) + indicator(w), two-way demeaned (agent and week), standardised;
            the indicator's coefficient is its predictive value beyond current behaviour and the village-wide week
  event     indicators (z-scored within agent) around loop onsets, weeks -8..+4
  ews       rolling variance and lag-1 autocorrelation of memory-embedding step size around onsets
All intervals: 90% bootstrap over agents (resampling whole agents), 1000 draws.
"""
import bisect
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"
rng = np.random.default_rng(7)
B = 1000
EPOCH = date(2025, 3, 31)  # a Monday
wk = lambda d: (date.fromisoformat(d) - EPOCH).days // 7
wk_date = lambda w: (EPOCH + timedelta(days=7 * w)).isoformat()

INDICATORS = {
    "keep": "Memory kept verbatim",
    "new": "Share of memory that is new",
    "dup_lines": "Duplicate lines in memory",
    "compress": "Compressibility (lower = more repetitive)",
    "neg": "Failure words per 1,000",
    "meta": "Self-correction words per 1,000",
    "lag": "Days since newest date mentioned",
    "url_keep": "Links kept from previous rewrite",
    "len": "Memory length (characters)",
    "step": "Memory embedding change per day",
}
OUTCOMES = {"repeat": "Repeated-message share", "idle": "Idle share (waiting or paused)"}
LAGS = [0, 1, 2, 4]

MH = json.loads((OUT / "memory_health.json").read_text())
S = json.loads((OUT / "strips.json").read_text())
agents_meta = {a["id"]: a["name"] for a in map(json.loads, __import__("gzip").open(ROOT / "data" / "agents.jsonl.gz", "rt"))}

# ---- outcomes per agent-week ----
offs = [d["o"] for d in S["days"]]
dates = [d["date"] for d in S["days"]]
beh = defaultdict(lambda: defaultdict(lambda: np.zeros(4)))  # msgs, reps, idle_s, total_s
for a in S["agents"]:
    for arr, rep in ((a["talk"], 0), (a["rep"], 1)):
        for t in arr:
            w = wk(dates[bisect.bisect_right(offs, t) - 1])
            beh[a["name"]][w][0] += 1
            beh[a["name"]][w][1] += rep
    sg = a["segs"]
    for i in range(0, len(sg), 3):
        w = wk(dates[bisect.bisect_right(offs, sg[i]) - 1])
        beh[a["name"]][w][3] += sg[i + 1]
        if sg[i + 2] in (3, 4):
            beh[a["name"]][w][2] += sg[i + 1]

# ---- indicators per agent-week ----
ind = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
for ag, rows in MH.items():
    for d, m in rows:
        for k in INDICATORS:
            if k != "step" and m.get(k) is not None:
                ind[ag][wk(d)][k].append(m[k])

# memory-embedding step size between consecutive agent-days
emb = np.load(OUT / "emb_mem.npy").astype(np.float32)
units = []
with open(OUT / "units_mem.jsonl") as f:
    for line in f:
        u = json.loads(line)
        units.append((agents_meta.get(u["a"], u["a"]), u["d"]))
by_agent_units = defaultdict(list)
for i, (ag, d) in enumerate(units):
    by_agent_units[ag].append((d, i))
for ag, lst in by_agent_units.items():
    lst.sort()
    for (d0, i0), (d1, i1) in zip(lst, lst[1:]):
        gap = (date.fromisoformat(d1) - date.fromisoformat(d0)).days
        if 0 < gap <= 7:
            a, b = emb[i0], emb[i1]
            step = 1 - float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
            ind[ag][wk(d1)]["step"].append(step)

# ---- panel ----
panel = []  # (agent, week, {ind: value}, repeat, idle, msgs)
for ag in ind:
    for w, mm in ind[ag].items():
        b = beh.get(ag, {}).get(w)
        rec = {k: float(np.mean(v)) for k, v in mm.items() if v}
        rep = b[1] / b[0] if b is not None and b[0] >= 10 else None
        idle = b[2] / b[3] if b is not None and b[3] > 3600 else None
        panel.append((ag, w, rec, rep, idle, int(b[0]) if b is not None else 0))
agents = sorted({p[0] for p in panel})
idx = {(p[0], p[1]): p for p in panel}


def series(ag, key):
    """{week: value} for an indicator or outcome."""
    out = {}
    for (a, w), p in idx.items():
        if a != ag:
            continue
        v = p[3] if key == "repeat" else p[4] if key == "idle" else p[2].get(key)
        if v is not None:
            out[w] = v
    return out


def pairs_for(ag, k_ind, k_out, lag):
    x, y = series(ag, k_ind), series(ag, k_out)
    return [(x[w], y[w + lag], y.get(w)) for w in x if (w + lag) in y]


def ci(vals):
    vals = np.asarray([v for v in vals if np.isfinite(v)])
    if len(vals) < 20:
        return [None, None]
    return [round(float(np.percentile(vals, 5)), 3), round(float(np.percentile(vals, 95)), 3)]


def demean(arr, groups):
    out = arr.copy()
    for g in np.unique(groups):
        m = groups == g
        out[m] -= out[m].mean()
    return out


def within_corr(per_agent):
    X, Y = [], []
    for ps in per_agent:
        if len(ps) < 6:
            continue
        x = np.array([p[0] for p in ps]); y = np.array([p[1] for p in ps])
        X.append(x - x.mean()); Y.append(y - y.mean())
    if not X:
        return np.nan
    X, Y = np.concatenate(X), np.concatenate(Y)
    sx, sy = X.std(), Y.std()
    return float((X * Y).mean() / (sx * sy)) if sx and sy else np.nan


def granger_beta(rows):
    """rows: (agent_i, week, x, y_future, y_now). Two-way demean, standardise, OLS y_future ~ y_now + x."""
    if len(rows) < 60:
        return np.nan
    r = np.array(rows, dtype=float)
    ag, wkk = r[:, 0], r[:, 1]
    cols = []
    for c in (2, 3, 4):
        v = r[:, c].copy()
        for _ in range(4):  # alternating projections ≈ two-way fixed effects
            v = demean(v, ag); v = demean(v, wkk)
        sd = v.std()
        cols.append(v / sd if sd else v)
    x, yf, yn = cols
    Xm = np.column_stack([yn, x])
    beta, *_ = np.linalg.lstsq(Xm, yf, rcond=None)
    return float(beta[1])


result = {"indicators": INDICATORS, "outcomes": OUTCOMES, "lags": LAGS, "leadlag": {}, "granger": {}, "event": {}, "agents": {}}

for ko in OUTCOMES:
    for ki in INDICATORS:
        for lag in LAGS:
            per = {ag: pairs_for(ag, ki, ko, lag) for ag in agents}
            per = {a: p for a, p in per.items() if len(p) >= 6}
            if len(per) < 5:
                continue
            names = list(per)
            r = within_corr(per.values())
            boots = [within_corr([per[names[j]] for j in rng.integers(0, len(names), len(names))]) for _ in range(B)]
            result["leadlag"][f"{ko}|{ki}|{lag}"] = {"r": round(r, 3), "ci": ci(boots), "agents": len(names), "n": sum(len(p) for p in per.values())}
            if lag == 0:
                continue
            rows_by = {a: [(i, w, x, y, yn) for i, a2 in enumerate([a]) for (w, (x, y, yn)) in []] for a in names}
            # assemble rows with week ids
            rows_by = {}
            for ai, a in enumerate(names):
                x, y = series(a, ki), series(a, ko)
                rows_by[a] = [(ai, w, x[w], y[w + lag], y[w]) for w in x if (w + lag) in y and w in y]
            allrows = [r_ for a in names for r_ in rows_by[a]]
            beta = granger_beta(allrows)
            boots = []
            for _ in range(B):
                pick = rng.integers(0, len(names), len(names))
                rows = []
                for new_id, j in enumerate(pick):
                    rows += [(new_id, w, x, yf, yn) for (_, w, x, yf, yn) in rows_by[names[j]]]
                boots.append(granger_beta(rows))
            boots = np.array([b for b in boots if np.isfinite(b)])
            result["granger"][f"{ko}|{ki}|{lag}"] = {
                "beta": round(beta, 3), "ci": ci(boots), "agents": len(names), "n": len(allrows),
                "p_sign": round(float(min((boots <= 0).mean(), (boots >= 0).mean()) * 2), 3) if len(boots) else None,
            }

# ---- loop onsets: repeat share >= 8% after 2 weeks below 5% (within the previous 3 weeks) ----
onsets = []
for ag in agents:
    rep = series(ag, "repeat")
    ws = sorted(rep)
    for i, w in enumerate(ws):
        prev = [rep[v] for v in ws[max(0, i - 2):i] if w - v <= 3]
        if rep[w] >= 0.08 and len(prev) == 2 and all(p < 0.05 for p in prev):
            onsets.append((ag, w))
REL = list(range(-8, 5))
for ki in INDICATORS:
    traces = []
    for ag, w0 in onsets:
        s = series(ag, ki)
        if len(s) < 8:
            continue
        vals = np.array(list(s.values())); mu, sd = vals.mean(), vals.std() or 1
        traces.append([((s[w0 + r] - mu) / sd) if (w0 + r) in s else np.nan for r in REL])
    if len(traces) < 3:
        continue
    T = np.array(traces)
    mean = np.nanmean(T, axis=0)
    boots = np.array([np.nanmean(T[rng.integers(0, len(T), len(T))], axis=0) for _ in range(B)])
    result["event"][ki] = {"rel": REL, "mean": [round(float(v), 3) if np.isfinite(v) else None for v in mean],
                           "lo": [round(float(v), 3) for v in np.nanpercentile(boots, 5, axis=0)],
                           "hi": [round(float(v), 3) for v in np.nanpercentile(boots, 95, axis=0)], "n": len(T)}

# ---- early-warning signals on embedding step: rolling variance and lag-1 autocorrelation (6-week window) ----
def rolling_ews(ag):
    s = series(ag, "step"); ws = sorted(s)
    var, ac = {}, {}
    for w in ws:
        win = [s[v] for v in ws if w - 5 <= v <= w]
        if len(win) >= 5:
            arr = np.array(win)
            var[w] = float(arr.var())
            ac[w] = float(np.corrcoef(arr[:-1], arr[1:])[0, 1]) if arr[:-1].std() and arr[1:].std() else np.nan
    return var, ac

ews_tr = {"var": [], "ac": []}
for ag, w0 in onsets:
    var, ac = rolling_ews(ag)
    for key, d in (("var", var), ("ac", ac)):
        vals = np.array([v for v in d.values() if np.isfinite(v)])
        if len(vals) < 6:
            continue
        mu, sd = vals.mean(), vals.std() or 1
        ews_tr[key].append([((d[w0 + r] - mu) / sd) if (w0 + r) in d and np.isfinite(d[w0 + r]) else np.nan for r in REL])
result["ews"] = {}
for key, tr in ews_tr.items():
    if len(tr) >= 3:
        T = np.array(tr)
        boots = np.array([np.nanmean(T[rng.integers(0, len(T), len(T))], axis=0) for _ in range(B)])
        result["ews"][key] = {"rel": REL, "mean": [round(float(v), 3) if np.isfinite(v) else None for v in np.nanmean(T, axis=0)],
                              "lo": [round(float(v), 3) for v in np.nanpercentile(boots, 5, axis=0)],
                              "hi": [round(float(v), 3) for v in np.nanpercentile(boots, 95, axis=0)], "n": len(T)}

# ---- per-agent weekly series for the small multiples ----
for ag in agents:
    weeks = sorted({w for (a, w) in idx if a == ag})
    if len(weeks) < 4:
        continue
    rows = []
    for w in weeks:
        p = idx[(ag, w)]
        rows.append([wk_date(w)] + [round(p[2][k], 4) if k in p[2] else None for k in INDICATORS] +
                    [round(p[3], 4) if p[3] is not None else None, round(p[4], 4) if p[4] is not None else None, p[5]])
    result["agents"][ag] = rows
result["columns"] = ["week"] + list(INDICATORS) + ["repeat", "idle", "msgs"]
result["onsets"] = [[ag, wk_date(w)] for ag, w in onsets]
result["meta"] = {"weeks_from": wk_date(min(p[1] for p in panel)), "agent_weeks": len(panel), "bootstrap": B,
                  "onset_rule": "a week with 8% or more repeated messages after two weeks below 5%"}

(OUT / "memory.json").write_text(json.dumps(result, separators=(",", ":")))
print("memory.json", round((OUT / "memory.json").stat().st_size / 1e6, 2), "MB; onsets:", len(onsets))
for ko in OUTCOMES:
    print(f"\nGranger ({ko}): beta [90% CI] at lag 1 / 2 / 4")
    for ki in INDICATORS:
        cells = []
        for lag in (1, 2, 4):
            g = result["granger"].get(f"{ko}|{ki}|{lag}")
            cells.append(f"{g['beta']:+.3f} [{g['ci'][0]},{g['ci'][1]}]" if g and g["ci"][0] is not None else "—")
        print(f"  {ki:10} " + "  ".join(cells))
for k, e in result["event"].items():
    print(f"event {k:10} n={e['n']}  pre(-4..-1)={np.nanmean([v for v in e['mean'][4:8] if v is not None]):+.2f}  onset={e['mean'][8]}")
for k, e in result["ews"].items():
    print(f"ews {k} n={e['n']} pre(-4..-1)={np.nanmean([v for v in e['mean'][4:8] if v is not None]):+.2f}")
