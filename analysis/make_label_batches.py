"""Stratified sample of agent chat messages for LLM labelling, split into batches.

~75% of the sample names at least one other agent, ~25% does not. Sampling is spread
evenly over agent x month cells. 5% of each batch also appears in the next batch, so
agreement between labelling agents can be measured.
Writes analysis/out/label_batches/batch_XX.jsonl and roster.json.
"""
import gzip
import json
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out" / "label_batches"
OUT.mkdir(parents=True, exist_ok=True)
random.seed(11)
TARGET, BATCH, OVERLAP = 10000, 500, 25

agents = [json.loads(l) for l in gzip.open(DATA / "agents.jsonl.gz", "rt")]
names = {a["id"]: a["name"] for a in agents}
rooms = {r["id"]: r["name"] for r in map(json.loads, gzip.open(DATA / "chat_rooms.jsonl.gz", "rt"))}
pats = [re.compile(r"(?<![\w.])" + re.escape(a["name"]) + r"(?![\w.])", re.I) for a in agents if len(a["name"]) > 4]

cells = defaultdict(lambda: {"m": [], "n": []})
for line in gzip.open(DATA / "chat_messages.jsonl.gz", "rt"):
    c = json.loads(line)
    if c["speaker_type"] != "agent" or c["agent_speaker_id"] not in names:
        continue
    text = (c["content"] or "").strip()
    if len(text) < 20:
        continue
    speaker = names[c["agent_speaker_id"]]
    mentions = "@" in text or any(p.search(text) and p.pattern.lower().find(re.escape(speaker).lower()) < 0 for p in pats)
    cells[(speaker, c["created_at"][:7])]["m" if mentions else "n"].append(
        {"id": c["id"], "date": c["created_at"][:16], "speaker": speaker, "room": rooms.get(c["room_id"], "?"), "text": text[:1200]})

def draw(kind, total):
    pools = [v[kind] for v in cells.values() if v[kind]]
    out, per = [], max(1, total // len(pools))
    for p in pools:
        out += random.sample(p, min(per, len(p)))
    rest = [m for p in pools for m in p if m not in out]
    random.shuffle(rest)
    return (out + rest)[:total]

sample = draw("m", int(TARGET * 0.75)) + draw("n", TARGET - int(TARGET * 0.75))
random.shuffle(sample)
batches = [sample[i:i + BATCH] for i in range(0, len(sample), BATCH)]
for i, b in enumerate(batches):
    nxt = batches[(i + 1) % len(batches)]
    b = b + [dict(m, overlap=True) for m in nxt[:OVERLAP]]
    with open(OUT / f"batch_{i:02d}.jsonl", "w") as f:
        for m in b:
            f.write(json.dumps(m) + "\n")
roster = sorted(({"name": a["name"], "model": a["model_string"], "joined": a["created_at"][:10]} for a in agents), key=lambda x: x["joined"])
(OUT / "roster.json").write_text(json.dumps(roster, indent=0))
print(len(sample), "messages in", len(batches), "batches of", BATCH, "+", OVERLAP, "overlap")
