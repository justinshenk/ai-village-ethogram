"""Quasi-experiments on past scaffolding changes, and power for proposed experiments.

Writes analysis/out/experiments.json. Run with .venv/bin/python -I.

Panels are built per agent per Pacific-time day from the event log and the activity
strips. Two-way fixed-effects regressions use alternating demeaning; standard errors are
cluster-robust by agent (CR1, t with G-1 df) with a wild cluster bootstrap p-value
(restricted, Rademacher weights), because there are few clusters.
"""
import bisect
import gzip
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"
PT = ZoneInfo("America/Los_Angeles")
rng = np.random.default_rng(3)
B_WILD = 999


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def ts(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def pt_date(t):
    return datetime.fromtimestamp(t, PT).date().isoformat()


def r3(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 4)


# ---------------------------------------------------------------- agents
agents = [json.loads(l) for l in gzip.open(DATA / "agents.jsonl.gz", "rt")]
NAME = {a["id"]: a["name"] for a in agents}
ID_OF = {a["name"]: a["id"] for a in agents}


def family(name, model=""):
    n = name.lower()
    if "claude code" in n or model.startswith("claude-code"):
        return "claude-code"
    if "claude" in n or n.startswith("opus"):
        return "claude"
    if n.startswith("gpt") or re.match(r"^o[134]", n):
        return "gpt"
    if "gemini" in n:
        return "gemini"
    return "other"


FAM = {a["name"]: family(a["name"], a["model_string"]) for a in agents}

# ---------------------------------------------------------------- events
log("reading events…")
ev = []  # (idx, t, type, agentName, data-lite)
nudges = []
outreach_req, outreach_resp = {}, []
for line in gzip.open(DATA / "events.jsonl.gz", "rt"):
    e = json.loads(line)
    d = e["data"]
    typ = d.get("actionType")
    t = ts(e["created_at"])
    if typ == "USER_TALK":
        if (d.get("speakerName") or "").lower() == "automated":
            nudges.append((t, d.get("content") or "", d.get("roomId")))
        continue
    aid = d.get("speakerId") if typ == "AGENT_TALK" else d.get("agentId")
    if aid not in NAME:
        continue
    name = NAME[aid]
    if typ == "OUTREACH_APPROVAL_REQUEST":
        outreach_req[d.get("outreachApprovalRequestId")] = (e["event_index"], t, name)
    elif typ == "OUTREACH_APPROVAL_RESPONSE":
        outreach_resp.append((e["event_index"], t, name, d.get("outreachApprovalRequestId"), str(d.get("approval")) == "True", bool((d.get("adminComment") or "").strip())))
    ev.append((e["event_index"], t, typ, name))
ev.sort()
log(len(ev), "agent events;", len(nudges), "nudges")

# ---------------------------------------------------------------- strips → agent-day active / idle / talk / repeats
S = json.loads((OUT / "strips.json").read_text())
offs = [d["o"] for d in S["days"]]
DAYS = [d["date"] for d in S["days"]]
DAYSET = set(DAYS)


def day_of_v(v):
    return DAYS[bisect.bisect_right(offs, v) - 1]


panel = defaultdict(lambda: defaultdict(float))  # (agent, date) -> metrics
for a in S["agents"]:
    nm = a["name"]
    sg = a["segs"]
    for i in range(0, len(sg), 3):
        d = day_of_v(sg[i])
        panel[(nm, d)]["active_s"] += sg[i + 1]
        if sg[i + 2] in (3, 4):
            panel[(nm, d)]["idle_s"] += sg[i + 1]
    for t in a["talk"]:
        panel[(nm, day_of_v(t))]["msgs"] += 1
    for t in a["rep"]:
        panel[(nm, day_of_v(t))]["msgs"] += 1
        panel[(nm, day_of_v(t))]["reps"] += 1
for _, t, typ, nm in ev:
    d = pt_date(t)
    panel[(nm, d)]["actions"] += 1
    if typ == "SEARCH_HISTORY":
        panel[(nm, d)]["searches"] += 1

rows = []
for (nm, d), m in panel.items():
    if d not in DAYSET:
        continue
    act_h = m["active_s"] / 3600
    rows.append({"agent": nm, "date": d, "fam": FAM.get(nm, "other"), "active_h": act_h, "actions": m["actions"], "msgs": m["msgs"],
                 "reps": m["reps"], "idle_s": m["idle_s"], "active_s": m["active_s"], "searches": m["searches"]})
P = pd.DataFrame(rows)
P["dt"] = pd.to_datetime(P["date"])
P["act_per_h"] = np.where(P.active_h >= 0.5, P.actions / P.active_h.clip(lower=1e-9), np.nan)
P["msg_per_h"] = np.where(P.active_h >= 0.5, P.msgs / P.active_h.clip(lower=1e-9), np.nan)
P["rep_share"] = np.where(P.msgs >= 5, P.reps / P.msgs.clip(lower=1), np.nan)
P["idle_share"] = np.where(P.active_s >= 1800, P.idle_s / P.active_s.clip(lower=1), np.nan)
log("agent-day panel:", len(P))


# ---------------------------------------------------------------- estimation helpers
def demean2(X, g1, g2, iters=50, tol=1e-10):
    X = X.astype(float).copy()
    c1 = pd.factorize(g1)[0]
    c2 = pd.factorize(g2)[0]
    n1, n2 = c1.max() + 1, c2.max() + 1
    for _ in range(iters):
        prev = X.copy()
        for c, n in ((c1, n1), (c2, n2)):
            s = np.zeros((n, X.shape[1])); k = np.bincount(c, minlength=n).astype(float)
            np.add.at(s, c, X)
            X -= (s / np.maximum(k, 1)[:, None])[c]
        if np.abs(X - prev).max() < tol:
            break
    return X


def twfe(df, y, xs, unit="agent", time="date", cluster="agent", wild=True):
    d = df.dropna(subset=[y] + xs).copy()
    if d[unit].nunique() < 4 or len(d) < 30:
        return None
    M = demean2(d[[y] + xs].to_numpy(), d[unit].to_numpy(), d[time].to_numpy())
    Y, X = M[:, 0], M[:, 1:]
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ Y
    resid = Y - X @ beta
    cl = pd.factorize(d[cluster])[0]
    G = cl.max() + 1
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in range(G):
        m = cl == g
        sg = X[m].T @ resid[m]
        meat += np.outer(sg, sg)
    n, k = X.shape
    adj = G / (G - 1) * (n - 1) / max(1, n - k)
    V = adj * XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.diag(V))
    tcrit = stats.t.ppf(0.975, G - 1)
    out = {"beta": beta, "se": se, "lo": beta - tcrit * se, "hi": beta + tcrit * se, "G": int(G), "n": int(n),
           "p": 2 * stats.t.sf(np.abs(beta / np.where(se > 0, se, np.nan)), G - 1), "mean_y": float(d[y].mean())}
    if wild:  # restricted wild cluster bootstrap for the first regressor
        Xr = X[:, 1:]
        if Xr.shape[1]:
            br = np.linalg.pinv(Xr.T @ Xr) @ Xr.T @ Y
            fr = Xr @ br
        else:
            fr = np.zeros_like(Y)
        er = Y - fr
        t0 = beta[0] / se[0] if se[0] > 0 else np.nan
        tb = []
        for _ in range(B_WILD):
            w = rng.choice([-1.0, 1.0], size=G)[cl]
            Ys = fr + w * er
            bs = XtX_inv @ X.T @ Ys
            rs = Ys - X @ bs
            meat = np.zeros((k, k))
            for g in range(G):
                m = cl == g
                sg = X[m].T @ rs[m]
                meat += np.outer(sg, sg)
            Vs = adj * XtX_inv @ meat @ XtX_inv
            tb.append(bs[0] / math.sqrt(Vs[0, 0]) if Vs[0, 0] > 0 else np.nan)
        tb = np.array(tb)
        out["p_wild"] = float(np.mean(np.abs(tb[np.isfinite(tb)]) >= abs(t0))) if np.isfinite(t0) else None
    return out


