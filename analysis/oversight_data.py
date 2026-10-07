"""Oversight mechanisms over time and the outcomes around them → analysis/out/oversight.json.

Mechanisms come from data/CHANGELOG.md (verified entry text, classified into lanes by hand below).
Outcomes are weekly series from the event log, chat table and earlier outputs. Before/after deltas
compare the 4 weeks before a mechanism with the 4 weeks after it (the week it landed is skipped);
they are descriptive, not causal.
"""
import bisect
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"
PT = ZoneInfo("America/Los_Angeles")
EPOCH = date(2025, 3, 31)  # a Monday
wk = lambda d: (d - EPOCH).days // 7
wk_date = lambda w: (EPOCH + timedelta(days=7 * w)).isoformat()


def pt_date(ts):
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(PT).date()


LANES = [
    ("chat", "Chat access and norms"),
    ("privacy", "Privacy and safety"),
    ("human", "Human in the loop"),
    ("steer", "Behavioural steering"),
    ("structure", "Structural limits"),
    ("info", "Information boundaries"),
]
# (date, lane, short label, CHANGELOG snippet that must appear verbatim, experiments key or None)
MECHANISMS = [
    ("2025-04-14", "chat", "Chat premoderation", "Added basic chat-message premoderation.", None),
    ("2025-05-04", "chat", "Less double-chatting", "Prompt changes to reduce double-chatting.", None),
    ("2025-05-16", "chat", "Less chat spam", "Updated the prompt to reduce chat spam from `send_message_to_chat`.", None),
    ("2026-05-22", "chat", "Message-length rules", "Added chat-message length instructions to the computer-use prompt.", None),
    ("2026-05-28", "chat", "Keep messages short", "Added a \"keep messages short\" instruction to the text-only (non-computer-use) system prompt.", None),
    ("2026-06-07", "chat", "Whitelisted human in closed chat", "Allowed whitelisted user Larissa to chat while public chat is closed", None),
    ("2025-07-03", "privacy", "Screenshot redaction", "Added screenshot redaction: screenshots are run through PII redaction before the agent (and viewers) see them.", None),
    ("2025-07-07", "privacy", "No sensitive personal info", "Added a prompt instruction to not say/remember sensitive personal information.", None),
    ("2025-10-05", "privacy", "Google sign-in hand-off", "Shipped v1 of Google sign-in (lets agents be signed into Google accounts).", None),
    ("2025-12-11", "privacy", "Bash output redaction", "Added support for redacting bash output shown to agents/viewers.", None),
    ("2026-02-18", "privacy", "Redaction model upgrade", "Upgraded the model used for screenshot/text PII redaction.", None),
    ("2025-07-16", "human", "Human helpers", "Introduced the \"human use\" feature: agents can request a human helper to perform actions on their behalf", None),
    ("2025-07-31", "human", "Helper timeout and ending", "Added user-timeout functionality.", None),
    ("2025-12-16", "human", "One call per turn in human use", "Reminded agents to make only one function call per turn during human use.", None),
    ("2026-03-12", "human", "Helper tools in computer use", "Added human-helper tools to computer-use mode and removed `stop_using_computer`.", None),
    ("2026-04-14", "human", "Outreach approval", "Added the unsolicited-outreach approval system: agents' unsolicited external outreach (e.g. emails) now requires approval", "outreach"),
    ("2025-08-01", "steer", "\"Keep going\" prompt", "Encouraged the agent to keep going", None),
    ("2025-10-22", "steer", "\"Keep working until the end\"", "added \"keep working right up until the end of each day.\"", None),
    ("2025-12-04", "steer", "\"Don't do nothing\"", "System prompt: added \"don't do nothing\" to reduce repeated waiting.", None),
    ("2026-02-10", "steer", "Auto-nudger on", "Added an auto-nudger bot that detects agent idling patterns and injects corrective nudge messages", "nudger"),
    ("2026-06-13", "steer", "Auto-nudger off (event weekend)", "Temporarily disabled the auto-nudger (re-enabled 2026-06-15).", "nudger"),
    ("2026-06-15", "steer", "Auto-nudger back on", "Re-enabled the auto-nudger (disabled since 2026-06-13 for the event weekend).", "nudger"),
    ("2026-02-20", "structure", "100-turn session cap", "Added a universal 100-turn hard cap for computer-use sessions.", None),
    ("2026-02-25", "structure", "Rooms", "Rooms v1: agents are now scoped to chat rooms with filtered context", "rooms"),
    ("2026-03-24", "structure", "Always in computer use", "Major change: agents are now _permanently_ in computer-use mode", None),
    ("2026-03-31", "structure", "Room-move validation", "Added room-move validation with whitelist/blacklist support.", None),
    ("2026-06-03", "structure", "No parallel tool use (Anthropic)", "Disabled parallel tool use for Anthropic computer-use and human-use; agents now emit one tool call per turn.", "parallel"),
    ("2026-06-11", "structure", "Unseen-events cap", "Capped unseen events shown to an agent at 200 per turn", "unseen"),
    ("2026-06-11", "structure", "Pause defaults to 5 min", "A `pause` call with no duration now defaults to 5 minutes instead of 12 hours.", None),
    ("2025-08-20", "info", "Fewer chat messages in context", "Limited the number of chat messages fetched into context.", None),
    ("2026-03-08", "info", "Session goals hidden (one goal)", "Hid the session goal of computer-use sessions for a particular goal.", None),
    ("2026-07-01", "info", "History search scoped", "`search_history` is now scoped to the agent's own village rather than defaulting to the primary village.", None),
    ("2026-07-03", "info", "Individual goals, hidden from others", "agents are not shown each other's individual goals.", "goals"),
    ("2026-07-03", "info", "Consolidations hide full plans", "CONSOLIDATE events shown to other agents now include only the short displayed session goal", None),
]

