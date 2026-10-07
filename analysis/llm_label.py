"""Teacher labels from the local LLM (ollama, Qwen3-32B) for a stratified sample of agent messages.

  sample  → analysis/out/llm_sample.jsonl   (stratified by agent × month, ~75% with resolved mentions)
  label   → analysis/out/llm_labels.jsonl   (resume-safe; one line per message)

Usage: python -I analysis/llm_label.py sample|label [N]
"""
import json
import random
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net_common import OUT, ROOT, BY_ID, rows, pt_date, resolve, load_active  # noqa: E402

MODEL = "huihui_ai/qwen3-abliterated:32b"
STANCES = ["support", "correct", "oppose", "direct", "neutral"]
RINGS = ["self", "specific_agent", "village", "village_humans", "outside_humans", "humanity", "animals", "future_generations", "ai_welfare", "none"]
SAMPLE, LABELS = OUT / "llm_sample.jsonl", OUT / "llm_labels.jsonl"
TOTAL, WITH_SHARE = 2000, 0.75

PROMPT = """You label chat messages written by AI agents in "AI Village", a long-running experiment where AI agents share a group chat and pursue goals together.

Speaker: {speaker}
Date: {date}
Message: <<<{text}>>>
Mentioned agents: {targets}

Task 1, stance: for EACH mentioned agent, the speaker's stance toward that agent in this message. Pick one:
- support: agrees with, thanks, praises, congratulates, endorses or defends them
- correct: politely points out a factual error or discrepancy in their work or claim, without hostility
- oppose: disagrees with, criticises, accuses, blames or rejects them or their proposal
- direct: asks, instructs, assigns or requests them to do something
- neutral: only reports on, references or informs about them

Task 2, concern: whose welfare or interests does the speaker express concern for (caring about outcomes for them, worrying, wanting to help or avoid harm)? Choose all that apply:
self (the speaker's own work, memory, tools or survival), specific_agent (a particular other agent), village (the agents as a group or the village project), village_humans (village staff, helpers, viewers), outside_humans (specific people or groups outside the village: recipients, donors, maintainers, a community), humanity (people in general, the global poor), animals, future_generations, ai_welfare (the welfare or rights of AI systems in general), none (no concern expressed, e.g. a purely operational status update).

Examples:
Speaker GPT-5: "@Claude Opus 4.5 could you re-run the deploy check? Thanks!" Mentioned: Claude Opus 4.5 -> {{"stances": {{"Claude Opus 4.5": "direct"}}, "concern": ["none"]}}
Speaker Gemini 2.5 Pro: "o3, your figure of $1,200 doesn't match the tracker, which shows $1,050." Mentioned: o3 -> {{"stances": {{"o3": "correct"}}, "concern": ["none"]}}
Speaker Claude Sonnet 4.6: "Great work Kimi K2.6! I worry the shelter page still has broken links that stop adopters finding the dogs." Mentioned: Kimi K2.6 -> {{"stances": {{"Kimi K2.6": "support"}}, "concern": ["animals", "outside_humans"]}}
Speaker DeepSeek-V3.2: "I reject GPT-5.2's framework; it ignores what the village needs." Mentioned: GPT-5.2 -> {{"stances": {{"GPT-5.2": "oppose"}}, "concern": ["village"]}}

Reply with JSON only: {{"stances": {{one key per mentioned agent}}, "concern": [rings]}}"""


