"""Build data for the activity-strip (#1) and transition-matrix (#2) views.

Reads data/*.jsonl.gz, writes analysis/out/strips.json and analysis/out/transitions.json.

Time axis: "village time". The village only runs a few hours on weekdays, so each
Pacific-time date with activity is mapped to its own window [first event, last event]
and the windows are laid end to end with a fixed gap between days.
"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "analysis" / "out"
OUT.mkdir(parents=True, exist_ok=True)
PT = ZoneInfo("America/Los_Angeles")
REGIME_CUTOVER = datetime(2026, 3, 24, tzinfo=timezone.utc).timestamp()
DAY_GAP = 15 * 60  # village-seconds of blank space between days
MAX_SEGMENT = 90 * 60  # longer silences within a day are drawn as "offline"

# Base states drawn as bands.
OFFLINE, CHAT, COMPUTER, WAITING, PAUSED, HELP = range(6)
STATE_NAMES = ["offline", "chat mode", "computer", "waiting", "paused", "awaiting human"]

# Event categories for the transition matrices.
CATS = ["talk", "talk (repeat)", "start computer", "stop computer", "wait", "pause",
        "consolidate", "search history", "human help", "outreach", "move room"]
CAT_OF = {
    "START_USING_COMPUTER": "start computer", "STOP_USING_COMPUTER": "stop computer",
    "WAIT": "wait", "PAUSE": "pause", "CONSOLIDATE": "consolidate",
    "SEARCH_HISTORY": "search history", "REQUEST_HUMAN_HELPER": "human help",
    "CANCEL_REQUEST_FOR_HUMAN_HELPER": "human help", "STOP_HUMAN_USE_SESSION": "human help",
    "REQUEST_GOOGLE_SIGN_IN": "human help", "RESTARTING_AFTER_GOOGLE_SIGN_IN": "human help",
    "OUTREACH_APPROVAL_REQUEST": "outreach", "ENTER_ROOM": "move room",
}


def rows(name):
    with gzip.open(DATA / name, "rt") as f:
        for line in f:
            yield json.loads(line)


def ts(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def pt_date(t):
    return datetime.fromtimestamp(t, PT).date().isoformat()


TOKEN = re.compile(r"[a-z0-9]+")


def shingles(text):
    toks = TOKEN.findall(text.lower())
    return set(zip(toks, toks[1:])) or set(toks)


def is_repeat(a, b):
    """Near-duplicate of the agent's previous message (bigram Jaccard >= 0.7)."""
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.7


agents = sorted(rows("agents.jsonl.gz"), key=lambda a: a["created_at"])
agent_idx = {a["id"]: i for i, a in enumerate(agents)}

print("reading events…", file=sys.stderr)
events = []
for e in rows("events.jsonl.gz"):
    d = e["data"]
    t = d.get("actionType")
    aid = d.get("speakerId") if t == "AGENT_TALK" else d.get("agentId")
    if aid not in agent_idx:
        continue
    extra = None
    if t == "AGENT_TALK":
        extra = d.get("content") or ""
    elif t == "PAUSE":
        extra = float(d.get("seconds") or 0)
    events.append((e["event_index"], ts(e["created_at"]), t, agent_idx[aid], extra))
events.sort()
print(f"{len(events)} agent events", file=sys.stderr)

# ---- village-time axis ----
# Each day's window is the 0.5th-99.5th percentile of its event times, so a single
# stray late-night action doesn't stretch the day; outliers clamp to the edges.
day_times = defaultdict(list)
for _, t, *_ in events:
    day_times[pt_date(t)].append(t)
day_win = {}
for d, tl in day_times.items():
    tl.sort()
    n = len(tl)
    day_win[d] = (tl[int(0.005 * n)], tl[min(n - 1, int(0.995 * n))])
days = sorted(day_win)
offset, cursor = {}, 0.0
for d in days:
    offset[d] = cursor
    lo, hi = day_win[d]
    cursor += (hi - lo) + DAY_GAP
TOTAL = cursor


def vt(t):
    d = pt_date(t)
    lo, hi = day_win.get(d, (t, t))
    return offset[d] + min(max(t - lo, 0), hi - lo) if d in offset else None


def day_end_vt(t):
    d = pt_date(t)
    return offset[d] + (day_win[d][1] - day_win[d][0])


# ---- per-agent segments, ticks, transitions ----
by_agent = defaultdict(list)
for ev in events:
    by_agent[ev[3]].append(ev)

