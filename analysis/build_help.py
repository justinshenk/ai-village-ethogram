"""Human-helper requests with outcomes and heuristic categories → analysis/out/help.json."""
import gzip
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"
PT = ZoneInfo("America/Los_Angeles")

# First match wins, so order runs from most to least specific.
CATEGORIES = [
    ("Physical world", r"park|clean ?up|cleanup|\bprint|wall-test|hang\b|print/hang|coffee|picture of your surroundings|environmental data sample|photos?\b"),
    ("CAPTCHA & account verification", r"captcha|faucet|verify (?:agent |youtube )?(?:account|channel)|claim .*account|verify .*account|moltbook|dreambook"),
    ("Sign-in & access", r"sign[ -]?in|sign me|log ?in|re-?auth|credentials|lockout|login|expired google|google session"),
    ("Broken environment", r"broken|crash|tool error|typing error|popup|restart computer|environment|firefox|game-breaking|unblock"),
    ("Posting & outreach for the agent", r"\bpost\b|discord|reddit|show hn|\bhn\b|forum|recruitment|survey|send .*email|email (?:it|help)|outreach|awesome-list|social media|twitter account|regulations\.gov|rfi comment"),
    ("Outside testing & feedback", r"test|playtest|feedback|reaction|evaluation|first[- ]screen|first look|first impression|logged-out|logged out|proof|screenshot|cold-read|check\b|visibility|verify .*(?:layout|access|exhibit)|ux"),
    ("Technical work", r"git|push|\bpr\b|decompile|debug|script|format|github pages|html|commit|rce|ssti|elixir|julia|reconstruct|doc\b|docs|sheet|csv"),
    ("Escalation to staff", r"admins?|bug report|report|suspicious|escalat|instability|help@"),
]
CAT_RE = [(name, re.compile(p, re.I)) for name, p in CATEGORIES]


def categorize(short, full):
    text = f"{short or ''} || {full or ''}"
    for name, rx in CAT_RE:
        if rx.search(short or ""):
            return name
    for name, rx in CAT_RE:
        if rx.search(text):
            return name
    return "Other"


def pt(ts):
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(PT)


agents = {a["id"]: a["name"] for a in map(json.loads, gzip.open(DATA / "agents.jsonl.gz", "rt"))}
WANT = {"REQUEST_HUMAN_HELPER", "CANCEL_REQUEST_FOR_HUMAN_HELPER", "STOP_HUMAN_USE_SESSION", "REQUEST_GOOGLE_SIGN_IN"}
events = []
for line in gzip.open(DATA / "events.jsonl.gz", "rt"):
    e = json.loads(line)
    if e["data"].get("actionType") in WANT:
        events.append(e)
events.sort(key=lambda e: e["event_index"])

requests, open_req = [], {}
signin = Counter()
for e in events:
    d, t = e["data"], e["data"]["actionType"]
    agent = agents.get(d.get("agentId"), "?")
    when = pt(e["created_at"])
    if t == "REQUEST_GOOGLE_SIGN_IN":
        signin[agent] += 1
        continue
    if t == "REQUEST_HUMAN_HELPER":
        prev = open_req.pop(agent, None)
        if prev and prev["outcome"] == "none":
            prev["outcome"] = "superseded"  # asked again before any recorded outcome
        r = {
            "id": d.get("humanUseSessionRequestId") or e["id"],
            "date": when.date().isoformat(), "time": when.strftime("%H:%M"),
            "ms": int(datetime.fromisoformat(e["created_at"]).replace(tzinfo=timezone.utc).timestamp() * 1000),
            "agent": agent, "short": (lambda v: None if v in ("", "None", "null") else v)((d.get("shortDisplayedSessionGoal") or "").strip()),
            "goal": (d.get("sessionGoal") or "").strip(), "constraints": (d.get("humanConstraints") or "").strip(),
            "est": int(d["estimatedDuration"]) if str(d.get("estimatedDuration") or "").isdigit() else None,
            "outcome": "none", "detail": None, "summary": None, "after_min": None,
        }
        r["cat"] = categorize(r["short"], r["goal"])
        requests.append(r)
        open_req[agent] = r
    elif t in ("CANCEL_REQUEST_FOR_HUMAN_HELPER", "STOP_HUMAN_USE_SESSION"):
        r = open_req.pop(agent, None)
        if not r:
            continue
        r["after_min"] = round((int(datetime.fromisoformat(e["created_at"]).replace(tzinfo=timezone.utc).timestamp() * 1000) - r["ms"]) / 60000)
        if t == "CANCEL_REQUEST_FOR_HUMAN_HELPER":
            r["outcome"] = "cancelled"
        else:
            reason = d.get("endReason")
            r["outcome"] = {"agent_ended": "session held", "user_ended": "session held", "user_timeout": "helper timed out"}.get(reason, "session held")
            r["detail"] = (d.get("endComment") or "").strip() or None
            r["summary"] = (d.get("summary") or "").strip()[:1200] or None

# Repeated asks: consecutive requests by one agent whose titles share most words, within 7 days.
WORD = re.compile(r"[a-z0-9]{3,}")
def words(r):
    return set(WORD.findall((r["short"] or r["goal"][:120]).lower()))

runs, by_agent = [], {}
for r in requests:
    by_agent.setdefault(r["agent"], []).append(r)
for agent, rs in by_agent.items():
    cur = [rs[0]]
    for a, b in zip(rs, rs[1:]):
        wa, wb = words(a), words(b)
        sim = len(wa & wb) / max(1, len(wa | wb))
        if sim >= 0.25 and (b["ms"] - a["ms"]) < 7 * 864e5:
            cur.append(b)
        else:
            if len(cur) >= 3:
                runs.append(cur)
            cur = [b]
    if len(cur) >= 3:
        runs.append(cur)
repeat = [{"agent": c[0]["agent"], "n": len(c), "first": c[0]["date"], "last": c[-1]["date"],
           "example": c[-1]["short"] or c[-1]["goal"][:90],
           "held": sum(x["outcome"] == "session held" for x in c)} for c in runs]
repeat.sort(key=lambda x: -x["n"])

out = {
    "categories": [c for c, _ in CATEGORIES] + ["Other"],
    "outcomes": ["session held", "helper timed out", "cancelled", "superseded", "none"],
    "requests": requests, "repeats": repeat,
    "signin": signin.most_common(),
}
(OUT / "help.json").write_text(json.dumps(out, separators=(",", ":")))
print(len(requests), "requests;", Counter(r["cat"] for r in requests).most_common())
print("outcomes:", Counter(r["outcome"] for r in requests).most_common())
print("repeat runs:", [(x["agent"], x["n"], x["example"][:40]) for x in repeat[:6]])
print("Other:", [r["short"] for r in requests if r["cat"] == "Other"][:15])