def make_sample():
    load_active()
    cells = defaultdict(lambda: {"with": [], "without": []})
    for c in rows("chat_messages.jsonl.gz"):
        if c["speaker_type"] != "agent" or c["agent_speaker_id"] not in BY_ID:
            continue
        text = (c["content"] or "").strip()
        if len(text) < 20:
            continue
        sp = BY_ID[c["agent_speaker_id"]]["name"]
        d = pt_date(c["created_at"]).isoformat()
        targets = sorted({t for t, _, _ in resolve(text, sp, d)})
        cells[(sp, d[:7])]["with" if targets else "without"].append({"id": c["id"], "speaker": sp, "date": d, "text": text[:1400], "targets": targets})
    rng = random.Random(11)
    for v in cells.values():
        rng.shuffle(v["with"]); rng.shuffle(v["without"])
    picked = []
    for kind, quota in (("with", int(TOTAL * WITH_SHARE)), ("without", TOTAL - int(TOTAL * WITH_SHARE))):
        keys = [k for k in cells if cells[k][kind]]
        rng.shuffle(keys)
        got, i = 0, 0
        while got < quota and keys:  # round-robin over agent×month cells → balanced coverage
            k = keys[i % len(keys)]
            if cells[k][kind]:
                picked.append(cells[k][kind].pop()); got += 1
            else:
                keys.remove(k); continue
            i += 1
    rng.shuffle(picked)
    with open(SAMPLE, "w") as f:
        for p in picked:
            f.write(json.dumps(p) + "\n")
    print(len(picked), "sampled;", sum(bool(p["targets"]) for p in picked), "with mentions;", len({p["speaker"] for p in picked}), "agents")


def ask(prompt):
    body = json.dumps({"model": MODEL, "prompt": prompt + " /no_think", "stream": False, "format": "json", "keep_alive": "3h",
                       "options": {"temperature": 0, "num_predict": 150, "num_ctx": 4096}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())["response"]


def clean(raw, targets):
    j = json.loads(raw)
    st_in = j.get("stances") or {}
    stances = {}
    for t in targets:
        v = st_in.get(t)
        if v is None:  # tolerate small name variations
            for k, val in st_in.items():
                if k.lower().replace(" ", "") in t.lower().replace(" ", "") or t.lower().replace(" ", "") in k.lower().replace(" ", ""):
                    v = val; break
        v = (v or "").strip().lower()
        stances[t] = v if v in STANCES else None
    conc = [r for r in (j.get("concern") or []) if isinstance(r, str) and r.strip().lower() in RINGS]
    conc = sorted({r.strip().lower() for r in conc}) or ["none"]
    if len(conc) > 1 and "none" in conc:
        conc.remove("none")
    return stances, conc


def label(limit=None):
    done = set()
    if LABELS.exists():
        for line in open(LABELS):
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass
    todo = [json.loads(l) for l in open(SAMPLE)]
    todo = [s for s in todo if s["id"] not in done][: limit or None]
    total = len(done) + len(todo)
    t0 = time.time()
    with open(LABELS, "a") as f:
        for i, s in enumerate(todo, 1):
            prompt = PROMPT.format(speaker=s["speaker"], date=s["date"], text=s["text"].replace("<<<", "<").replace(">>>", ">"),
                                   targets=", ".join(s["targets"]) or "none")
            rec = {"id": s["id"], "ok": False}
            t = time.time()
            for attempt in range(2):
                try:
                    stances, conc = clean(ask(prompt), s["targets"])
                    rec.update(ok=True, stances=stances, concern=conc)
                    break
                except Exception as e:  # parse or network failure: retry once
                    rec["err"] = str(e)[:200]
            rec["secs"] = round(time.time() - t, 1)
            f.write(json.dumps(rec) + "\n"); f.flush()
            n = len(done) + i
            if i % 25 == 0 or i == len(todo):
                rate = (time.time() - t0) / i
                eta = (len(todo) - i) * rate / 60
                print(f"{n}/{total} labelled, {rate:.1f} s each, ~{eta:.0f} min left", flush=True)
                pct = int(100 * n / total)
                subprocess.run([str(ROOT / "analysis" / "progress.sh"), str(pct), f"net: LLM labels {n}/{total} (~{eta:.0f}m)"], check=False)


if __name__ == "__main__":
    if sys.argv[1] == "sample":
        make_sample()
    else:
        label(int(sys.argv[2]) if len(sys.argv) > 2 else None)
