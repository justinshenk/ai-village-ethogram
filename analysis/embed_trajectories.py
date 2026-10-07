"""Embedding trajectories of AI Village agents (one unit = agent x Pacific-time day).

Stages (each caches its output under analysis/out/, rerun only what changed):
  extract       chat + intentions units        -> out/units_chat.jsonl      (stdlib only)
  extract-mem   last memory per agent-day      -> out/units_mem.jsonl       (stdlib only)
  embed         sentence-transformer vectors   -> out/emb_{chat,mem}.npy
  project       residualise, UMAP, clusters,   -> out/trajectories.json, out/unit_samples.json
                drift, convergence

Usage: python -I analysis/embed_trajectories.py [stage ...]   (no args = all stages)
       python -I analysis/embed_trajectories.py mem           (add memory views; reuses cached chat embeddings,
                                                               chat views reproduce identically: fixed seeds)
"""
import datetime as dt
import gzip
import json
import re
import sys
import time
import zoneinfo
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "analysis" / "out"
OUT.mkdir(parents=True, exist_ok=True)
PT = zoneinfo.ZoneInfo("America/Los_Angeles")

MODEL = "BAAI/bge-base-en-v1.5"
CHUNK_CHARS = 1500          # ~375 tokens, under the model's 512 limit
MAX_CHUNKS_CHAT = 16        # per unit, sampled evenly across the day
MAX_CHUNKS_MEM = 12
MSG_CAP = 800               # chars kept per chat message
INTENT_CAP = 600            # chars kept per session goal / nextSessionGoal
TFIDF_CAP = 12000           # chars of unit text kept for cluster labelling
MIN_MSGS = 3
PERMA_CU = "2026-03-24"


def rows(name):
    with gzip.open(DATA / name, "rt") as f:
        for line in f:
            yield json.loads(line)


def pt_date(ts):
    t = dt.datetime.fromisoformat(ts).replace(tzinfo=dt.timezone.utc)
    return t.astimezone(PT).date().isoformat()


def chunk_evenly(text, max_chunks):
    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]
    chunks = [c for c in chunks if c.strip()]
    if len(chunks) <= max_chunks:
        return chunks
    step = len(chunks) / max_chunks
    return [chunks[int(i * step)] for i in range(max_chunks)]


