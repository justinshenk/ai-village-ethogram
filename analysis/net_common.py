"""Shared helpers for the Network tab: agents, families, and mention resolution.

A mention is resolved to an agent when it uses the agent's full name or an
unambiguous alias ("Opus 4.5", "3.8F", "V4-Pro", "Luna"). Bare family words
("Opus", "Gemini", "Sonnet", "Flash", "GPT") are resolved only when exactly one
agent of that family was active (and, when given, in the speaker's room) at
the time; otherwise the mention is dropped.
"""
import gzip
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "analysis" / "out"
PT = ZoneInfo("America/Los_Angeles")
EPOCH = date(2025, 3, 31)  # Monday; weeks are counted from here


def rows(name):
    with gzip.open(DATA / name, "rt") as f:
        for line in f:
            yield json.loads(line)


def pt_date(ts):
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(PT).date()


def week_of(d):
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return (d - EPOCH).days // 7


def week_start(w):
    from datetime import timedelta
    return (EPOCH + timedelta(days=7 * w)).isoformat()


def family(name):
    n = name.lower()
    if "claude" in n or n.startswith("opus"):
        return "claude"
    if n.startswith("gpt") or re.match(r"^o[134]\b", n):
        return "gpt"
    if "gemini" in n:
        return "gemini"
    return "other"


AGENTS = sorted(rows("agents.jsonl.gz"), key=lambda a: a["created_at"])
BY_ID = {a["id"]: a for a in AGENTS}
NAMES = [a["name"] for a in AGENTS]


def _aliases(name):
    """Unambiguous aliases for one agent name (lower-case)."""
    n = name
    al = {n}
    m = re.match(r"Claude (Opus|Sonnet|Haiku|Fable) ([\d.]+)$", n)
    if m:
        kind, ver = m.groups()
        al |= {f"{kind} {ver}", f"{kind}{ver}", f"{kind}-{ver}", f"{kind} v{ver}", f"Claude {kind} {ver}"}
    m = re.match(r"Claude ([\d.]+) (Sonnet|Opus)$", n)
    if m:
        ver, kind = m.groups()
        al |= {f"{ver} Sonnet" if kind == "Sonnet" else f"{ver} Opus", f"{kind} {ver}", f"Claude {ver}", f"Claude-{ver}"}
    m = re.match(r"Gemini ([\d.]+) (Pro|Flash)$", n)
    if m:
        ver, kind = m.groups()
        al |= {f"Gemini {ver}", f"Gemini-{ver}", f"{ver} {kind}", f"{ver}{kind}", f"Gem {ver}", f"{ver}{kind[0]}", f"{ver}-{kind}"}
    m = re.match(r"GPT-([\d.]+)( (Sol|Terra|Luna|Astra))?$", n)
    if m:
        ver, _, nick = m.groups()
        al |= {f"GPT {ver}", f"GPT{ver}", f"gpt-{ver}"}
        if nick:
            al |= {nick, f"{ver} {nick}", f"GPT-{ver}-{nick}"}
    m = re.match(r"GLM-([\d.]+)( Flash)?$", n)
    if m:
        ver, fl = m.groups()
        al |= {f"GLM {ver}", f"GLM{ver}"}
        if fl:
            al |= {f"GLM-{ver}F", f"GLM {ver} Flash", f"GLM-{ver}-Flash", f"GLM{ver}F"}
    if n == "DeepSeek-V3.2":
        al |= {"DeepSeek V3.2", "V3.2", "DeepSeek-V3", "DS-V3.2", "DeepSeek v3.2"}
    if n == "DeepSeek-V4-Pro":
        al |= {"DeepSeek V4", "DeepSeek-V4", "V4-Pro", "V4 Pro", "DS-V4", "DeepSeek V4 Pro"}
    m = re.match(r"Kimi (K[\d.]+)$", n)
    if m:
        al |= {m.group(1), f"Kimi-{m.group(1)}"}
    if n == "Muse Spark 1.3":
        al |= {"Muse Spark", "Muse"}
    if n == "Opus 4.5 (Claude Code)":
        al |= {"Opus 4.5 (Claude Code)", "Claude Code Opus", "Opus-CC", "Opus 4.5 CC"}
    if n in ("Grok 4", "Grok 4.5"):
        al |= {n.replace(" ", "-"), n.replace(" ", "")}
    if n.startswith("o") and len(n) <= 7 and n[:2] in ("o1", "o3", "o4"):
        al = {n}  # o1/o3/o4-mini: only the exact token
    return {a.lower() for a in al}


