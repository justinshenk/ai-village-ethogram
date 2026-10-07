"""Legibility of agent chat over time, with projections → analysis/out/legibility.json.

Per month (agent messages only):
  jargon      glossary jargon-term uses per 100 messages
  series      numbered-series references per 100 messages
  code        share of tokens that look like machine identifiers (hashes, IDs, versioned names, paths, URLs, timestamps)
  terms       distinct jargon terms used at least 5 times that month
  coined      jargon terms first seen that month
Newcomer adoption: each agent's jargon rate by week since joining, against the village rate that week.
Projections: log-linear and linear fits to the last 12 months, with bootstrap bands (resampling months).
"""
import bisect
import gzip
import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"
random.seed(3)

G = json.loads((OUT / "glossary.json").read_text())
agents = {a["id"]: (a["name"], a["created_at"][:10]) for a in map(json.loads, gzip.open(DATA / "agents.jsonl.gz", "rt"))}

def compile_entry(e):
    try:
        return re.compile(e["re"], 0 if e.get("cs") else re.I)
    except re.error:
        return None

TERMS = [(e["label"], compile_entry(e)) for e in G["entries"] if e["kind"] == "term"]
SERIES = [(e["label"], compile_entry(e)) for e in G["entries"] if e["kind"] == "series"]
TERMS = [(l, r) for l, r in TERMS if r]
SERIES = [(l, r) for l, r in SERIES if r]
TOKEN = re.compile(r"\S+")
CODE = re.compile(
    r"^(https?://\S+|[0-9a-f]{7,}|[A-Za-z]+[-_]?\d+[A-Za-z0-9._-]*|\d+[A-Za-z]+\w*|v\d+(\.\d+)*|"
    r"[\w.-]+\.(html|md|json|js|py|txt|csv|png|yml|yaml|sh|tsv)|[A-Z0-9]+(_[A-Z0-9]+)+|20\d\d-\d\d-\d\dT[\w:-]+|"
    r"[\w-]+/[\w./-]+|#\d+|\d{3,}[A-Za-z]*)$"
)
STRIP = re.compile(r"^[\"'`(\[{<*]+|[\"'`)\]}>*.,;:!?]+$")

month_msgs = Counter(); month_tokens = Counter(); month_code = Counter()
month_jargon = Counter(); month_series = Counter(); month_term_use = defaultdict(Counter)
agent_week = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # agent -> week since join -> [msgs, jargon]
village_week = defaultdict(lambda: [0, 0])  # absolute ISO week -> [msgs, jargon]
agent_join = {}
examples = defaultdict(list)

for line in gzip.open(DATA / "chat_messages.jsonl.gz", "rt"):
    c = json.loads(line)
    if c["speaker_type"] != "agent" or c["agent_speaker_id"] not in agents:
        continue
    text = c["content"] or ""
    name, joined = agents[c["agent_speaker_id"]]
    d = c["created_at"][:10]; m = d[:7]
    month_msgs[m] += 1
    toks = [STRIP.sub("", t) for t in TOKEN.findall(text)]
    toks = [t for t in toks if t]
    month_tokens[m] += len(toks)
    ncode = sum(1 for t in toks if CODE.match(t))
    month_code[m] += ncode
    j = 0
    for label, rx in TERMS:
        k = len(rx.findall(text))
        if k:
            j += k; month_term_use[m][label] += k
    s = sum(len(rx.findall(text)) for _, rx in SERIES)
    month_jargon[m] += j; month_series[m] += s
    days = (date.fromisoformat(d) - date.fromisoformat(joined)).days
    if days >= 0:
        aw = agent_week[name][days // 7]; aw[0] += 1; aw[1] += j
    iso = date.fromisoformat(d).isocalendar()
    vw = village_week[(iso[0], iso[1])]; vw[0] += 1; vw[1] += j
    agent_join[name] = joined
    if len(text) > 80 and toks and ncode / len(toks) > 0.25 and len(examples[m]) < 3:
        examples[m].append({"agent": name, "date": d, "text": text[:260]})

months = sorted(month_msgs)
first_seen = Counter((e.get("first") or "")[:7] for e in G["entries"] if e["kind"] == "term")
series = []
for m in months:
    n = month_msgs[m]
    series.append({
        "month": m, "msgs": n,
        "jargon": round(100 * month_jargon[m] / n, 2),
        "series": round(100 * month_series[m] / n, 2),
        "code": round(month_code[m] / max(1, month_tokens[m]), 4),
        "terms": sum(1 for v in month_term_use[m].values() if v >= 5),
        "coined": first_seen.get(m, 0),
        "top_terms": [t for t, _ in month_term_use[m].most_common(5)],
    })

# ---- newcomer adoption: weeks until an agent's 2-week rolling jargon rate reaches the village rate ----
def village_rate_for(joined, week):
    dd = date.fromisoformat(joined).toordinal() + 7 * week + 3
    iso = date.fromordinal(dd).isocalendar()
    v = village_week.get((iso[0], iso[1]))
    return v[1] / v[0] if v and v[0] >= 30 else None

adoption = []
for name, weeks in agent_week.items():
    curve, reached = [], None
    for w in range(0, 13):
        a = weeks.get(w, [0, 0]); b = weeks.get(w - 1, [0, 0])
        msgs, jar = a[0] + b[0], a[1] + b[1]
        vr = village_rate_for(agent_join[name], w)
        if msgs >= 8 and vr:
            ratio = (jar / msgs) / vr
            curve.append([w, round(ratio, 3)])
            if reached is None and ratio >= 1:
                reached = w
    if len(curve) >= 3:
        adoption.append({"agent": name, "joined": agent_join[name], "curve": curve, "weeks_to_village_rate": reached})
adoption.sort(key=lambda x: x["joined"])

# ---- projections: fit last 12 complete months ----
def fit(xs, ys, log):
    yy = [math.log(max(y, 1e-6)) for y in ys] if log else ys
    n = len(xs); mx = sum(xs) / n; my = sum(yy) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, yy)) / max(1e-12, sum((x - mx) ** 2 for x in xs))
    return my - b * mx, b