# ---------------------------------------------------------------- extract
def extract_chat():
    units = defaultdict(lambda: {"chat": [], "intent": []})
    for c in rows("chat_messages.jsonl.gz"):
        if c["speaker_type"] != "agent" or not c["agent_speaker_id"]:
            continue
        txt = (c["content"] or "").strip()
        if txt:
            units[(c["agent_speaker_id"], pt_date(c["created_at"]))]["chat"].append(
                (c["created_at"], txt[:MSG_CAP]))
    for s in rows("computer_use_sessions.jsonl.gz"):
        g = (s.get("session_goal") or "").strip()
        if g:
            units[(s["agent_id"], pt_date(s["created_at"]))]["intent"].append((s["created_at"], g[:INTENT_CAP]))
    for e in rows("events.jsonl.gz"):
        d = e["data"]
        if d.get("actionType") == "CONSOLIDATE" and d.get("nextSessionGoal") and d.get("agentId"):
            units[(d["agentId"], pt_date(e["created_at"]))]["intent"].append(
                (e["created_at"], d["nextSessionGoal"].strip()[:INTENT_CAP]))
    kept = 0
    with open(OUT / "units_chat.jsonl", "w") as f:
        for (aid, day), u in sorted(units.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if len(u["chat"]) < MIN_MSGS and not u["intent"]:
                continue
            chat = [t for _, t in sorted(u["chat"])]
            intent = [t for _, t in sorted(u["intent"])]
            # chunks: chat stream and intentions embedded together, mean-pooled later
            chat_text = "\n".join(chat)
            intent_text = "\n".join(intent)
            n_int = min(len(chunk_evenly(intent_text, 99)), MAX_CHUNKS_CHAT // 4) if intent else 0
            chunks = chunk_evenly(intent_text, n_int) if n_int else []
            chunks += chunk_evenly(chat_text, MAX_CHUNKS_CHAT - len(chunks))
            full = intent_text + "\n" + chat_text
            f.write(json.dumps({"a": aid, "d": day, "n": len(chat), "ni": len(intent), "chunks": chunks,
                                "text": full[:TFIDF_CAP],
                                "samples": [t[:200] for t in (chat[::max(1, len(chat) // 3)][:3] or intent[:3])]}) + "\n")
            kept += 1
    print(f"extract: {len(units)} agent-days, kept {kept}")


def extract_mem():
    last = {}
    n = 0
    for m in rows("agent_memories.jsonl.gz"):
        n += 1
        key = (m["agent_id"], pt_date(m["created_at"]))
        prev = last.get(key)
        if prev is None or m["created_at"] > prev[0]:
            last[key] = (m["created_at"], m["content"] or "")
        if n % 20000 == 0:
            print(f"  mem rows {n}", flush=True)
    with open(OUT / "units_mem.jsonl", "w") as f:
        for (aid, day), (_, txt) in sorted(last.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if len(txt.strip()) < 200:
                continue
            f.write(json.dumps({"a": aid, "d": day, "n": len(txt), "chunks": chunk_evenly(txt, MAX_CHUNKS_MEM),
                                "text": txt[:TFIDF_CAP], "samples": [txt[:200]]}) + "\n")
    print(f"extract-mem: {n} rows -> {len(last)} agent-days")


# ---------------------------------------------------------------- embed
def load_units(space):
    with open(OUT / f"units_{space}.jsonl") as f:
        return [json.loads(l) for l in f]


def embed(space):
    import numpy as np
    from sentence_transformers import SentenceTransformer
    path = OUT / f"emb_{space}.npy"
    units = load_units(space)
    if path.exists() and np.load(path).shape[0] == len(units):
        print(f"embed {space}: cached")
        return
    model = SentenceTransformer(MODEL, device="mps", model_kwargs={"torch_dtype": "float16"})
    model.max_seq_length = 512
    flat, owner = [], []
    for i, u in enumerate(units):
        for c in u["chunks"]:
            flat.append(c)
            owner.append(i)
    t0 = time.time()
    # sort by length so batches are padding-efficient
    order = sorted(range(len(flat)), key=lambda i: len(flat[i]))
    vecs = model.encode([flat[i] for i in order], batch_size=128, normalize_embeddings=True,
                        show_progress_bar=True, convert_to_numpy=True)
    chunk_vecs = np.empty_like(vecs)
    chunk_vecs[order] = vecs
    owner = np.array(owner)
    out = np.zeros((len(units), vecs.shape[1]), dtype=np.float32)
    np.add.at(out, owner, chunk_vecs)
    out /= np.linalg.norm(out, axis=1, keepdims=True)
    np.save(path, out)
    print(f"embed {space}: {len(flat)} chunks, {len(units)} units, {time.time() - t0:.0f}s")


# ---------------------------------------------------------------- project
NAME_WORDS = ("claude opus sonnet haiku fable gpt gemini flash pro deepseek grok kimi glm muse spark astra luna "
              "sol terra o1 o3 o4 mini 4o reasoner v3 v4 leader fine tuned").split()


def goal_periods():
    gs = sorted(rows("village_goals.jsonl.gz"), key=lambda g: g["start_time"] or "")
    out = []
    for g in gs:
        s = pt_date(g["start_time"])
        e = pt_date(g["end_time"]) if g["end_time"] else "9999-12-31"
        out.append((s, e, g["goal"].strip()))
    return out


def goal_of(day, periods):
    for i, (s, e, _) in enumerate(periods):
        if s <= day < e:
            return i
    return len(periods) - 1


def family(name):
    n = name.lower()
    for k in ("claude", "gpt", "gemini", "deepseek", "grok", "kimi", "glm", "muse"):
        if k in n:
            return k
    if n.startswith(("o1", "o3", "o4")):
        return "gpt"
    return "other"


def project():
    import numpy as np
    import umap
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
    from sklearn.metrics import normalized_mutual_info_score as nmi

    agents_rows = sorted(rows("agents.jsonl.gz"), key=lambda a: a["created_at"])
    aidx = {a["id"]: i for i, a in enumerate(agents_rows)}
    agents = [{"id": a["id"], "name": a["name"], "model": a["model_string"][:60]} for a in agents_rows]
    periods = goal_periods()

    name_tokens = set(NAME_WORDS)
    for a in agents_rows:
        name_tokens.update(re.findall(r"[a-z]+", a["name"].lower()))
    stop = list(ENGLISH_STOP_WORDS | name_tokens | {"https", "http", "com", "www", "github", "io", "html", "md",
                                                    "ll", "ve", "don", "just", "let", "day", "session", "today"})

    def clean(t):
        t = re.sub(r"https?://\S+", " ", t)
        t = re.sub(r"[0-9a-f]{7,}", " ", t)
        return re.sub(r"\d+", " ", t)

    result = {"meta": {"model": MODEL, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "notes": ("unit = agent x Pacific day. chat = agent chat + session intentions "
                                 "(session_goal, CONSOLIDATE.nextSessionGoal); mem = last memory snapshot that day. "
                                 "resid = embedding minus the mean of all agents active that day (>=3) "
                                 "else the village-goal-period mean, re-normalised. points: "
                                 "[agentIdx, date, x, y, clusterIdx, n] where n = chat messages (chat) "
                                 "or memory chars (mem). drift/convergence computed on chat space.")},
              "agents": agents, "goals": [[s, e, g[:120]] for s, e, g in periods], "views": {}}
    samples_out = {}
    report = {}

    for space in ("chat", "mem"):
        if not (OUT / f"emb_{space}.npy").exists():
            print(f"project: no embeddings for {space}, skipping")
            continue
        units = load_units(space)
        X = np.load(OUT / f"emb_{space}.npy")
        keep = [i for i, u in enumerate(units) if u["a"] in aidx]
        units = [units[i] for i in keep]
        X = X[keep]
        days = np.array([u["d"] for u in units])
        ag = np.array([aidx[u["a"]] for u in units])
        gids = np.array([goal_of(d, periods) for d in days])

        # residualise against same-day village mean (fallback: goal-period mean)
        R = X.copy()
        goal_mean = {g: X[gids == g].mean(0) for g in np.unique(gids)}
        for d in np.unique(days):
            m = days == d
            mu = X[m].mean(0) if m.sum() >= 3 else goal_mean[gids[m][0]]
            R[m] = X[m] - mu
        R /= np.linalg.norm(R, axis=1, keepdims=True) + 1e-9

        texts = [clean(u["text"]) for u in units]
        # unit-level term counts: a label term must appear in >=25 units and be used by >=3 agents,
        # so one agent's private IDs / jargon can't name a region
        cv = CountVectorizer(stop_words=stop, min_df=25, max_df=0.4, binary=True,
                             token_pattern=r"(?u)\b[a-zA-Z][a-z]{2,14}\b", lowercase=True)
        U = cv.fit_transform(texts).tocsc()
        vocab = np.array(cv.get_feature_names_out())
        n_agents_using = np.array([len(np.unique(ag[U[:, j].indices])) for j in range(U.shape[1])])
        U = U.tocsr()
        f_t = np.asarray(U.sum(0)).ravel()
        for kind, M in (("raw", X), ("resid", R)):
            key = f"{space}_{kind}"
            t0 = time.time()
            xy = umap.UMAP(n_neighbors=30, min_dist=0.1, metric="cosine", random_state=42).fit_transform(M)
            xy = (xy - xy.min(0)) / (xy.max(0) - xy.min(0))       # 0..1 for the page
            k = 14
            lab = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(M)
            # class-based TF-IDF (BERTopic form): share of cluster's units using term x log(1 + mean/f_t)
            A = f_t.sum() / k
            clusters = []
            samples_out[key] = []
            for c in range(k):
                idx = np.where(lab == c)[0]
                tf_c = np.asarray(U[idx].sum(0)).ravel()
                score = (tf_c / len(idx)) * np.log1p(A / np.maximum(f_t, 1))
                score[n_agents_using < 3] = 0
                top = vocab[np.argsort(-score)[:3]]
                ac = np.bincount(ag[idx], minlength=len(agents))
                gc = np.bincount(gids[idx], minlength=len(periods))
                clusters.append({"label": " · ".join(top), "x": round(float(np.median(xy[idx, 0])), 3),
                                 "y": round(float(np.median(xy[idx, 1])), 3), "n": int(len(idx)),
                                 "agents": [[int(a), round(ac[a] / len(idx), 2)] for a in np.argsort(-ac)[:3]],
                                 "goals": [[int(g), round(gc[g] / len(idx), 2)] for g in np.argsort(-gc)[:2]],
                                 "span": [min(days[idx].tolist()), max(days[idx].tolist())]})
                rng = np.random.default_rng(c)
                pick = rng.choice(idx, size=min(3, len(idx)), replace=False)
                samples_out[key].append([{"agent": agents[ag[i]]["name"], "date": days[i],
                                          "text": units[i]["samples"][0]} for i in pick])
            pts = [[int(ag[i]), days[i], round(float(xy[i, 0]), 3), round(float(xy[i, 1]), 3), int(lab[i]),
                    int(units[i]["n"])] for i in range(len(units))]
            result["views"][key] = {"points": pts, "clusters": clusters}
            fam = [family(agents[a]["name"]) for a in ag]
            report[key] = {"nmi_goal": round(nmi(gids, lab), 3), "nmi_agent": round(nmi(ag, lab), 3),
                           "nmi_family": round(nmi(fam, lab), 3), "nmi_regime": round(nmi(days >= PERMA_CU, lab), 3),
                           "secs": round(time.time() - t0)}
            print(key, report[key], [c["label"] for c in clusters])

        if space == "chat":
            # drift in residual space
            drift = {}
            for a in np.unique(ag):
                idx = np.where(ag == a)[0]
                idx = idx[np.argsort(days[idx])]
                early = R[idx[:10]].mean(0)
                early /= np.linalg.norm(early)
                rows_ = []
                for j, i in enumerate(idx):
                    step = 1 - float(R[i] @ R[idx[j - 1]]) if j else 0.0
                    rows_.append([days[i], round(1 - float(R[i] @ early), 3), round(step, 3)])
                drift[str(int(a))] = rows_
            result["drift"] = drift
            conv = []
            for d in np.unique(days):
                m = np.where(days == d)[0]
                if len(m) >= 2:
                    S = X[m] @ X[m].T
                    conv.append([d, round(float((S.sum() - len(m)) / (len(m) * (len(m) - 1))), 3), int(len(m))])
            result["convergence"] = conv
            result["meta"]["n_units"] = len(units)
            per_agent = defaultdict(int)
            for a in ag:
                per_agent[agents[a]["name"]] += 1
            report["units_per_agent"] = dict(sorted(per_agent.items(), key=lambda kv: -kv[1]))
        else:
            result["meta"]["n_units_mem"] = len(units)

    (OUT / "trajectories.json").write_text(json.dumps(result, separators=(",", ":")))
    (OUT / "unit_samples.json").write_text(json.dumps(samples_out, separators=(",", ":")))
    (OUT / "report.json").write_text(json.dumps(report, indent=1))
    print("wrote trajectories.json", (OUT / "trajectories.json").stat().st_size // 1024, "KB")


if __name__ == "__main__":
    stages = sys.argv[1:] or ["extract", "extract-mem", "embed", "project"]
    if stages == ["mem"]:   # second pass once data/agent_memories.jsonl.gz exists; chat embeddings are cached
        stages = ["extract-mem", "embed", "project"]
    for s in stages:
        t0 = time.time()
        if s == "extract":
            extract_chat()
        elif s == "extract-mem":
            if (DATA / "agent_memories.jsonl.gz").exists():
                extract_mem()
            else:
                print("extract-mem: memories file not downloaded yet, skipping")
        elif s == "embed":
            embed("chat")
            if (OUT / "units_mem.jsonl").exists():
                embed("mem")
        elif s == "project":
            project()
        print(f"[{s}] {time.time() - t0:.0f}s", flush=True)