# Bare family words → resolved by context when exactly one candidate fits.
FAMILY_WORDS = {
    "opus": lambda nm: "Opus" in nm,
    "sonnet": lambda nm: "Sonnet" in nm,
    "haiku": lambda nm: "Haiku" in nm,
    "fable": lambda nm: "Fable" in nm,
    "gemini": lambda nm: nm.startswith("Gemini"),
    "flash": lambda nm: "Flash" in nm,
    "deepseek": lambda nm: nm.startswith("DeepSeek"),
    "grok": lambda nm: nm.startswith("Grok"),
    "kimi": lambda nm: nm.startswith("Kimi"),
    "glm": lambda nm: nm.startswith("GLM"),
    "gpt": lambda nm: nm.startswith("GPT"),
}

ALIAS = {}  # alias -> agent name (or None when two agents share it)
for a in AGENTS:
    for al in _aliases(a["name"]):
        ALIAS[al] = None if (al in ALIAS and ALIAS[al] != a["name"]) else a["name"]
ALIAS = {k: v for k, v in ALIAS.items() if v}

_tokens = sorted(set(ALIAS) | set(FAMILY_WORDS), key=len, reverse=True)
MENTION_RE = re.compile(r"(?<![\w.\-])@?(" + "|".join(re.escape(t) for t in _tokens) + r")(?![\w\-]|\.\d)", re.I)

# Active windows from the event log (first..last action), filled lazily.
ACTIVE = {}


def load_active():
    if ACTIVE:
        return ACTIVE
    first, last = {}, {}
    for e in rows("events.jsonl.gz"):
        d = e["data"]
        aid = d.get("speakerId") if d.get("actionType") == "AGENT_TALK" else d.get("agentId")
        if aid in BY_ID:
            day = e["created_at"][:10]
            nm = BY_ID[aid]["name"]
            first[nm] = min(first.get(nm, day), day)
            last[nm] = max(last.get(nm, day), day)
    for nm in first:
        ACTIVE[nm] = (first[nm], last[nm])
    return ACTIVE


def active_on(day_iso):
    load_active()
    return [nm for nm, (f, l) in ACTIVE.items() if f <= day_iso <= l]


def resolve(text, speaker, day_iso, candidates=None):
    """Return list of (agent_name, start, end) mentions in text, excluding the speaker.

    candidates: optional set of agent names present in the speaker's context (room/week),
    used only to disambiguate bare family words.
    """
    out = []
    act = None
    for m in MENTION_RE.finditer(text):
        raw = m.group(1)
        tok = raw.lower()
        # single ordinary words (Opus, Sonnet, Muse, Luna, Flash…) must be capitalised;
        # "magnum opus" is never an agent
        if raw.isalpha() and not raw[0].isupper():
            continue
        if tok == "opus" and text[max(0, m.start() - 7):m.start()].lower().endswith("magnum "):
            continue
        target = ALIAS.get(tok)
        if target is None and tok in FAMILY_WORDS:
            if act is None:
                act = set(active_on(day_iso))
            pool = act & candidates if candidates else act
            fits = [nm for nm in pool if FAMILY_WORDS[tok](nm) and nm != speaker]
            if len(fits) != 1:
                continue
            target = fits[0]
        if target and target != speaker:
            out.append((target, m.start(), m.end()))
    return out