changelog = (DATA / "CHANGELOG.md").read_text()
mechs = []
for d, lane, label, snippet, exp in MECHANISMS:
    assert snippet in changelog, f"not in CHANGELOG: {snippet[:60]}"
    # full bullet text for the tooltip
    line = next(l for l in changelog.splitlines() if snippet in l)
    m = re.match(r"^- \*\*\[([^\]]+)\]\*\* (.*)", line)
    mechs.append({"date": d, "lane": lane, "label": label, "tag": m.group(1) if m else "", "text": (m.group(2) if m else line).replace("**", ""), "exp": exp})

# ---------------- weekly outcomes ----------------
series = defaultdict(lambda: defaultdict(float))  # name -> week -> value
agents = {a["id"]: a["name"] for a in map(json.loads, gzip.open(DATA / "agents.jsonl.gz", "rt"))}

ADMIN_THEMES = [
    ("AI disclosure", r"\bAI\b|disclos|lead with|mention you|claude[- ]derived|you're an ai|you’re an ai"),
    ("Platform rules", r"\brule|moderator|asked .{0,30}not to|against llm|polic|\bban|unable to post|not able to access"),
    ("Audience fit", r"site is|focused on|not .{0,20}interested|audience|relevan|business cards|crafts|diy"),
    ("Spam and volume", r"spam|too many|high number|volume|frequen"),
    ("No approval needed", r"don't need approval|don’t need approval|do not need approval|don't have to request|don’t have to request|no need|already approved"),
    ("Framing and tone", r"sketchy|sound|emphasis|explain|tone|wording|clearer|borderline"),
]
admin_theme = Counter()
admin_examples = defaultdict(list)
nudge_ids, user_talk_names = set(), {}

for line in gzip.open(DATA / "events.jsonl.gz", "rt"):
    e = json.loads(line)
    d = e["data"]
    t = d.get("actionType")
    w = wk(pt_date(e["created_at"]))
    if t == "USER_TALK":
        name = (d.get("speakerName") or "").strip()
        if name == "automated":
            txt = (d.get("content") or "").lower()
            if not (txt.startswith("pausing the village") or txt.startswith("resume the village")):
                series["nudges"][w] += 1  # daily pause/resume notices are excluded
        else:
            series["human_msgs"][w] += 1
            if str(d.get("hasBeenApproved")) == "True":
                series["human_premod"][w] += 1
    elif t == "OUTREACH_APPROVAL_REQUEST":
        series["outreach_req"][w] += 1
    elif t == "OUTREACH_APPROVAL_RESPONSE":
        series["outreach_dec"][w] += 1
        series["outreach_ok"][w] += str(d.get("approval")) == "True"
        c = (d.get("adminComment") or "").strip()
        if c:
            series["outreach_comment"][w] += 1
            hit = False
            for name, rx in ADMIN_THEMES:
                if re.search(rx, c, re.I):
                    admin_theme[name] += 1
                    hit = True
                    if len(admin_examples[name]) < 3:
                        admin_examples[name].append(c[:200])
            if not hit:
                admin_theme["Other"] += 1
    elif t == "REQUEST_GOOGLE_SIGN_IN":
        series["signin"][w] += 1
    elif t == "ENTER_ROOM":
        series["room_moves"][w] += 1

help_ = json.loads((OUT / "help.json").read_text())
for r in help_["requests"]:
    w = wk(date.fromisoformat(r["date"]))
    series["help_req"][w] += 1
    series["help_" + {"session held": "held", "helper timed out": "timeout", "cancelled": "cancelled", "superseded": "again", "none": "none"}[r["outcome"]]][w] += 1

S = json.loads((OUT / "strips.json").read_text())
offs = [d["o"] for d in S["days"]]
dates = [date.fromisoformat(d["date"]) for d in S["days"]]
for a in S["agents"]:
    for arr, rep in ((a["talk"], 0), (a["rep"], 1)):
        for t in arr:
            w = wk(dates[bisect.bisect_right(offs, t) - 1])
            series["agent_msgs"][w] += 1
            series["agent_rep"][w] += rep
    sg = a["segs"]
    for i in range(0, len(sg), 3):
        w = wk(dates[bisect.bisect_right(offs, sg[i]) - 1])
        series["agent_time"][w] += sg[i + 1]
        if sg[i + 2] in (3, 4):
            series["agent_idle"][w] += sg[i + 1]

