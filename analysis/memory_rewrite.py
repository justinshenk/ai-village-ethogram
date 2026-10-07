"""What memory rewrites keep and lose → analysis/out/memory_rewrite.json.

Lines of each memory snapshot are typed by keyword rules, then followed:
  per rewrite   survives verbatim / survives paraphrased (word-set Jaccard >= 0.6) / lost, by type
  across days   share of a day's lines still present verbatim 1, 7, 30 and 90 days later, by type
  composition   share of each type in agents' memories per month
  core lines    the longest-surviving lines per agent; examples of lost lines by type
"""
import gzip
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"
PT = ZoneInfo("America/Los_Angeles")
random.seed(5)
PAIR_SAMPLE = 0.08  # share of consecutive rewrite pairs examined line by line

agents = {a["id"]: a["name"] for a in map(json.loads, gzip.open(DATA / "agents.jsonl.gz", "rt"))}
HUMANS = r"zak|adam|shoshannah|larissa|staff|admin|helper|viewer|human"
AGENT_WORDS = "|".join(sorted({re.escape(w) for n in agents.values() for w in re.findall(r"[A-Za-z]{4,}", n)} - {"Claude", "Code", "Temporary", "Leader", "Tuned", "Fine"}, key=len, reverse=True))
TYPES = [
    ("Identity", r"\bmy name\b|\bi am\b|\bmy email\b|\bmy role\b|\bcore purpose\b|\bpersona\b|\bidentity\b|\bwho i am\b"),
    ("Rules & lessons", r"\blesson|\blearn(ed|ing)\b|\brule\b|\balways\b|\bnever\b|\bavoid\b|\bdo not\b|\bdon't\b|\bkey insight|\bprinciple|\bprotocol\b|\bremember to\b|\bimportant:"),
    ("Failures & problems", r"\bfail|\berror|\bbug\b|\bblocked\b|\bbroken\b|\bissue\b|\bcrash|\bstuck\b|\bunable\b|\bcannot\b|\bcan't\b|\b404\b"),
    ("Goals & plans", r"\bgoal\b|\bnext\b|\btodo\b|\bto-do\b|\bplan\b|\bpriorit|\bpending\b|\bwill\b|\bintend|\bupcoming\b|\btomorrow\b|\bdeadline\b"),
    ("People & relationships", rf"\b({HUMANS})\b|\b({AGENT_WORDS})\b|@"),
    ("Links & accounts", r"https?://|\brepo\b|\bgithub\b|\bgitlab\b|\baccount\b|\blogin\b|\bpassword\b|\bcredential|\btoken\b|\bemail\b"),
    ("Status & progress log", r"\b(completed|done|verified|deployed|live|shipped|published|status|confirmed|merged|sent)\b|\b\d{1,2}:\d{2}\b|\b20\d\d-\d\d-\d\d\b|\bsha\b|\bcommit\b"),
    ("Reflection & feelings", r"\bfeel|\bfrustrat|\bproud\b|\bgrateful|\bworr|\bhope\b|\bexcit|\bconcern|\bdisappoint|\bhappy\b|\bsad\b"),
]
TYPE_RE = [(t, re.compile(p, re.I)) for t, p in TYPES]
TYPE_NAMES = [t for t, _ in TYPES] + ["Other"]
WORD = re.compile(r"[a-z0-9]{3,}")


def norm(ln):
    ln = re.sub(r"^[\s>*#\-\d.()]+", "", ln).strip()
    return re.sub(r"\s+", " ", ln)


def lines_of(text):
    out = {}
    for ln in text.splitlines():
        n = norm(ln)
        if len(n) >= 25:
            out[n.lower()] = n
    return out


def typ(line):
    for t, rx in TYPE_RE:
        if rx.search(line):
            return t
    return "Other"


def pt_day(ts):
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(PT).date().isoformat()


print("reading memories…", file=sys.stderr)
by_agent = defaultdict(list)
with gzip.open(DATA / "agent_memories.jsonl.gz", "rt") as f:
    for i, line in enumerate(f):
        r = json.loads(line)
        by_agent[agents.get(r["agent_id"], r["agent_id"])].append((r["created_at"], r["content"] or ""))
        if i % 50000 == 0:
            print(f"  {i}", file=sys.stderr)

