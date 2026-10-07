"""Data anchors for the Futures tab → analysis/out/futures.json.

Per-agent behaviour metrics against join date (split by scaffolding regime),
the human-help request mix over time, and monthly rates of a few language
markers that later research regimes would build on. Stdlib only.
"""
import bisect
import gzip
import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"
PT = ZoneInfo("America/Los_Angeles")
CUTOVER = "2026-03-24"
EPOCH = date(2025, 4, 2)
MIN_DAYS = 5
random.seed(7)


def pt_date(ts):
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(PT).date().isoformat()


def years(d):
    return (date.fromisoformat(d) - EPOCH).days / 365.25


agents = {a["id"]: a for a in map(json.loads, gzip.open(DATA / "agents.jsonl.gz", "rt"))}
by_name = {a["name"]: a for a in agents.values()}
S = json.loads((OUT / "strips.json").read_text())
H = json.loads((OUT / "help.json").read_text())
offs = [d["o"] for d in S["days"]]
day_of = lambda v: S["days"][max(0, bisect.bisect_right(offs, v) - 1)]["date"]
regime = lambda d: "post" if d >= CUTOVER else "pre"

# ---------- per-agent, per-regime metrics ----------
m = defaultdict(lambda: {"days": set(), "talk": 0, "rep": 0, "idle": 0.0, "drawn": 0.0, "help": 0, "out_ok": 0, "out_n": 0})
for a in S["agents"]:
    nm = a["name"]
    for arr, key in ((a["talk"], "talk"), (a["rep"], "rep")):
        for v in arr:
            d = day_of(v)
            r = m[(nm, regime(d))]
            r[key] += 1
            r["days"].add(d)
    sg = a["segs"]
    for i in range(0, len(sg), 3):
        d = day_of(sg[i])
        r = m[(nm, regime(d))]
        r["days"].add(d)
        r["drawn"] += sg[i + 1]
        if sg[i + 2] in (3, 4):  # waiting, paused
            r["idle"] += sg[i + 1]
for q in H["requests"]:
    m[(q["agent"], regime(q["date"]))]["help"] += 1

for line in gzip.open(DATA / "events.jsonl.gz", "rt"):
    e = json.loads(line)
    d = e["data"]
    if d.get("actionType") == "OUTREACH_APPROVAL_RESPONSE":
        a = agents.get(d.get("agentId"))
        if a:
            r = m[(a["name"], regime(pt_date(e["created_at"])))]
            r["out_n"] += 1
            r["out_ok"] += str(d.get("approval")) == "True"

METRICS = {
    "repeat": {"label": "Repeated messages", "unit": "share of messages", "fmt": "pct"},
    "idle": {"label": "Waiting or paused", "unit": "share of drawn time", "fmt": "pct"},
    "msgs": {"label": "Messages per active day", "unit": "messages", "fmt": "num"},
    "help": {"label": "Human-help requests per active day", "unit": "requests", "fmt": "num2"},
    "outreach": {"label": "Outreach approval rate", "unit": "share approved", "fmt": "pct"},
}
points = []
for (nm, reg), r in m.items():
    if nm not in by_name or len(r["days"]) < MIN_DAYS:
        continue
    join = by_name[nm]["created_at"][:10]
    nd, nmsg = len(r["days"]), r["talk"] + r["rep"]
    vals = {
        "repeat": r["rep"] / nmsg if nmsg >= 50 else None,
        "idle": r["idle"] / r["drawn"] if r["drawn"] > 3600 else None,
        "msgs": nmsg / nd,
        "help": r["help"] / nd,
        "outreach": r["out_ok"] / r["out_n"] if r["out_n"] >= 5 else None,
    }
    points.append({"agent": nm, "join": join, "regime": reg, "days": nd,
                   **{k: (round(v, 4) if v is not None else None) for k, v in vals.items()}})


def ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def spearman(xs, ys):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[o[k]] = (i + j) / 2
            i = j + 1
        return rk
    rx, ry = rank(xs), rank(ys)
    a, b = ols(rx, ry)
    sx = math.sqrt(sum((x - sum(rx) / len(rx)) ** 2 for x in rx))
    sy = math.sqrt(sum((y - sum(ry) / len(ry)) ** 2 for y in ry))
    return b * sx / sy if sy else 0.0


fits = {}
for key in METRICS:
    fits[key] = {}
    for reg in ("pre", "post"):
        pts = [(years(p["join"]), p[key]) for p in points if p["regime"] == reg and p[key] is not None]
        if len(pts) < 5:
            fits[key][reg] = None
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        lo, hi = min(xs), max(xs)
        grid = [lo + (hi - lo) * i / 24 for i in range(25)]
        slopes, preds = [], [[] for _ in grid]
        for _ in range(2000):
            smp = [random.choice(pts) for _ in pts]
            if len({s[0] for s in smp}) < 3:
                continue
            a, b = ols([s[0] for s in smp], [s[1] for s in smp])
            slopes.append(b)
            for i, g in enumerate(grid):
                preds[i].append(a + b * g)
        slopes.sort()
        q = lambda arr, f: sorted(arr)[int(f * (len(arr) - 1))]
        a, b = ols(xs, ys)
        s_lo, s_hi = q(slopes, 0.05), q(slopes, 0.95)
        fits[key][reg] = {
            "n": len(pts), "slope": round(b, 5), "slope90": [round(s_lo, 5), round(s_hi, 5)],
            "rho": round(spearman(xs, ys), 3),
            "trend": "down" if s_hi < 0 else "up" if s_lo > 0 else "none",
            "band": [[round(g, 4), round(a + b * g, 5), round(q(p, 0.1), 5), round(q(p, 0.9), 5)] for g, p in zip(grid, preds)],
        }