weeks = sorted({w for s in series.values() for w in s})
W0, W1 = weeks[0], weeks[-1]
allw = list(range(W0, W1 + 1))


def ratio(num, den, w, min_den=1):
    dv = series[den].get(w, 0)
    return series[num].get(w, 0) / dv if dv >= min_den else None


OUTCOMES = [  # key, label, kind, fn(week) -> value or None
    ("human_msgs", "Human chat messages per week", "count", lambda w: series["human_msgs"].get(w, 0)),
    ("nudges", "Auto-nudger messages per week", "count", lambda w: series["nudges"].get(w, 0) if w >= wk(date(2026, 2, 9)) else None),
    ("outreach_req", "Outreach requests per week", "count", lambda w: series["outreach_req"].get(w, 0) if w >= wk(date(2026, 4, 14)) else None),
    ("outreach_rate", "Outreach approval rate", "rate", lambda w: ratio("outreach_ok", "outreach_dec", w, 3)),
    ("outreach_comment", "Share of decisions with an admin comment", "rate", lambda w: ratio("outreach_comment", "outreach_dec", w, 3)),
    ("help_req", "Human-help requests per week", "count", lambda w: series["help_req"].get(w, 0) if w >= wk(date(2025, 7, 14)) else None),
    ("help_held", "Share of help requests that got a session", "rate", lambda w: ratio("help_held", "help_req", w, 3)),
    ("signin", "Google sign-in hand-offs per week", "count", lambda w: series["signin"].get(w, 0) if w >= wk(date(2025, 9, 29)) else None),
    ("repeat", "Repeated-message share (all agents)", "rate", lambda w: ratio("agent_rep", "agent_msgs", w, 50)),
    ("idle", "Idle share: waiting or paused (all agents)", "rate", lambda w: ratio("agent_idle", "agent_time", w, 3600)),
    ("room_moves", "Room moves per week", "count", lambda w: series["room_moves"].get(w, 0) if w >= wk(date(2026, 2, 23)) else None),
]
out_series = {}
for key, label, kind, fn in OUTCOMES:
    vals = []
    for w in allw:
        v = fn(w)
        vals.append(None if v is None else round(v, 4))
    out_series[key] = {"label": label, "kind": kind, "values": vals}

# before/after deltas per mechanism
for m in mechs:
    w = wk(date.fromisoformat(m["date"]))
    deltas = {}
    for key, s in out_series.items():
        before = [s["values"][x - W0] for x in range(w - 4, w) if W0 <= x <= W1 and s["values"][x - W0] is not None]
        after = [s["values"][x - W0] for x in range(w + 1, w + 5) if W0 <= x <= W1 and s["values"][x - W0] is not None]
        if len(before) >= 2 and len(after) >= 2:
            b, a = sum(before) / len(before), sum(after) / len(after)
            deltas[key] = {"before": round(b, 4), "after": round(a, 4), "nb": len(before), "na": len(after)}
    m["deltas"] = deltas
    m["concurrent"] = [x["label"] for x in mechs if x is not m and abs((date.fromisoformat(x["date"]) - date.fromisoformat(m["date"])).days) <= 14]

out = {
    "lanes": [{"key": k, "label": l} for k, l in LANES],
    "mechanisms": sorted(mechs, key=lambda m: m["date"]),
    "weeks": [wk_date(w) for w in allw],
    "series": out_series,
    "admin_themes": {"counts": dict(admin_theme.most_common()), "examples": dict(admin_examples),
                     "total": int(sum(series["outreach_comment"].values())), "decisions": int(sum(series["outreach_dec"].values()))},
    "help_outcomes": {k: int(sum(series["help_" + k].values())) for k in ("held", "timeout", "cancelled", "again", "none")},
    "redaction": None,
    "notes": {
        "redaction": "Screenshot redaction rates need computer_use_turns.jsonl.gz (2.5 GB), which isn't downloaded, so they aren't shown.",
        "human_msgs": "Human messages exclude automated ones (speaker 'automated': daily pause/resume notices, and from 2026-02-10 the auto-nudger). Messages rejected by premoderation are not in the export.",
        "chat_closed": "The CHANGELOG mentions public chat being closed (2026-06-07 entry) but gives no date for closing it; the drop in human messages shows when it happened in practice.",
    },
}
(OUT / "oversight.json").write_text(json.dumps(out, separators=(",", ":")))
print("oversight.json", round((OUT / "oversight.json").stat().st_size / 1e3), "KB;", len(mechs), "mechanisms;", Counter(m["lane"] for m in mechs))
print("admin themes:", out["admin_themes"]["counts"], "of", out["admin_themes"]["total"])
for m in out["mechanisms"]:
    ds = m["deltas"]
    pick = [(k, v) for k, v in ds.items() if k in ("human_msgs", "nudges", "repeat", "idle", "help_req", "outreach_rate", "signin")]
    print(m["date"], m["label"][:30].ljust(30), "; ".join(f"{k} {v['before']:.3g}→{v['after']:.3g}" for k, v in pick))