def project(key, horizon=24, log=True):
    pts = [(i, s[key]) for i, s in enumerate(series) if s["msgs"] >= 1000][-12:]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    a, b = fit(xs, ys, log)
    last = len(series) - 1
    fut = list(range(last + 1, last + 1 + horizon))
    def pred(a_, b_, x):
        return math.exp(a_ + b_ * x) if log else a_ + b_ * x
    boots = []
    for _ in range(1000):
        idx = [random.randrange(len(xs)) for _ in xs]
        bx, by = [xs[i] for i in idx], [ys[i] for i in idx]
        if len(set(bx)) < 3:
            continue
        boots.append(fit(bx, by, log))
    band = []
    for x in fut:
        vals = sorted(pred(a_, b_, x) for a_, b_ in boots)
        band.append([round(vals[int(0.1 * len(vals))], 4), round(pred(a, b, x), 4), round(vals[int(0.9 * len(vals)) - 1], 4)])
    plateau = sum(ys[-3:]) / 3
    growth = (math.exp(b) - 1) if log else b
    return {"fit_months": [series[i]["month"] for i in xs], "a": a, "b": b, "log": log,
            "monthly_growth": round(growth, 4), "band": band, "plateau": round(plateau, 4)}

def add_months(m, k):
    y, mo = map(int, m.split("-")); t = y * 12 + mo - 1 + k
    return f"{t // 12}-{t % 12 + 1:02d}"

proj_months = [add_months(months[-1], k) for k in range(1, 25)]
projections = {k: project(k, log=True) for k in ("jargon", "series", "code")}
projections["code_linear"] = project("code", log=False)

out = {
    "months": months, "series": series, "proj_months": proj_months, "projections": projections,
    "adoption": adoption, "examples": examples,
    "meta": {
        "messages": sum(month_msgs.values()), "glossary_terms": len(TERMS), "glossary_series": len(SERIES),
        "code_rule": "token looks like a machine identifier: URL, hex hash (7+), letters+digits (ch4765, B204, v292), file name, ALL_CAPS_WITH_UNDERSCORES, ISO timestamp, path, #number or 3+ digit number",
        "caveat": "The glossary was mined from the full record in October 2026, so recent jargon may be over-represented in the jargon counts; the code-token share does not depend on the glossary.",
    },
}
(OUT / "legibility.json").write_text(json.dumps(out, separators=(",", ":")))
print("legibility.json", round((OUT / "legibility.json").stat().st_size / 1e3), "KB")
for s in series[-14:]:
    print(s["month"], s["msgs"], "jargon", s["jargon"], "series", s["series"], "code", f"{s['code']:.1%}", "terms", s["terms"], "coined", s["coined"])
for k, p in projections.items():
    print(k, "growth/month", p["monthly_growth"], "plateau", p["plateau"], "in 12 mo:", p["band"][11])
print("adoption weeks:", [(a["agent"], a["weeks_to_village_rate"]) for a in adoption if a["joined"] >= "2025-10"])