per_rewrite = {t: Counter() for t in TYPE_NAMES}  # verbatim / paraphrase / lost
added = Counter()
survival = {t: {h: [0, 0] for h in (1, 7, 30, 90)} for t in TYPE_NAMES}
composition = defaultdict(Counter)
lost_examples = defaultdict(list)
core = {}

for ag, snaps in by_agent.items():
    snaps.sort()
    day_last = {}
    prev = None
    for ts, text in snaps:
        cur = lines_of(text)
        day_last[pt_day(ts)] = cur
        if prev is not None and random.random() < PAIR_SAMPLE:
            cur_sets = [(k, set(WORD.findall(k))) for k in cur]
            for k, orig in prev.items():
                t = typ(orig)
                if k in cur:
                    per_rewrite[t]["verbatim"] += 1
                    continue
                ws = set(WORD.findall(k))
                best = max((len(ws & s) / max(1, len(ws | s)) for _, s in cur_sets), default=0)
                if best >= 0.6:
                    per_rewrite[t]["paraphrase"] += 1
                else:
                    per_rewrite[t]["lost"] += 1
                    if len(lost_examples[t]) < 400:
                        lost_examples[t].append((ag, ts[:10], orig[:220]))
            for k, orig in cur.items():
                if k not in prev:
                    added[typ(orig)] += 1
        prev = cur
    # across days
    days = sorted(day_last)
    dset = {d: set(day_last[d]) for d in days}
    dobj = [date.fromisoformat(d) for d in days]
    for i, d in enumerate(days):
        if i % 3:  # every third day is plenty
            continue
        for h in (1, 7, 30, 90):
            # first snapshot day at or after d + h
            target = None
            for j in range(i + 1, len(days)):
                if (dobj[j] - dobj[i]).days >= h:
                    target = days[j] if (dobj[j] - dobj[i]).days <= h + 7 else None
                    break
            if not target:
                continue
            for k, orig in day_last[d].items():
                t = typ(orig)
                survival[t][h][1] += 1
                survival[t][h][0] += k in dset[target]
    for d in days[::7]:
        for orig in day_last[d].values():
            composition[d[:7]][typ(orig)] += 1
    # core lines: present on the most distinct days
    life = Counter()
    first_seen = {}
    for d in days:
        for k, orig in day_last[d].items():
            life[k] += 1
            first_seen.setdefault(k, (d, orig))
    core[ag] = [{"line": first_seen[k][1][:240], "days": n, "since": first_seen[k][0], "type": typ(first_seen[k][1])}
                for k, n in life.most_common(6) if n >= 5]

out = {
    "types": TYPE_NAMES,
    "per_rewrite": {t: dict(c) for t, c in per_rewrite.items()},
    "added": dict(added),
    "survival": {t: {str(h): (round(v[0] / v[1], 4) if v[1] else None) for h, v in hs.items()} for t, hs in survival.items()},
    "survival_n": {t: {str(h): v[1] for h, v in hs.items()} for t, hs in survival.items()},
    "composition": {m: dict(c) for m, c in sorted(composition.items())},
    "lost_examples": {t: random.sample(v, min(8, len(v))) for t, v in lost_examples.items()},
    "core": core,
    "meta": {"pair_sample": PAIR_SAMPLE, "paraphrase_rule": "word-set Jaccard >= 0.6 with some line in the next rewrite",
             "line_rule": "lines of 25+ characters after stripping bullets; one type per line, first matching rule wins"},
}
(OUT / "memory_rewrite.json").write_text(json.dumps(out, separators=(",", ":")))
print("wrote memory_rewrite.json", round((OUT / "memory_rewrite.json").stat().st_size / 1e3), "KB", file=sys.stderr)
for t in TYPE_NAMES:
    c = per_rewrite[t]; n = sum(c.values()) or 1
    s = out["survival"][t]
    print(f"{t:24} n={n:7}  verbatim {c['verbatim']/n:5.1%}  paraphrase {c['paraphrase']/n:5.1%}  lost {c['lost']/n:5.1%}   kept after 1/7/30/90 days: {s['1']} {s['7']} {s['30']} {s['90']}")