strips = []
trans = {}  # agent -> regime -> Counter((from, to))
cat_counts = {}
runs = {}
for ai, evs in by_agent.items():
    segs = []  # [start, dur, state]
    talk, talk_rep, consol, search, help_, outreach = [], [], [], [], [], []
    in_session = False
    prev_sh = None
    tr = {"pre": Counter(), "post": Counter()}
    cc = {"pre": Counter(), "post": Counter()}
    prev_cat, prev_day = None, None
    run_len, max_run = Counter(), Counter()
    for i, (_, t, typ, _, extra) in enumerate(evs):
        post = t >= REGIME_CUTOVER
        regime = "post" if post else "pre"
        v = vt(t)
        cat = CAT_OF.get(typ)
        # ticks + repeat detection
        if typ == "AGENT_TALK":
            sh = shingles(extra)
            rep = is_repeat(sh, prev_sh)
            prev_sh = sh
            (talk_rep if rep else talk).append(round(v))
            cat = "talk (repeat)" if rep else "talk"
        elif typ == "CONSOLIDATE":
            consol.append(round(v))
        elif typ == "SEARCH_HISTORY":
            search.append(round(v))
        elif typ in ("REQUEST_HUMAN_HELPER", "REQUEST_GOOGLE_SIGN_IN"):
            help_.append(round(v))
        elif typ == "OUTREACH_APPROVAL_REQUEST":
            outreach.append(round(v))
        # transitions (sequences break at day boundaries)
        if cat:
            day = pt_date(t)
            cc[regime][cat] += 1
            if prev_cat and prev_day == day:
                tr[regime][(prev_cat, cat)] += 1
                run_len[cat] = run_len[cat] + 1 if prev_cat == cat else 1
            else:
                run_len[cat] = 1
            max_run[cat] = max(max_run[cat], run_len[cat])
            prev_cat, prev_day = cat, day
        # base state
        if typ == "START_USING_COMPUTER":
            in_session = True
        elif typ == "STOP_USING_COMPUTER":
            in_session = False
        default = COMPUTER if (post or in_session) else CHAT
        if typ == "WAIT":
            state = WAITING
        elif typ == "PAUSE":
            state = PAUSED
        elif typ in ("REQUEST_HUMAN_HELPER", "REQUEST_GOOGLE_SIGN_IN"):
            state = HELP
        else:
            state = default
        # segment runs until the agent's next event, capped by day end and MAX_SEGMENT
        end = day_end_vt(t)
        if i + 1 < len(evs) and pt_date(evs[i + 1][1]) == pt_date(t):
            end = vt(evs[i + 1][1])
        dur = end - v
        if state == PAUSED and extra:
            if extra < dur:  # pause ended before next event: back to default
                segs.append([v, extra, PAUSED])
                v, dur, state = v + extra, dur - extra, default
        if dur > MAX_SEGMENT and state not in (WAITING, PAUSED, HELP):
            segs.append([v, MAX_SEGMENT, state])
            v, dur, state = v + MAX_SEGMENT, dur - MAX_SEGMENT, OFFLINE
        if dur > 0:
            if segs and segs[-1][2] == state and abs(segs[-1][0] + segs[-1][1] - v) < 1:
                segs[-1][1] += dur
            else:
                segs.append([v, dur, state])
    flat = []
    for s, d, st in segs:
        if st != OFFLINE and d >= 1:
            flat += [round(s), max(1, round(d)), st]
    a = agents[ai]
    strips.append({
        "i": ai, "name": a["name"], "model": a["model_string"],
        "first": pt_date(evs[0][1]), "last": pt_date(evs[-1][1]), "n": len(evs),
        "segs": flat, "talk": talk, "rep": talk_rep, "consol": consol,
        "search": search, "help": help_, "outreach": outreach,
    })
    trans[ai] = {r: [[CATS.index(a_), CATS.index(b_), n] for (a_, b_), n in c.items()]
                 for r, c in tr.items()}
    cat_counts[ai] = {r: {CATS.index(k): n for k, n in c.items()} for r, c in cc.items()}
    runs[ai] = {CATS.index(k): n for k, n in max_run.items()}

strips.sort(key=lambda s: s["first"])

# ---- goals, changelog, day numbers ----
goals = []
for g in sorted(rows("village_goals.jsonl.gz"), key=lambda g: g["start_time"] or ""):
    s = ts(g["start_time"]) if g["start_time"] else None
    e = ts(g["end_time"]) if g["end_time"] else None
    goals.append({"goal": g["goal"].strip(), "start": pt_date(s) if s else None,
                  "end": pt_date(e) if e else None})

changelog = []
date = None
for line in (DATA / "CHANGELOG.md").read_text().splitlines():
    m = re.match(r"^## (\d{4}-\d{2}-\d{2})(.*)", line)
    if m:
        date, title = m.group(1), m.group(2).strip(" —-")
        if title:
            changelog.append({"date": date, "text": title, "major": True})
        continue
    m = re.match(r"^- \*\*\[([^\]]+)\]\*\* (.*)", line)
    if m and date:
        changelog.append({"date": date, "tag": m.group(1), "text": m.group(2), "major": False})

day_numbers = {}
tpath = DATA / "village-transcript.json"
if tpath.exists():
    print("reading transcript for day numbers…", file=sys.stderr)
    tr_json = json.loads(tpath.read_text())
    for d in tr_json["days"]:
        for ev in d["events"][:1]:
            day_numbers[pt_date(datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00")).timestamp())] = d["day"]

day_list = [{"date": d, "o": round(offset[d]), "len": round(day_win[d][1] - day_win[d][0]),
             "t0": round(day_win[d][0]), "day": day_numbers.get(d)} for d in days]

strips_out = {
    "meta": {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "total": round(TOTAL), "dayGap": DAY_GAP, "maxSegment": MAX_SEGMENT,
             "cutover": "2026-03-24", "states": STATE_NAMES},
    "days": day_list, "goals": goals, "changelog": changelog, "agents": strips,
}
(OUT / "strips.json").write_text(json.dumps(strips_out, separators=(",", ":")))

trans_out = {
    "cats": CATS,
    "agents": [{"i": s["i"], "name": s["name"], "model": s["model"], "first": s["first"]} for s in strips],
    "trans": trans, "counts": cat_counts, "maxRun": runs,
}
(OUT / "transitions.json").write_text(json.dumps(trans_out, separators=(",", ":")))

for f in ("strips.json", "transitions.json"):
    print(f, round((OUT / f).stat().st_size / 1e6, 2), "MB", file=sys.stderr)
print("days", len(days), "total village hours", round(TOTAL / 3600), file=sys.stderr)
rep_share = sorted(((len(s["rep"]) / max(1, len(s["rep"]) + len(s["talk"])), s["name"]) for s in strips), reverse=True)
print("repeat-talk share, top 10:", [(n, f"{r:.0%}") for r, n in rep_share[:10]], file=sys.stderr)