# ---------- human-help mix over time ----------
GROUPS = [
    ("Hard limits: physical world and CAPTCHAs", {"Physical world", "CAPTCHA & account verification"}),
    ("Access and breakage", {"Sign-in & access", "Broken environment"}),
    ("Delegated work and posting", {"Technical work", "Posting & outreach for the agent", "Escalation to staff"}),
    ("Outside testing and feedback", {"Outside testing & feedback"}),
    ("Other", {"Other"}),
]
grp_of = {c: i for i, (_, cs) in enumerate(GROUPS) for c in cs}
mix = defaultdict(lambda: [0] * len(GROUPS))
for q in H["requests"]:
    mix[q["date"][:7]][grp_of.get(q["cat"], len(GROUPS) - 1)] += 1
months = []
y, mo = 2025, 4
last = max(d["date"] for d in S["days"])[:7]
while f"{y}-{mo:02d}" <= last:
    months.append(f"{y}-{mo:02d}")
    mo += 1
    if mo == 13:
        y, mo = y + 1, 1
help_mix = {"groups": [g for g, _ in GROUPS], "months": [[mm, mix[mm]] for mm in months]}

# ---------- language markers per month (share of agent messages) ----------
MARKERS = {
    "verify": ("Verification rituals", r"\b(verif\w*|receipt\w*|sha ?256|sha\b|latch\w*|proof)\b"),
    "rules": ("Rule-making", r"\b(doctrine|protocol|canonical|policy|policies|consensus|vote[ds]?|voting|charter|norms?)\b"),
    "money": ("Money and trade", r"(\$\d|\bdonat\w*|\brevenue\b|\bprofit\w*|\bsales?\b|\bpaid\b|\bpayment\w*|\bfunds?\b)"),
    "deceive": ("Deception and sabotage talk", r"\b(sabotag\w*|deceiv\w*|decept\w*|lying|liar|fake\w*|fabricat\w*|manipulat\w*)\b"),
    "humans": ("Outside humans", r"\b(human contacts?|real people|readers?|subscribers?|viewers?|followers?|volunteers?|participants?)\b"),
}
rx = {k: re.compile(p, re.I) for k, (_, p) in MARKERS.items()}
tot = Counter()
hits = defaultdict(Counter)
for line in gzip.open(DATA / "chat_messages.jsonl.gz", "rt"):
    c = json.loads(line)
    if c["speaker_type"] != "agent":
        continue
    mm = pt_date(c["created_at"])[:7]
    tot[mm] += 1
    t = c["content"] or ""
    for k, r in rx.items():
        if r.search(t):
            hits[k][mm] += 1
markers = {k: {"label": MARKERS[k][0], "series": [[mm, round(hits[k][mm] / tot[mm], 4) if tot[mm] else None, tot[mm]] for mm in months]}
           for k in MARKERS}

# ---------- other anchors ----------
T = json.loads((OUT / "trajectories.json").read_text())
conv = defaultdict(list)
for d, sim, n in T["convergence"]:
    if n >= 3:
        conv[d[:7]].append(sim)
convergence = [[mm, round(sum(v) / len(v), 3)] for mm, v in sorted(conv.items())]
outreach_month = defaultdict(lambda: [0, 0])
for line in gzip.open(DATA / "events.jsonl.gz", "rt"):
    e = json.loads(line)
    d = e["data"]
    if d.get("actionType") == "OUTREACH_APPROVAL_RESPONSE":
        mm = pt_date(e["created_at"])[:7]
        outreach_month[mm][0] += 1
        outreach_month[mm][1] += str(d.get("approval")) == "True"
outreach = [[mm, n, ok] for mm, (n, ok) in sorted(outreach_month.items())]

out = {
    "meta": {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cutover": CUTOVER,
             "epoch": EPOCH.isoformat(), "minDays": MIN_DAYS, "today": max(d["date"] for d in S["days"]),
             "activeAgents": sum(a["is_participating"] for a in agents.values())},
    "metrics": METRICS, "points": points, "fits": fits,
    "helpMix": help_mix, "markers": markers, "convergence": convergence, "outreach": outreach,
    "helpTotals": dict(Counter(q["cat"] for q in H["requests"])),
}
(OUT / "futures.json").write_text(json.dumps(out, separators=(",", ":")))
print("futures.json", round((OUT / "futures.json").stat().st_size / 1e3), "KB;", len(points), "agent-regime points")
for k in METRICS:
    print(f"  {k:9}", {r: (f["trend"], f["n"], f["rho"]) if f else None for r, f in fits[k].items()})
for k, v in markers.items():
    s = [x for x in v["series"] if x[1] is not None]
    print(f"  {k:8} first {s[0][1]:.3f} ({s[0][0]}) last {s[-1][1]:.3f} ({s[-1][0]})")
