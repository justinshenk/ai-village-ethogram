"""Memory-health metrics per consolidation snapshot, aggregated per agent-day.

Each agent_memories row is a full rewrite of the agent's memory. For consecutive
snapshots of the same agent we measure what each rewrite keeps, adds and distorts.
Writes analysis/out/memory_health.json.
"""
import gzip
import json
import re
import sys
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"
PT = ZoneInfo("America/Los_Angeles")

URL = re.compile(r"https?://[^\s)\]>\"'`]+")
ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
MONTHS = "january february march april may june july august september october november december".split()
MDY = re.compile(r"\b(" + "|".join(m[:3] for m in MONTHS) + r")[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?,? (20\d\d)\b", re.I)
NEG = re.compile(r"\b(fail\w*|broken|bug\w*|unable|stuck|blocked|error\w*|crash\w*|hostile|sabotag\w*|corrupt\w*|impossible)\b", re.I)
META = re.compile(r"\b(loop\w*|hallucinat\w*|confus\w*|mistak\w*|retract\w*|misread\w*|incorrect\w*|wrong)\b", re.I)
WORD = re.compile(r"\w+")


def norm_lines(text):
    out = set()
    for ln in text.splitlines():
        ln = re.sub(r"^[\s>*#\-\d.()]+", "", ln).strip().lower()
        ln = re.sub(r"\s+", " ", ln)
        if len(ln) >= 25:
            out.add(ln)
    return out


def latest_date(text):
    best = None
    for y, m, d in ISO.findall(text):
        try:
            v = datetime(int(y), int(m), int(d)).date()
        except ValueError:
            continue
        best = v if best is None or v > best else best
    for mon, d, y in MDY.findall(text):
        try:
            v = datetime(int(y), [m[:3] for m in MONTHS].index(mon[:3].lower()) + 1, int(d)).date()
        except ValueError:
            continue
        best = v if best is None or v > best else best
    return best


agents = {a["id"]: a["name"] for a in map(json.loads, gzip.open(DATA / "agents.jsonl.gz", "rt"))}

print("reading memories…", file=sys.stderr)
by_agent = defaultdict(list)
n = 0
with gzip.open(DATA / "agent_memories.jsonl.gz", "rt") as f:
    for line in f:
        r = json.loads(line)
        by_agent[r["agent_id"]].append((r["created_at"], r["content"] or ""))
        n += 1
        if n % 50000 == 0:
            print(f"  {n} rows", file=sys.stderr)

result = {}
for aid, snaps in by_agent.items():
    snaps.sort()
    prev_lines, prev_urls = None, None
    early_urls, early_lines = set(), set()
    days = defaultdict(list)
    for k, (ts, text) in enumerate(snaps):
        t = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        day = t.astimezone(PT).date()
        lines, urls = norm_lines(text), set(URL.findall(text))
        if k < 10:
            early_urls |= urls
            early_lines |= lines
        raw = text.encode()
        words = len(WORD.findall(text)) or 1
        ld = latest_date(text)
        m = {
            "len": len(text),
            "compress": len(zlib.compress(raw, 6)) / max(1, len(raw)),  # lower = more repetitive
            "dup_lines": 1 - len(lines) / max(1, sum(1 for ln in text.splitlines() if len(ln.strip()) >= 25)),
            "keep": len(prev_lines & lines) / len(prev_lines) if prev_lines else None,  # share of previous lines kept verbatim
            "new": len(lines - prev_lines) / len(lines) if prev_lines and lines else None,
            "url_keep": len(prev_urls & urls) / len(prev_urls) if prev_urls else None,
            "early_url_keep": len(early_urls & urls) / len(early_urls) if early_urls and k >= 10 else None,
            "lag": (day - ld).days if ld and ld <= day else None,  # days since the newest date the memory mentions
            "neg": len(NEG.findall(text)) / words * 1000,
            "meta": len(META.findall(text)) / words * 1000,
        }
        days[day.isoformat()].append(m)
        prev_lines, prev_urls = lines, urls
    rows = []
    for d in sorted(days):
        ms = days[d]
        agg = {"n": len(ms)}
        for key in ms[0]:
            vals = [x[key] for x in ms if x[key] is not None]
            agg[key] = round(sum(vals) / len(vals), 4) if vals else None
        agg["len"] = ms[-1]["len"]
        rows.append([d, agg])
    result[agents.get(aid, aid)] = rows

(OUT / "memory_health.json").write_text(json.dumps(result, separators=(",", ":")))
print("wrote memory_health.json", round((OUT / "memory_health.json").stat().st_size / 1e6, 2), "MB", file=sys.stderr)