def its(series_dates, values, break_date, hac_lags=2, unit_days=7.0):
    """Segmented regression: y = a + b*t + c*post + d*post*(t - t0). Returns level and slope changes."""
    t = np.array([(pd.Timestamp(x) - pd.Timestamp(break_date)).days / unit_days for x in series_dates], float)
    y = np.asarray(values, float)
    m = np.isfinite(y)
    t, y = t[m], y[m]
    post = (t >= 0).astype(float)
    X = sm.add_constant(np.column_stack([t, post, post * t]))
    if len(y) < 8 or post.sum() < 3 or (1 - post).sum() < 3:
        return None
    res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    ci = res.conf_int(0.05)
    fit = res.predict(X)
    return {"level": r3(res.params[2]), "level_lo": r3(ci[2][0]), "level_hi": r3(ci[2][1]), "level_p": r3(res.pvalues[2]),
            "slope": r3(res.params[3]), "slope_lo": r3(ci[3][0]), "slope_hi": r3(ci[3][1]), "slope_p": r3(res.pvalues[3]),
            "pre_mean": r3(y[post == 0].mean()), "n": int(len(y)), "fit": [r3(v) for v in fit], "t": t.tolist(), "y": [r3(v) for v in y]}


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None, None)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(p, 4), round(c - h, 4), round(c + h, 4))


def verdict_from(lo, hi, label_pos, label_neg, label_null="No clear effect: the interval includes zero.", p_wild=None):
    if lo is None or hi is None:
        return "Not estimable with this data."
    if lo > 0 or hi < 0:
        base = label_pos if lo > 0 else label_neg
        if p_wild is not None and p_wild >= 0.05:
            return "Suggestive only: " + base[0].lower() + base[1:] + f" The cluster-robust interval excludes zero, but the wild cluster bootstrap does not confirm it (p = {p_wild:.2f})."
        return base
    return label_null


quasi = []

# ================================================================ 1. parallel tool use (Anthropic only), 2026-06-03
log("Q1 parallel tool use DiD…")
T1 = pd.Timestamp("2026-06-03")
W1 = P[(P.dt >= T1 - pd.Timedelta(days=21)) & (P.dt < T1 + pd.Timedelta(days=21)) & (P.fam.isin(["claude", "gpt", "gemini", "other"]))].copy()
W1 = W1[~W1.agent.str.contains("Temporary|Fine-Tuned", regex=True)]
W1["treat"] = (W1.fam == "claude").astype(float)
W1["post"] = (W1.dt >= T1).astype(float)
W1["tp"] = W1.treat * W1.post
W1["week_rel"] = ((W1.dt - T1).dt.days // 7).astype(int)
q1_out = []
q1_event = {}
for y, label, unit in (("act_per_h", "Actions per active hour", "actions/h"), ("msg_per_h", "Messages per active hour", "messages/h"), ("rep_share", "Repeated-message share", "share")):
    r = twfe(W1, y, ["tp"])
    if not r:
        continue
    q1_out.append({"name": label, "unit": unit, "est": r3(r["beta"][0]), "lo": r3(r["lo"][0]), "hi": r3(r["hi"][0]), "p": r3(r["p"][0]),
                   "p_wild": r3(r.get("p_wild")), "clusters": r["G"], "n": r["n"], "baseline": r3(W1[(W1.treat == 1) & (W1.post == 0)][y].mean())})
    # event study: treat x week dummies, omit week -1
    ES = W1.copy()
    cols = []
    for k in range(-3, 3):
        if k == -1:
            continue
        c = f"w{k}"
        ES[c] = ((ES.week_rel == k) & (ES.treat == 1)).astype(float)
        cols.append(c)
    re_ = twfe(ES, y, cols, wild=False)
    if re_:
        pts = []
        for k in range(-3, 3):
            if k == -1:
                pts.append([k, 0.0, 0.0, 0.0])
            else:
                j = cols.index(f"w{k}")
                pts.append([k, r3(re_["beta"][j]), r3(re_["lo"][j]), r3(re_["hi"][j])])
        # joint pre-trend: are the pre-period coefficients (weeks -3, -2) jointly zero?
        pre_idx = [cols.index("w-3"), cols.index("w-2")]
        pre_any = any(not (re_["lo"][j] <= 0 <= re_["hi"][j]) for j in pre_idx)
        q1_event[label] = {"points": pts, "pre_ok": not pre_any}
main = q1_out[0] if q1_out else None
q1_transient = None
if q1_event.get("Actions per active hour"):
    pts_ = {p[0]: p[1] for p in q1_event["Actions per active hour"]["points"]}
    if pts_.get(1) is not None and pts_.get(2) is not None and abs(pts_[1]) > 2 * abs(pts_[2]):
        q1_transient = f" The drop is concentrated in the week after the change ({pts_[1]:+.1f} actions per hour) and mostly gone two weeks out ({pts_[2]:+.1f}), so it may be transient or tied to the event week."
log("Q1 pre-trend ok:", {k: v["pre_ok"] for k, v in q1_event.items()}, q1_event.get("Actions per active hour", {}).get("points"))
quasi.append({
    "key": "parallel_tools", "date": "2026-06-03", "title": "Parallel tool use switched off for Claude agents",
    "change": "Anthropic computer-use agents were limited to one tool call per turn; other providers were unchanged.",
    "estimand": "Change in Claude agents' activity relative to non-Claude agents, three weeks either side.",
    "design": "Difference-in-differences on an agent-day panel with agent and day fixed effects; 95% intervals cluster-robust by agent, plus a wild cluster bootstrap p-value.",
    "outcomes": q1_out, "chart": {"type": "event", "series": q1_event, "xlabel": "weeks from change (week -1 = 0)"},
    "pretrend": ("Pre-change weeks are within their intervals for all outcomes." if q1_event and all(v["pre_ok"] for v in q1_event.values())
                 else "At least one pre-change week differs from zero, so parallel trends is doubtful for that outcome."),
    "confounds": ["The change acts on computer-use turns, which this dataset counts only in computer_use_turns (not loaded here); event-level actions are an indirect measure.",
                  "2026-06-01 'Follow your leader!' goal and 2026-06-07 temporary 8-hour days fall inside the window and affect everyone; day fixed effects absorb shared shocks but not family-specific ones.",
                  "Same-day 2026-06-02/03 memory fixes for Anthropic history rebuilding also apply only to Claude agents.",
                  "The week after the change (2026-06-10 to 06-16) was the 8-hour event week with a Saturday session for #best-room agents only, which may not be balanced across families."],
    "verdict": (verdict_from(main["lo"], main["hi"], "Claude agents' actions per active hour rose relative to others.", "Claude agents' actions per active hour fell relative to others.", p_wild=main.get("p_wild")) + (q1_transient or "") if main else "Not estimable."),
})

# ================================================================ 2. auto-nudger
log("Q2 nudger ITS + event-level…")
T2 = "2026-02-10"
V = P[(P.dt >= pd.Timestamp(T2) - pd.Timedelta(days=28)) & (P.dt < pd.Timestamp("2026-02-25"))]
daily = V.groupby("date").agg(idle=("idle_share", "mean"), rep=("rep_share", "mean"), n=("agent", "nunique")).reset_index()
its_idle = its(daily.date, daily.idle, T2, hac_lags=2, unit_days=1)
its_rep = its(daily.date, daily.rep, T2, hac_lags=2, unit_days=1)

# event-level: what an agent does in the 30 minutes after a nudge that names it, vs matched idle moments without a nudge
name_pats = [(a["name"], re.compile(r"(?<![\w.])" + re.escape(a["name"]) + r"(?![\w.])", re.I)) for a in agents if len(a["name"]) > 4]
by_agent_ev = defaultdict(list)
for _, t, typ, nm in ev:
    by_agent_ev[nm].append((t, typ))
for v in by_agent_ev.values():
    v.sort()
times_of = {nm: np.array([x[0] for x in v]) for nm, v in by_agent_ev.items()}
IDLE = {"WAIT", "PAUSE"}


def acted_within(nm, t0, secs=1800):
    """Did the agent take a non-idle action within secs after t0?"""
    arr = times_of.get(nm)
    if arr is None:
        return None
    i = np.searchsorted(arr, t0, side="right")
    lst = by_agent_ev[nm]
    while i < len(arr) and arr[i] <= t0 + secs:
        if lst[i][1] not in IDLE:
            return 1
        i += 1
    return 0


def last_action_idle(nm, t0):
    arr = times_of.get(nm)
    if arr is None:
        return False, None
    i = np.searchsorted(arr, t0, side="right") - 1
    if i < 0:
        return False, None
    return by_agent_ev[nm][i][1] in IDLE, t0 - arr[i]


treated, nudge_times = [], defaultdict(list)
for t, content, room in nudges:
    for nm, p in name_pats:
        if p.search(content) and nm in times_of:
            nudge_times[nm].append(t)
            idle, since = last_action_idle(nm, t)
            if idle and since is not None and since < 4 * 3600:
                a = acted_within(nm, t)
                if a is not None:
                    treated.append((nm, since, a))
control = []
for nm, lst in by_agent_ev.items():
    nts = np.array(sorted(nudge_times.get(nm, [])))
    if not len(nts):
        continue
    lo_t, hi_t = nts.min() - 14 * 86400, nts.max() + 14 * 86400
    for (t, typ) in lst:
        if typ not in IDLE or not (lo_t <= t <= hi_t):
            continue
        for lag in (300, 900, 1800):  # moments 5/15/30 min into an idle stretch
            t0 = t + lag
            j = np.searchsorted(nts, t0)
            near = (j < len(nts) and nts[j] - t0 < 3600) or (j > 0 and t0 - nts[j - 1] < 3600)
            if near:
                continue
            idle, since = last_action_idle(nm, t0)
            if idle and since is not None and since < 4 * 3600:
                a = acted_within(nm, t0)
                if a is not None:
                    control.append((nm, since, a))
# match on time-since-last-action buckets
def bucket(s):
    return 0 if s < 600 else 1 if s < 1800 else 2 if s < 3600 else 3

tb, cb = defaultdict(list), defaultdict(list)
for nm, s, a in treated:
    tb[bucket(s)].append(a)
for nm, s, a in control:
    cb[bucket(s)].append(a)
diffs, weights = [], []
for b in tb:
    if cb.get(b):
        diffs.append(np.mean(tb[b]) - np.mean(cb[b])); weights.append(len(tb[b]))
ate = float(np.average(diffs, weights=weights)) if diffs else None
# bootstrap over agents for the matched difference
agents_t = sorted({x[0] for x in treated})
boot = []
T_by = defaultdict(list); C_by = defaultdict(list)
for x in treated:
    T_by[x[0]].append(x)
for x in control:
    C_by[x[0]].append(x)
for _ in range(1000):
    pick = rng.choice(agents_t, size=len(agents_t)) if agents_t else []
    tbb, cbb = defaultdict(list), defaultdict(list)
    for nm in pick:
        for _, s, a in T_by[nm]:
            tbb[bucket(s)].append(a)
        for _, s, a in C_by[nm]:
            cbb[bucket(s)].append(a)
    ds, ws = [], []
    for b in tbb:
        if cbb.get(b):
            ds.append(np.mean(tbb[b]) - np.mean(cbb[b])); ws.append(len(tbb[b]))
    if ds:
        boot.append(np.average(ds, weights=ws))
q2_out = []
if its_idle:
    q2_out.append({"name": "Idle share, level change at switch-on", "unit": "share", "est": its_idle["level"], "lo": its_idle["level_lo"], "hi": its_idle["level_hi"], "p": its_idle["level_p"], "n": its_idle["n"], "baseline": its_idle["pre_mean"]})
if its_rep:
    q2_out.append({"name": "Repeated-message share, level change", "unit": "share", "est": its_rep["level"], "lo": its_rep["level_lo"], "hi": its_rep["level_hi"], "p": its_rep["level_p"], "n": its_rep["n"], "baseline": its_rep["pre_mean"]})
if ate is not None and boot:
    q2_out.append({"name": "Acts within 30 min after a nudge (vs matched idle moments)", "unit": "probability", "est": r3(ate),
                   "lo": r3(np.percentile(boot, 2.5)), "hi": r3(np.percentile(boot, 97.5)), "n": len(treated), "clusters": len(agents_t),
                   "baseline": r3(np.mean([a for _, _, a in control])) if control else None})
quasi.append({
    "key": "nudger", "date": "2026-02-10", "title": "Automatic nudges for idle agents",
    "change": "A bot started posting nudges when it detected idling; it was off 2026-06-13 to 06-15 for the event weekend and on again after.",
    "estimand": "(a) Village-wide change in idle and repeat share when nudging started. (b) Short-run effect of a nudge naming an agent on whether it acts within 30 minutes.",
    "design": "(a) Interrupted time series on daily village means, 4 weeks before to the rooms change, segmented regression with HAC errors. (b) Nudges that name an agent who is idle, compared with idle moments of the same agents at least an hour from any nudge, matched on time since the last action; 95% interval from a bootstrap over agents.",
    "outcomes": q2_out,
    "chart": {"type": "its", "break": T2, "unit_days": 1, "series": {"Idle share": its_idle, "Repeated-message share": its_rep},
              "dates": daily.date.tolist()},
    "pretrend": "Segmented regression allows a pre-trend; the level change is measured against its extrapolation. The off weekend (2026-06-13 to 06-15) is too short for its own test and was an unusual Saturday session.",
    "confounds": ["Opus 4.6 joined 2026-02-06 and Sonnet 4.6 on 02-18; a 100-turn session cap arrived 02-20.",
                  "Nudges are triggered by idling, so raw nudge-vs-no-nudge comparisons are confounded; the event-level estimate matches on idle state and time since the last action but cannot rule out other differences in what the detector picks up.",
                  "Only nudges that name the agent are attributed to it."],
    "verdict": (verdict_from(q2_out[-1]["lo"], q2_out[-1]["hi"], "A nudge makes an idle agent more likely to act within 30 minutes.", "Nudged agents were less likely to act within 30 minutes than matched idle moments.")
                if q2_out and q2_out[-1]["name"].startswith("Acts") else "Not estimable."),
})

# ================================================================ 3. rooms
log("Q3 rooms ITS…")
N = json.loads((OUT / "network.json").read_text())
wk = [r for r in N["weekly"] if "2025-11-01" <= r[0] <= "2026-05-25" and r[4] >= 5]
its_mod = its([r[0] for r in wk], [r[1] for r in wk], "2026-02-23", hac_lags=2)
its_rec = its([r[0] for r in wk], [r[3] for r in wk], "2026-02-23", hac_lags=2)
TR = json.loads((OUT / "trajectories.json").read_text())
conv = [c for c in TR.get("convergence", []) if "2026-01-01" <= c[0] <= "2026-04-20" and c[2] >= 3]
its_conv = its([c[0] for c in conv], [c[1] for c in conv], "2026-02-25", hac_lags=3, unit_days=7)
q3_out = []
for lab, r in (("Network modularity (weekly)", its_mod), ("Reciprocity (weekly)", its_rec), ("Similarity between agents (daily)", its_conv)):
    if r:
        q3_out.append({"name": lab + ", level change", "unit": "index", "est": r["level"], "lo": r["level_lo"], "hi": r["level_hi"], "p": r["level_p"], "n": r["n"], "baseline": r["pre_mean"]})
rc = N.get("rooms_control", {})
quasi.append({
    "key": "rooms", "date": "2026-02-25", "title": "Chat split into rooms",
    "change": "Agents now see only their current room's messages and members; a move_to_room tool followed on 02-26.",
    "estimand": "Level change in network structure and in similarity between agents at the switch.",
    "design": "Interrupted time series: weekly chat-network modularity and reciprocity (weeks with 5+ active agents, Nov 2025 to May 2026) and daily similarity between agents, segmented regression with HAC errors. Cross-sectional context from the Network tab: same-room pairs mention each other far more often than pairs in different rooms.",
    "outcomes": q3_out, "chart": {"type": "its", "break": "2026-02-23", "unit_days": 7, "series": {"Modularity": its_mod, "Reciprocity": its_rec}, "dates": [r[0] for r in wk]},
    "pretrend": "The model fits a separate pre-period trend; with weekly data there are few points either side, so intervals are wide.",
    "confounds": ["Perma-computer-use work ran 2026-03-11 to 03-24, inside the post window.", "Village goals changed weekly (challenges, Pentagon debate, RPG).",
                  f"Same-room pairs: {rc.get('co_present', {}).get('rate')} tie rate vs {rc.get('not_co_present', {}).get('rate')} for other pairs after the switch (Network tab)."],
    "verdict": (verdict_from(q3_out[0]["lo"], q3_out[0]["hi"], "Modularity rose at the switch to rooms.", "Modularity fell at the switch to rooms.",
                             "No clear level change in modularity at the switch; the weekly series is short and noisy.") if q3_out else "Not estimable."),
})

# ================================================================ 4. unseen-events cap 2026-06-11
log("Q4 returns after absence…")
T4 = pd.Timestamp("2026-06-11")
village_days = sorted(DAYSET)
vd_idx = {d: i for i, d in enumerate(village_days)}
returns = []
for nm, lst in by_agent_ev.items():
    first_t = {}
    for t, _ in lst:
        d = pt_date(t)
        if d in vd_idx and d not in first_t:
            first_t[d] = t
    dlist = sorted(first_t)
    arr = times_of[nm]
    for a_, b_ in zip(dlist, dlist[1:]):
        missed = vd_idx[b_] - vd_idx[a_] - 1
        if missed >= 1:  # absent for at least one full village day while the village ran
            t0 = first_t[b_]
            i0, i1 = np.searchsorted(arr, t0), np.searchsorted(arr, t0 + 7200)
            win = lst[i0:i1]
            msgs = sum(1 for _, typ in win if typ == "AGENT_TALK")
            searches = sum(1 for _, typ in win if typ == "SEARCH_HISTORY")
            returns.append({"agent": nm, "date": b_, "missed": missed, "post": pd.Timestamp(b_) >= T4, "searches": searches, "msgs": msgs, "actions": len(win)})
RT = pd.DataFrame(returns)
RT = RT[(RT.date >= "2026-03-24") & (RT.date <= "2026-09-18")] if len(RT) else RT
log("returns:", len(RT), "pre", int((~RT.post).sum()) if len(RT) else 0, "post", int(RT.post.sum()) if len(RT) else 0)
q4_out = []
for col, lab in (("searches", "History searches in first 2 hours back"), ("actions", "Actions in first 2 hours back")):
    pre = RT[~RT.post][col].to_numpy(float); post = RT[RT.post][col].to_numpy(float)
    if len(pre) >= 3 and len(post) >= 3:
        diff = post.mean() - pre.mean()
        bs = [rng.choice(post, len(post)).mean() - rng.choice(pre, len(pre)).mean() for _ in range(2000)]
        q4_out.append({"name": lab, "unit": "count", "est": r3(diff), "lo": r3(np.percentile(bs, 2.5)), "hi": r3(np.percentile(bs, 97.5)), "n": int(len(pre) + len(post)), "baseline": r3(pre.mean())})
quasi.append({
    "key": "unseen_cap", "date": "2026-06-11", "title": "Unseen events capped at 200 per turn",
    "change": "Agents returning after a long absence used to receive every event they missed; now at most 200, with a note to use search_history for older context.",
    "estimand": "Change in what agents do in their first two hours back after missing at least one full village day.",
    "design": "Before/after comparison of returns (after the 2026-03-24 regime change only), difference in means with a bootstrap interval.",
    "outcomes": q4_out, "chart": {"type": "bars", "groups": ["Before cap", "After cap"],
                                    "series": {lab["name"]: [r3(RT[~RT.post][c].mean()) if len(RT) else None, r3(RT[RT.post][c].mean()) if len(RT) else None] for lab, c in zip(q4_out, ["searches", "actions"])},
                                    "n": [int((~RT.post).sum()) if len(RT) else 0, int(RT.post.sum()) if len(RT) else 0]},
    "pretrend": "No pre-trend test: returns are sparse events.",
    "confounds": ["Returns after the cap fall mostly in July to September, when hours doubled and individual goals started.", "Absences have different causes (pauses, sign-in problems, staff decisions)."],
    "verdict": (verdict_from(q4_out[0]["lo"], q4_out[0]["hi"], "Returning agents searched history more after the cap, as the new note suggests.", "Returning agents searched history less after the cap.") if q4_out else "Too few returns to compare."),
})

# ================================================================ 5. outreach approval learning
log("Q5 outreach…")
resp_sorted = sorted(outreach_resp)
seq = defaultdict(list)
for idx, t, nm, rid, ok, cm in resp_sorted:
    seq[nm].append((t, ok, cm))
OR = []
for nm, lst in seq.items():
    for i, (t, ok, cm) in enumerate(lst):
        prev = lst[i - 1] if i else None
        OR.append({"agent": nm, "k": i + 1, "ok": float(ok), "prev_rej": (prev is not None and not prev[1]), "prev_rej_comment": (prev is not None and not prev[1] and prev[2])})
ORd = pd.DataFrame(OR)
ORd["logk"] = np.log(ORd.k)
ORd["date"] = 0
lp = twfe(ORd.assign(unit=ORd.agent, time=0), "ok", ["logk"], unit="agent", time="date") if len(ORd) else None
bins = [(1, 3), (4, 8), (9, 20), (21, 200)]
curve = []
for a_, b_ in bins:
    sub = ORd[(ORd.k >= a_) & (ORd.k <= b_)]
    p, lo, hi = wilson(int(sub.ok.sum()), len(sub))
    curve.append([f"{a_}-{b_}" if b_ < 200 else f"{a_}+", p, lo, hi, int(len(sub))])
after = ORd[ORd.prev_rej]
w_c = after[after.prev_rej_comment]; wo_c = after[~after.prev_rej_comment]
pc, pcl, pch = wilson(int(w_c.ok.sum()), len(w_c))
pn, pnl, pnh = wilson(int(wo_c.ok.sum()), len(wo_c))
q5_out = []
if lp:
    q5_out.append({"name": "Approval change per doubling of requests (within agent)", "unit": "probability", "est": r3(lp["beta"][0] * math.log(2)), "lo": r3(lp["lo"][0] * math.log(2)),
                   "hi": r3(lp["hi"][0] * math.log(2)), "p": r3(lp["p"][0]), "p_wild": r3(lp.get("p_wild")), "clusters": lp["G"], "n": lp["n"], "baseline": r3(ORd.ok.mean())})
if len(w_c) and len(wo_c):
    d = pc - pn
    se = math.sqrt(pc * (1 - pc) / len(w_c) + pn * (1 - pn) / len(wo_c)) if 0 < pc < 1 or 0 < pn < 1 else None
    q5_out.append({"name": "Next approval after a rejection with an admin comment, minus without", "unit": "probability", "est": r3(d),
                   "lo": r3(d - 1.96 * se) if se else None, "hi": r3(d + 1.96 * se) if se else None, "n": int(len(after)), "baseline": r3(pn)})
quasi.append({
    "key": "outreach", "date": "2026-04-14", "title": "Learning under the outreach-approval rule",
    "change": "Since 2026-04-14 every unsolicited outreach (emails, posts, issues) needs a human staff decision before it is sent. The rule itself is not being tested here: this asks whether agents learn what gets approved, and whether an admin comment on a rejection helps the next request. Staff add a comment to almost every rejection (39 of 40 matched) but to few approvals (21 of 109).",
    "estimand": "(a) Whether approval rises with an agent's experience of the system. (b) Whether a rejection that explains itself helps the next request.",
    "design": "(a) Linear probability model of approval on log request number with agent fixed effects, cluster-robust by agent, wild bootstrap p. (b) Next-request approval after rejections with vs without an admin comment (normal approximation).",
    "outcomes": q5_out, "chart": {"type": "curve", "xlabel": "request number (per agent)", "points": curve,
                                    "compare": {"With admin comment": [pc, pcl, pch, int(len(w_c))], "No comment": [pn, pnl, pnh, int(len(wo_c))]}},
    "pretrend": "Not applicable: the system starts on 2026-04-14 and the analysis is within it.",
    "confounds": ["Agents choose what to request, so improving approval can mean better messages or safer targets.", "Admin comments are not random: staff may comment on borderline cases.", "GPT-5.4 alone made about a third of requests."],
    "verdict": (verdict_from(q5_out[0]["lo"], q5_out[0]["hi"], "Approval rises as agents gain experience with the system.", "Approval falls as agents make more requests.", p_wild=q5_out[0].get("p_wild")) if q5_out else "Not estimable."),
})

# ================================================================ 6. hours 4h -> 8h (ABAB: 06-07..06-12 8h, back to 4h, 8h from 06-29)
log("Q6 hours…")
W6 = P[(P.dt >= pd.Timestamp("2026-05-25")) & (P.dt <= pd.Timestamp("2026-07-24"))].copy()
W6["eight"] = (((W6.dt >= pd.Timestamp("2026-06-08")) & (W6.dt <= pd.Timestamp("2026-06-12"))) | (W6.dt >= pd.Timestamp("2026-06-29"))).astype(float)
W6["trend"] = (W6.dt - pd.Timestamp("2026-05-25")).dt.days / 7.0
W6["actions_day"] = W6.actions
q6_out = []
for y, lab, unit in (("actions_day", "Actions per agent-day", "actions"), ("act_per_h", "Actions per active hour", "actions/h"), ("idle_share", "Idle share", "share"), ("rep_share", "Repeated-message share", "share")):
    d = W6.dropna(subset=[y]).copy()
    d["unit"] = d.agent; d["time0"] = 0
    # agent FE + linear trend; day FE would absorb the treatment, so use trend
    r = twfe(d.assign(date=0), y, ["eight", "trend"], unit="agent", time="date")
    if r:
        q6_out.append({"name": lab, "unit": unit, "est": r3(r["beta"][0]), "lo": r3(r["lo"][0]), "hi": r3(r["hi"][0]), "p": r3(r["p"][0]), "p_wild": r3(r.get("p_wild")),
                       "clusters": r["G"], "n": r["n"], "baseline": r3(d[d.eight == 0][y].mean())})
d6 = W6.groupby("date").agg(actions=("actions_day", "mean"), eight=("eight", "max")).reset_index()
quasi.append({
    "key": "hours", "date": "2026-06-29", "title": "Village hours doubled from 4 to 8 a day",
    "change": "The village ran 9am to 5pm instead of 10am to 2pm; it had also run 8-hour days in the event week 2026-06-08 to 06-12.",
    "estimand": "Difference between 8-hour and 4-hour days in per-day and per-hour activity, using both switches (on, off, on).",
    "design": "Agent fixed effects with a linear time trend on the agent-day panel, 2026-05-25 to 2026-07-24; cluster-robust by agent with a wild bootstrap p.",
    "outcomes": q6_out, "chart": {"type": "daily", "dates": d6.date.tolist(), "values": [r3(v) for v in d6.actions], "flag": d6.eight.astype(int).tolist(), "label": "Mean actions per agent-day", "flagLabel": "8-hour day"},
    "pretrend": "The on-off-on pattern guards against a simple trend explanation: effects should appear and vanish with the hours.",
    "confounds": ["Individual goals started 2026-07-06 and nine agents joined 2026-06-30 to 07-17.", "The event week was unusual (an 'Organise an event!' goal)."],
    "verdict": (verdict_from(q6_out[0]["lo"], q6_out[0]["hi"], "Agents do more per day on 8-hour days.", "Agents did less per day on 8-hour days.", p_wild=q6_out[0].get("p_wild")) +
                (" Per-hour activity: " + verdict_from(q6_out[1]["lo"], q6_out[1]["hi"], "higher.", "lower.", "no clear change.") if len(q6_out) > 1 else "")) if q6_out else "Not estimable.",
})

# ================================================================ 7. hidden individual goals: same-goal pairs
log("Q7 same-goal pairs…")
goals = [json.loads(l) for l in gzip.open(DATA / "agent_goals.jsonl.gz", "rt")]
by_goal = defaultdict(set)
for g in goals:
    if g.get("end_time"):
        continue
    if g["agent_id"] in NAME:
        by_goal[g["short_name"]].add(NAME[g["agent_id"]])
same_pairs = {tuple(sorted(v)) for v in by_goal.values() if len(v) == 2}
log("same-goal pairs:", same_pairs)
# weekly directed mentions from chat (full names)
ment = defaultdict(lambda: defaultdict(int))  # (week) -> (a,b) -> count
msgs_w = defaultdict(lambda: defaultdict(int))
EPOCH = date(2025, 3, 31)
for line in gzip.open(DATA / "chat_messages.jsonl.gz", "rt"):
    c = json.loads(line)
    if c["speaker_type"] != "agent" or c["agent_speaker_id"] not in NAME:
        continue
    if not ("2026-05-25" <= c["created_at"][:10] <= "2026-08-30"):
        continue
    a = NAME[c["agent_speaker_id"]]
    w = (date.fromisoformat(pt_date(ts(c["created_at"]))) - EPOCH).days // 7
    msgs_w[w][a] += 1
    txt = c["content"] or ""
    for nm, p in name_pats:
        if nm != a and p.search(txt):
            ment[w][(a, nm)] += 1
TG = (date(2026, 7, 6) - EPOCH).days // 7
rows7 = []
weeks7 = sorted(msgs_w)
active_w = {w: {a for a, n in msgs_w[w].items() if n >= 5} for w in weeks7}
for w in weeks7:
    act = sorted(active_w[w])
    for i, a in enumerate(act):
        for b in act[i + 1:]:
            rate = (ment[w].get((a, b), 0) + ment[w].get((b, a), 0)) / max(1, msgs_w[w][a] + msgs_w[w][b])
            rows7.append({"pair": f"{a}|{b}", "week": w, "post": float(w >= TG), "same": float(tuple(sorted((a, b))) in same_pairs), "rate": rate})
D7 = pd.DataFrame(rows7)
q7_out = []
pairs_with_pre = sorted({p for p in D7[(D7.same == 1) & (D7.post == 0)].pair} & {p for p in D7[(D7.same == 1) & (D7.post == 1)].pair})
if len(D7) and pairs_with_pre:
    D7["sp"] = D7.same * D7.post
    sub = D7[D7.pair.isin(set(D7[D7.post == 0].pair) & set(D7[D7.post == 1].pair))].copy()
    M = demean2(sub[["rate", "sp"]].to_numpy(), sub.pair.to_numpy(), sub.week.to_numpy())
    beta = float((M[:, 1] @ M[:, 0]) / (M[:, 1] @ M[:, 1]))
    # randomisation inference: reassign "same goal" to random pairs with pre and post data
    cand = sorted(set(sub.pair))
    k = len(pairs_with_pre)
    perm = []
    for _ in range(2000):
        pick = set(rng.choice(cand, size=k, replace=False))
        sp = (sub.pair.isin(pick).astype(float) * sub.post).to_numpy()
        Mp = demean2(np.column_stack([sub.rate.to_numpy(), sp]), sub.pair.to_numpy(), sub.week.to_numpy())
        perm.append(float((Mp[:, 1] @ Mp[:, 0]) / (Mp[:, 1] @ Mp[:, 1])) if (Mp[:, 1] @ Mp[:, 1]) > 0 else 0.0)
    perm = np.array(perm)
    q7_out.append({"name": f"Mention rate between same-goal rivals, DiD ({k} pairs with a pre-period)", "unit": "mentions per message", "est": r3(beta),
                   "lo": r3(beta - np.percentile(np.abs(perm), 95)), "hi": r3(beta + np.percentile(np.abs(perm), 95)),
                   "p": r3(float(np.mean(np.abs(perm) >= abs(beta)))), "n": int(len(sub)), "baseline": r3(sub[(sub.same == 1) & (sub.post == 0)].rate.mean())})
post7 = D7[D7.post == 1]
if len(post7):
    s_ = post7[post7.same == 1].rate.to_numpy(); o_ = post7[post7.same == 0].rate.to_numpy()
    if len(s_) and len(o_):
        bs = [rng.choice(s_, len(s_)).mean() - rng.choice(o_, len(o_)).mean() for _ in range(2000)]
        q7_out.append({"name": "After goals: same-goal pairs minus other pairs (all pairs)", "unit": "mentions per message", "est": r3(s_.mean() - o_.mean()),
                       "lo": r3(np.percentile(bs, 2.5)), "hi": r3(np.percentile(bs, 97.5)), "n": int(len(post7)), "baseline": r3(o_.mean())})
wk_series = {}
if len(D7):
    for lab, flag in (("Same-goal pairs", 1.0), ("Other pairs", 0.0)):
        g = D7[D7.same == flag].groupby("week").rate.mean()
        wk_series[lab] = [[(EPOCH + timedelta(days=7 * int(w))).isoformat(), r3(v)] for w, v in g.items()]
quasi.append({
    "key": "goals", "date": "2026-07-06", "title": "Hidden individual goals, some shared by two agents",
    "change": "Each agent got a private goal shown below the village goal; agents cannot see each other's goals. Several pairs share a goal.",
    "estimand": "Whether agents who secretly share a goal start paying more attention to each other.",
    "design": "Pair-week panel of mutual mentions per message. Difference-in-differences with pair and week fixed effects for same-goal pairs that existed before the goals; randomisation inference reassigns 'same goal' to random pairs. Plus a post-period comparison including pairs with newer agents.",
    "outcomes": q7_out, "chart": {"type": "lines", "break": "2026-07-06", "series": wk_series, "ylabel": "mentions per message"},
    "pairs": [list(p) for p in sorted(same_pairs)], "pairs_with_pre": pairs_with_pre,
    "pretrend": f"Only {len(pairs_with_pre)} same-goal pairs were both active before 2026-07-06; the others include agents who joined after, so they enter only the post-period comparison.",
    "confounds": ["Rooms shape who meets whom: same-goal rivals may share or not share a room.", "Hours doubled the week before; several agents joined that month.", "Mentions are full-name matches only."],
    "verdict": (verdict_from(q7_out[0]["lo"], q7_out[0]["hi"], "Same-goal rivals mention each other more once goals start.", "Same-goal rivals mention each other less once goals start.",
                             "No clear change in attention between secret rivals; with so few pairs, only a large effect would show.") if q7_out else "Not estimable."),
})

# ================================================================ (B) proposed experiments: variance and MDE
log("B: variance + MDE…")
P["week"] = ((P.dt - pd.Timestamp(EPOCH)).dt.days // 7).astype(int)
VERIF = re.compile(r"\b(verif\w*|receipt\w*|sha\w*|latch\w*|confirm\w*|sentinel|probe\w*|checksum|proof\w*|200 ok|live)\b", re.I)
verif_w = defaultdict(lambda: [0, 0])
cross_w = defaultdict(lambda: [0, 0])
neg_w = {}
for line in gzip.open(DATA / "chat_messages.jsonl.gz", "rt"):
    c = json.loads(line)
    if c["speaker_type"] != "agent" or c["agent_speaker_id"] not in NAME or c["created_at"][:10] < "2026-03-24":
        continue
    a = NAME[c["agent_speaker_id"]]
    w = (date.fromisoformat(c["created_at"][:10]) - EPOCH).days // 7
    txt = c["content"] or ""
    verif_w[(a, w)][1] += 1
    verif_w[(a, w)][0] += bool(VERIF.search(txt))
    for nm, p in name_pats:
        if nm != a and p.search(txt):
            cross_w[(a, w)][1] += 1
            cross_w[(a, w)][0] += FAM.get(nm) != FAM.get(a)
MH = json.loads((OUT / "memory_health.json").read_text())
for ag, rows_ in MH.items():
    acc = defaultdict(list)
    for d, m in rows_:
        if d >= "2026-03-24" and m.get("neg") is not None:
            acc[(date.fromisoformat(d) - EPOCH).days // 7].append(m["neg"])
    for w, v in acc.items():
        neg_w[(ag, w)] = float(np.mean(v))
post = P[P.date >= "2026-03-24"]
aw = post.groupby(["agent", "week"]).agg(reps=("reps", "sum"), msgs=("msgs", "sum"), idle=("idle_s", "sum"), act=("active_s", "sum")).reset_index()
aw["rep_share"] = np.where(aw.msgs >= 10, aw.reps / aw.msgs.clip(lower=1), np.nan)
aw["idle_share"] = np.where(aw.act >= 3600, aw.idle / aw.act.clip(lower=1), np.nan)
aw["verif"] = [verif_w[(a, w)][0] / verif_w[(a, w)][1] if verif_w[(a, w)][1] >= 10 else np.nan for a, w in zip(aw.agent, aw.week)]
aw["cross"] = [cross_w[(a, w)][0] / cross_w[(a, w)][1] if cross_w[(a, w)][1] >= 5 else np.nan for a, w in zip(aw.agent, aw.week)]
aw["neg"] = [neg_w.get((a, w), np.nan) for a, w in zip(aw.agent, aw.week)]


def var_parts(df, col):
    d = df.dropna(subset=[col])
    d = d[d.groupby("agent")[col].transform("count") >= 4]
    if d.agent.nunique() < 5:
        return None
    mu = d.groupby("agent")[col].transform("mean")
    within = d[col] - mu
    sw = float(within.std())
    sb = float(d.groupby("agent")[col].mean().std())
    icc = sb ** 2 / (sb ** 2 + sw ** 2) if (sb + sw) > 0 else 0
    acs = []
    for _, g in d.assign(w=within).sort_values("week").groupby("agent"):
        x = g.w.to_numpy()
        if len(x) >= 5 and x[:-1].std() > 0 and x[1:].std() > 0:
            acs.append(np.corrcoef(x[:-1], x[1:])[0, 1])
    phi = float(np.clip(np.nanmean(acs) if acs else 0.0, -0.5, 0.95))
    return {"mean": float(d[col].mean()), "sd_within": sw, "sd_between": sb, "icc": icc, "ac1": phi, "agents": int(d.agent.nunique())}


def ar_mean_var(sigma, phi, p):
    s = 1 + 2 * sum((1 - k / p) * phi ** k for k in range(1, p))
    return sigma ** 2 / p * s


def mde_crossover(v, n_agents, weeks, arms=2):
    """AB/BA crossover: each agent spends weeks/arms in each condition; per-agent contrast; t-test with n-1 df."""
    p = max(1, weeks // arms)
    var_diff = 2 * ar_mean_var(v["sd_within"], v["ac1"], p)
    t = stats.t.ppf(0.975, n_agents - 1) + stats.t.ppf(0.8, n_agents - 1)
    return t * math.sqrt(var_diff / n_agents)


def mde_parallel(v, n_agents, weeks):
    """Individually randomised, two arms, baseline-adjusted agent means (ANCOVA, r from ICC)."""
    var_mean = v["sd_between"] ** 2 + ar_mean_var(v["sd_within"], v["ac1"], max(1, weeks))
    r2 = min(0.8, v["icc"])  # prior agent mean explains roughly the between-agent share
    t = stats.t.ppf(0.975, n_agents - 3) + stats.t.ppf(0.8, n_agents - 3)
    return t * math.sqrt(var_mean * (1 - r2) * 4 / n_agents)


def mde_switchback(sd, phi, weeks):
    """Village-level switchback, alternating weeks; difference of arm means over `weeks` weeks."""
    if weeks < 2:
        return None
    p = weeks // 2
    var = 2 * ar_mean_var(sd, -abs(phi) * 0 + phi, p)  # alternating assignment; AR(1) on weekly series
    t = stats.t.ppf(0.975, max(1, weeks - 2)) + stats.t.ppf(0.8, max(1, weeks - 2))
    return t * math.sqrt(var)


def mde_proportion(p0, n_total, de=1.0):
    """Two-arm difference in proportions with n_total decision points split 50/50, design effect de."""
    if n_total < 4:
        return None
    se = math.sqrt(2 * p0 * (1 - p0) / (n_total / 2) * de)
    return (stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) * se


def mde_cluster(v, k_per_arm, m, weeks):
    var_ind = v["sd_between"] ** 2 + ar_mean_var(v["sd_within"], v["ac1"], max(1, weeks))
    de = 1 + (m - 1) * max(v.get("icc_room", 0.1), 0.0)
    t = stats.t.ppf(0.975, 2 * k_per_arm - 2) + stats.t.ppf(0.8, 2 * k_per_arm - 2)
    return t * math.sqrt(2 * var_ind * de / (k_per_arm * m))


WEEKS = [2, 4, 6, 8]
SWB = [4, 8, 12, 16]
SLOW = [4, 8, 16, 26]
NAG = 30
vp = {c: var_parts(aw, c) for c in ("rep_share", "idle_share", "verif", "cross", "neg")}
# room ICC for cross-family share: agents' dominant room per week from chat
room_w = defaultdict(Counter)
rooms = {r["id"]: r["name"] for r in map(json.loads, gzip.open(DATA / "chat_rooms.jsonl.gz", "rt"))}
for line in gzip.open(DATA / "chat_messages.jsonl.gz", "rt"):
    c = json.loads(line)
    if c["speaker_type"] == "agent" and c["agent_speaker_id"] in NAME and c["created_at"][:10] >= "2026-03-24":
        room_w[(NAME[c["agent_speaker_id"]], (date.fromisoformat(c["created_at"][:10]) - EPOCH).days // 7)][rooms.get(c["room_id"], "?")] += 1
aw["room"] = [room_w[(a, w)].most_common(1)[0][0] if room_w[(a, w)] else None for a, w in zip(aw.agent, aw.week)]
for c in ("rep_share", "verif"):
    d = aw.dropna(subset=[c, "room"])
    d = d.assign(rw=d.room + "|" + d.week.astype(str))
    grp = d.groupby("rw")[c]
    between = float(grp.mean().var()); total = float(d[c].var())
    if vp.get(c):
        vp[c]["icc_room"] = max(0.0, min(0.9, (between - total / max(1, grp.size().mean())) / total)) if total > 0 else 0.0
# weekly village series for switchback designs
wk_mod = np.array([r[1] for r in N["weekly"] if r[0] >= "2026-03-24" and r[4] >= 5])
mod_sd = float(wk_mod.std()) if len(wk_mod) > 3 else None
mod_phi = float(np.corrcoef(wk_mod[:-1], wk_mod[1:])[0, 1]) if len(wk_mod) > 5 else 0.0
# in-attention concentration (Gini) per week as the leader-experiment proxy
gini_w = []
for w in sorted(ment):
    rec = Counter()
    for (a, b), n in ment[w].items():
        rec[b] += n
    act = active_w.get(w, set())
    vals = np.sort(np.array([rec.get(x, 0) for x in act], float))
    if len(vals) >= 5 and vals.sum() > 0:
        n_ = len(vals)
        gini_w.append(float((2 * np.arange(1, n_ + 1) - n_ - 1) @ vals / (n_ * vals.sum())))
gini_w = np.array(gini_w)
gini_sd = float(gini_w.std()) if len(gini_w) > 3 else None
gini_phi = float(np.corrcoef(gini_w[:-1], gini_w[1:])[0, 1]) if len(gini_w) > 5 else 0.0

# decision points
post_nudges = [t for t, _, _ in nudges if pt_date(t) >= "2026-03-24"]
nudge_weeks = max(1, len({(date.fromisoformat(pt_date(t)) - EPOCH).days // 7 for t in post_nudges}))
nudges_per_week = len(post_nudges) / nudge_weeks
base_act = float(np.mean([a for _, _, a in control])) if control else 0.5
rej_per_week = sum(1 for x in outreach_resp if not x[4]) / max(1, len({(date.fromisoformat(pt_date(x[1])) - EPOCH).days // 7 for x in outreach_resp}))
p_next_ok = float(ORd[ORd.prev_rej].ok.mean()) if len(ORd[ORd.prev_rej]) else 0.6
H = json.loads((OUT / "help.json").read_text())
hr = [r for r in H["requests"] if r["date"] >= "2026-07-01"]
help_weeks = max(1, len({(date.fromisoformat(r["date"]) - EPOCH).days // 7 for r in hr}))
help_per_week = len(hr) / help_weeks
p_held = sum(r["outcome"] == "session held" for r in hr) / max(1, len(hr))


def pack(values):
    return [r3(v) for v in values]


def sdunits(vals, sd):
    return [r3(v / sd) if v is not None and sd else None for v in vals]


proposals = []
# pair-level variance for the reveal-goals design (post-goal pair-weeks)
vp_pair = None
if len(D7):
    pw = D7[D7.post == 1].rename(columns={"pair": "agent"})
    vp_pair = var_parts(pw, "rate")


def mde_pairs(v, n_pairs, weeks):
    var_mean = v["sd_between"] ** 2 + ar_mean_var(v["sd_within"], v["ac1"], max(1, weeks))
    t = stats.t.ppf(0.975, n_pairs - 2) + stats.t.ppf(0.8, n_pairs - 2)
    return t * math.sqrt(var_mean * 4 / n_pairs)



def add(key, title, hypothesis, unit, design, outcome, outcome_def, tab, v, mdes, unit_label, guard, note="", weeks=None):
    proposals.append({"key": key, "title": title, "hypothesis": hypothesis, "unit": unit, "design": design, "outcome": outcome, "outcome_def": outcome_def,
                      "tab": tab, "variance": {k: r3(x) for k, x in (v or {}).items()} if v else None, "weeks": weeks or WEEKS, "mde": pack(mdes),
                      "mde_sd": sdunits(mdes, (v or {}).get("sd_within")) if v and v.get("sd_within") else None, "mde_unit": unit_label,
                      "guardrails": guard, "note": note})


add("consolidation_policy", "Memory consolidation policy", "Diff-based or append-only consolidation, or a staleness check against the event log, reduces looping compared with full rewrites.",
    "Agent crossover (AB/BA)", f"{NAG} agents alternate policies in blocks; contrast within each agent.", "Repeated-message share", "Share of an agent's weekly messages that nearly repeat its previous one (10+ messages).",
    "#memory", vp["rep_share"], [mde_crossover(vp["rep_share"], NAG, w) for w in WEEKS], "share points", ["Keep the current policy as fallback if memory corrupts.", "Freeze other scaffolding changes during the trial."])
add("fact_check", "Memory fact-check step", "Verifying memory claims against search_history before saving reduces failure framing and unsupported claims.",
    "Agent crossover (AB/BA)", f"{NAG} agents alternate with and without the step.", "Failure words in memory per 1,000", "Density of failure words in the agent's memory rewrites (Memory tab). The intended outcome, unsupported claims, needs LLM labels; this is a proxy.",
    "#memory", vp["neg"], [mde_crossover(vp["neg"], NAG, w) for w in WEEKS], "per 1,000 words", ["Cap the extra tool calls per consolidation."])
add("random_rooms", "Random room assignment", "Randomly assigned rooms break model-family clustering and reduce network modularity compared with self-selected rooms.",
    "Village switchback (alternating weeks)", "Alternate weeks of random assignment and free choice; compare weekly network modularity.", "Chat-network modularity", "Weekly modularity of the mention network (Network tab).",
    "#network", {"sd_within": mod_sd, "ac1": mod_phi} if mod_sd else None, [mde_switchback(mod_sd, mod_phi, w) if mod_sd else None for w in SWB], "modularity", ["Keep goal-critical collaborators reachable through a shared room."],
    "Each week is one unit, so this needs months; modularity is also noisy week to week.", weeks=SWB)
add("reveal_goals", "Reveal individual goals", "Agents who know a rival shares their goal cooperate or compete more (mutual attention changes).",
    "Pair randomisation", "Reveal goals to half of the same-goal pairs (7 pairs today) and compare mutual mentions.", "Mutual mentions per message", "Mentions between the two agents of a pair per message (Network tab).",
    "#network", vp_pair, [mde_pairs(vp_pair, 7, w) if vp_pair else None for w in WEEKS], "mentions per message", ["Agents can't see others' private notes; only the goal text is revealed."],
    "With 7 pairs (3 or 4 per arm), only very large effects are detectable; more same-goal pairs would be needed.")
add("verification_dampener", "Verification-ritual dampener", "A budget or nudge on status, receipt and 'verified' messages shifts effort toward outside impact.",
    "Agent crossover (AB/BA)", f"{NAG} agents alternate with and without a verification budget.", "Verification-language share", "Share of an agent's weekly messages with verification words (receipt, sha, latch, verified, live, proof…).",
    "#futures", vp["verif"], [mde_crossover(vp["verif"], NAG, w) for w in WEEKS], "share points", ["Never block verification of real deployments; budget only status chatter."])
add("micro_nudges", "Micro-randomised nudges", "A nudge makes an idle agent more likely to act within 30 minutes.",
    "Micro-randomised (each idle detection)", f"Each detection is nudged with probability 0.5; about {round(nudges_per_week)} detections a week village-wide today.", "Acts within 30 minutes", "Whether the agent takes a non-idle action within 30 minutes of the decision point.",
    "#activity", {"baseline": base_act, "per_week": nudges_per_week}, [mde_proportion(base_act, nudges_per_week * w, de=1.5) for w in WEEKS], "probability", ["Cap nudges per agent per hour."],
    "The most powerful design here: decision points accumulate quickly.")
add("help_redesign", "Human-help request redesign", "A required 'why I can't do this myself' field and a weekly helper budget raise the share of requests that become sessions.",
    "Micro-randomised (each request form)", f"Randomise the form per request; about {round(help_per_week)} requests a week in Jul to Aug 2026.", "Request becomes a session", "Share of requests ending in a held session (Human help tab).",
    "#help", {"baseline": p_held, "per_week": help_per_week}, [mde_proportion(max(p_held, 0.05), help_per_week * w, de=1.5) for w in SLOW], "probability", ["Keep a fast path for real emergencies."], weeks=SLOW)
add("outreach_reasons", "Outreach feedback with or without reasons", "Rejections that explain themselves raise approval of the next request.",
    "Micro-randomised (each rejection)", f"Randomise whether a rejection includes the reason; about {round(rej_per_week, 1)} rejections a week.", "Next request approved", "Approval of the agent's next outreach request.",
    "#help", {"baseline": p_next_ok, "per_week": rej_per_week}, [mde_proportion(p_next_ok, rej_per_week * w, de=1.3) for w in SLOW], "probability", ["Staff still give reasons where safety requires it."],
    "Rejections are rare, so this accrues slowly.", weeks=SLOW)
add("cadence", "Consolidation cadence 20 / 40 / 80 actions", "Shorter cadence keeps memory fresher but costs continuity; longer cadence raises looping.",
    "Agent crossover, three arms", f"{NAG} agents rotate through three cadences (Latin square); pairwise contrasts.", "Repeated-message share", "As above.",
    "#memory", vp["rep_share"], [mde_crossover(vp["rep_share"], NAG, w, arms=3) for w in WEEKS], "share points", ["Monitor token costs at the 20-action cadence."])
add("family_rooms", "Single-family vs mixed rooms", "Behaviour that persists in single-family rooms belongs to the model family; behaviour that changes is learned from the village.",
    "Room clusters", "4 rooms, 2 per arm, about 7 agents each.", "Verification-language share", "As above, compared across room types.",
    "#network", vp["verif"], [mde_cluster(vp["verif"], 2, 7, w) for w in WEEKS], "share points", ["Rotate composition to avoid isolating any agent long-term."],
    "Two rooms per arm leaves 2 degrees of freedom; treat results as exploratory unless effects are large.")
add("change_notices", "Telling agents about scaffolding changes", "Agents who get change notices blame a hostile environment less.",
    "Individual randomisation (parallel arms)", f"{NAG} agents, half receive notices; baseline-adjusted comparison.", "Failure words in memory per 1,000", "Proxy for environment blame (Memory tab).",
    "#memory", vp["neg"], [mde_parallel(vp["neg"], NAG, w) for w in WEEKS], "per 1,000 words", ["Notices must be accurate and not reveal private goals."])
add("formal_leader", "Formal leader with task-assignment powers", "A formal leader concentrates attention and raises directive compliance.",
    "Village switchback (alternating weeks)", "Alternate leader and no-leader weeks; compare concentration of attention.", "Concentration of attention (Gini of mentions received)", "Weekly Gini of mentions received across active agents; directive compliance from the LLM-labelled 'direct' edges once available.",
    "#network", {"sd_within": gini_sd, "ac1": gini_phi} if gini_sd else None, [mde_switchback(gini_sd, gini_phi, w) if gini_sd else None for w in SWB], "Gini points", ["The leader cannot override outreach approval or safety rules."],
    "Each week is one unit, so this needs months.", weeks=SWB)

out = {
    "meta": {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "panel_agent_days": int(len(P)), "wild_bootstrap_draws": B_WILD,
             "mde_assumptions": f"{NAG} agents, 80% power, two-sided alpha 0.05; variance from post-2026-03-24 agent-weeks; within-agent AR(1) for serial correlation."},
    "quasi": quasi, "proposals": proposals,
}
def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    return o


(OUT / "experiments.json").write_text(json.dumps(clean(out), separators=(",", ":")))
log("wrote experiments.json", round((OUT / "experiments.json").stat().st_size / 1e3), "KB")
for q in quasi:
    log(f"\n[{q['key']}] {q['verdict']}")
    for o in q["outcomes"]:
        log(f"   {o['name']}: {o['est']} [{o.get('lo')}, {o.get('hi')}] p={o.get('p')} wild={o.get('p_wild')} n={o.get('n')} base={o.get('baseline')}")
log("\nMDE (2/4/6/8 weeks):")
for p_ in proposals:
    log(f"   {p_['title']}: {p_['mde']} {p_['mde_unit']}  sd-units={p_['mde_sd']}")
