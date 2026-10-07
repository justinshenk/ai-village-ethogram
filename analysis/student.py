"""Student classifiers that extend teacher labels to every agent message.

Stages (python -I analysis/student.py <stage>):
  embed   bge-base embeddings of every agent message (concern) and of every resolved mention
          window (stance: "speaker → target: …±200 chars…")  → out/stu_msg.npy, out/stu_win.npy + index files
  train   5-fold CV on teacher labels (out/llm_labels_claude.jsonl), report F1, fit on all, predict everything
          → out/stu_pred_stance.jsonl.gz, out/stu_pred_concern.jsonl.gz, out/student_report.json
  build   aggregate predictions → out/signed_edges.json and out/concern.json
"""
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net_common import OUT, BY_ID, NAMES, rows, pt_date, week_of, week_start  # noqa: E402

STANCES = ["support", "correct", "oppose", "direct", "neutral"]
RINGS = ["self", "specific_agent", "village", "village_humans", "outside_humans", "humanity", "animals", "ai_welfare"]  # future_generations had no teacher positives
import os
TEACHER = Path(os.environ.get("TEACHER", OUT / "llm_labels_claude.jsonl"))
MODEL = "BAAI/bge-base-en-v1.5"


def load_messages():
    msgs = {}
    for c in rows("chat_messages.jsonl.gz"):
        if c["speaker_type"] == "agent" and c["agent_speaker_id"] in BY_ID:
            msgs[c["id"]] = (BY_ID[c["agent_speaker_id"]]["name"], pt_date(c["created_at"]).isoformat(), c["content"] or "")
    return msgs


def windows():
    """(msg_id, target, text) per resolved mention pair; window around the first mention of that target."""
    msgs = load_messages()
    out = []
    with open(OUT / "mentions_chat.jsonl") as f:
        for line in f:
            r = json.loads(line)
            sp, d, text = msgs[r["id"]]
            seen = set()
            for t, a, b in r["m"]:
                if t in seen:
                    continue
                seen.add(t)
                lo, hi = max(0, a - 200), min(len(text), b + 200)
                out.append((r["id"], t, f"{sp} → {t}: {text[lo:hi]}"))
    return msgs, out


def embed():
    from sentence_transformers import SentenceTransformer
    import torch
    msgs, wins = windows()
    model = SentenceTransformer(MODEL, device="mps" if torch.backends.mps.is_available() else "cpu")
    model.half()
    model.max_seq_length = 256
    ids = list(msgs)
    print(f"embedding {len(ids)} messages and {len(wins)} mention windows", file=sys.stderr)
    E = model.encode([msgs[i][2][:1500] for i in ids], batch_size=128, normalize_embeddings=True, show_progress_bar=True, convert_to_numpy=True)
    np.save(OUT / "stu_msg.npy", E.astype(np.float16))
    (OUT / "stu_msg_ids.json").write_text(json.dumps(ids))
    W = model.encode([w[2] for w in wins], batch_size=128, normalize_embeddings=True, show_progress_bar=True, convert_to_numpy=True)
    np.save(OUT / "stu_win.npy", W.astype(np.float16))
    (OUT / "stu_win_ids.json").write_text(json.dumps([[w[0], w[1]] for w in wins]))
    print("done", E.shape, W.shape, file=sys.stderr)


# ---------------------------------------------------------------- train
def load_teacher():
    """Merge duplicate labels (overlapping batches) by majority vote."""
    by = defaultdict(list)
    for line in open(TEACHER):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("id"):
            by[r["id"]].append(r)
    stance, concern, agree = {}, {}, []
    for mid, rs in by.items():
        votes = defaultdict(Counter)
        for r in rs:
            for t, v in (r.get("stances") or {}).items():
                if v in STANCES:
                    votes[t][v] += 1
        for t, c in votes.items():
            stance[(mid, t)] = c.most_common(1)[0][0]
            if len(rs) > 1 and sum(c.values()) > 1:
                agree.append(c.most_common(1)[0][1] / sum(c.values()))
        ring_votes = Counter(x for r in rs for x in set(r.get("concern") or []) if x in RINGS)
        concern[mid] = {x for x, n in ring_votes.items() if n * 2 >= len(rs)}
    return stance, concern, (round(float(np.mean(agree)), 3) if agree else None), len(by)


def train():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedKFold, KFold
    stance_lab, concern_lab, dup_agree, n_teacher = load_teacher()
    msg_ids = json.loads((OUT / "stu_msg_ids.json").read_text()); E = np.load(OUT / "stu_msg.npy").astype(np.float32)
    win_ids = [tuple(x) for x in json.loads((OUT / "stu_win_ids.json").read_text())]; W = np.load(OUT / "stu_win.npy").astype(np.float32)
    mpos = {m: i for i, m in enumerate(msg_ids)}; wpos = {k: i for i, k in enumerate(win_ids)}
    report = {"teacher_messages": n_teacher, "duplicate_agreement": dup_agree}

    # stance
    keys = [k for k in stance_lab if k in wpos]
    msgs = load_messages()
    nid = {nm: i for i, nm in enumerate(NAMES)}
    def feats(klist):
        ids = np.zeros((len(klist), 2 * len(NAMES)), np.float32)
        for r, k in enumerate(klist):
            ids[r, nid[msgs[k[0]][0]]] = 1; ids[r, len(NAMES) + nid[k[1]]] = 1
        return np.hstack([W[[wpos[k] for k in klist]], E[[mpos[k[0]] for k in klist]], ids])
    X = feats(keys); y = np.array([STANCES.index(stance_lab[k]) for k in keys])
    present = [c for c in range(len(STANCES)) if (y == c).sum() >= 10]
    best = None
    for C in (0.5, 2.0):
        oof = np.zeros(len(y), dtype=int)
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(X, y):
            clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(X[tr], y[tr])
            oof[te] = clf.predict(X[te])
        mf = f1_score(y, oof, labels=present, average="macro")
        if best is None or mf > best[0]:
            best = (mf, C, oof)
    mf, C, oof = best
    per = f1_score(y, oof, labels=list(range(len(STANCES))), average=None, zero_division=0)
    conf = np.zeros((len(STANCES), len(STANCES)), dtype=int)
    for a, b in zip(y, oof):
        conf[a, b] += 1
    usable_st = [STANCES[c] for c in range(len(STANCES)) if per[c] >= 0.55 and (y == c).sum() >= 30]
    report["stance"] = {"n": len(y), "C": C, "macro_f1": round(float(mf), 3), "per_class": {STANCES[c]: round(float(per[c]), 3) for c in range(len(STANCES))},
                        "support": {STANCES[c]: int((y == c).sum()) for c in range(len(STANCES))}, "confusion": conf.tolist(), "usable": usable_st}
    clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(X, y)
    allk = [k for k in wpos if k[0] in msgs and k[1] in nid]
    pred, prob = [], []
    for b0 in range(0, len(allk), 20000):
        Xb = feats(allk[b0:b0 + 20000]); pred += list(clf.predict(Xb)); prob += list(clf.predict_proba(Xb).max(1))
    pred = dict(zip(allk, pred)); prob = dict(zip(allk, prob))
    with gzip.open(OUT / "stu_pred_stance.jsonl.gz", "wt") as f:
        for k in allk:
            i = k
            lab = stance_lab.get(k)
            f.write(json.dumps([k[0], k[1], lab if lab else STANCES[int(pred[k])], 1.0 if lab else round(float(prob[k]), 3), 1 if lab else 0]) + "\n")

    # concern (one-vs-rest per ring, threshold tuned on out-of-fold probabilities)
    cids = [m for m in concern_lab if m in mpos]
    Xc = E[[mpos[m] for m in cids]]
    Y = np.array([[1 if r in concern_lab[m] else 0 for r in RINGS] for m in cids])
    ring_rep, models = {}, {}
    for k, r in enumerate(RINGS):
        yk = Y[:, k]
        if yk.sum() < 15:
            ring_rep[r] = {"positives": int(yk.sum()), "f1": None, "usable": False}
            continue
        oofp = np.zeros(len(yk))
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(Xc, yk):
            m = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000).fit(Xc[tr], yk[tr])
            oofp[te] = m.predict_proba(Xc[te])[:, 1]
        ths = np.linspace(0.2, 0.9, 15)
        f1s = [f1_score(yk, (oofp >= t).astype(int), zero_division=0) for t in ths]
        t = float(ths[int(np.argmax(f1s))]); f1 = float(max(f1s))
        prec_rate = float(((oofp >= t).astype(int)).mean())
        ring_rep[r] = {"positives": int(yk.sum()), "prevalence": round(float(yk.mean()), 3), "f1": round(f1, 3), "threshold": round(t, 2),
                       "predicted_rate": round(prec_rate, 3), "usable": bool(f1 >= 0.5 and yk.sum() >= 30)}
        models[r] = (LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000).fit(Xc, yk), t)
    report["concern"] = {"n": len(cids), "rings": ring_rep, "usable": [r for r in RINGS if ring_rep[r]["usable"]],
                         "macro_f1": round(float(np.mean([v["f1"] for v in ring_rep.values() if v["f1"] is not None])), 3)}
    probs = {r: m.predict_proba(E)[:, 1] for r, (m, t) in models.items()}
    with gzip.open(OUT / "stu_pred_concern.jsonl.gz", "wt") as f:
        for i, mid in enumerate(msg_ids):
            if mid in concern_lab:
                rings, src = sorted(concern_lab[mid]), 1
            else:
                rings, src = [r for r, (m, t) in models.items() if probs[r][i] >= t], 0
            f.write(json.dumps([mid, rings, src]) + "\n")
    (OUT / "student_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


# ---------------------------------------------------------------- build
ROOMS_START = "2026-02-25"
AGREE = {"targets": 0.89, "stances": 0.85, "concern": 0.80, "n": 500}  # coordinator's double-labelled overlap
HAND = (38, 40)  # my hand check of 40 teacher labels
RING_DIST = {r: k for k, r in enumerate(RINGS)}
IDX = {n: i for i, n in enumerate(NAMES)}


def balance_partition(nodes, edges, restarts=60, seed=0):
    """Two-faction split minimising weighted frustration. edges: {(a,b): signed weight} undirected."""
    rng = np.random.default_rng(seed)
    nodes = list(nodes)
    if len(nodes) < 2 or not edges:
        return {n: 1 for n in nodes}, 0.0
    pos = {n: k for k, n in enumerate(nodes)}
    A = np.zeros((len(nodes), len(nodes)))
    for (a, b), w in edges.items():
        A[pos[a], pos[b]] += w; A[pos[b], pos[a]] += w
    tot = np.abs(A).sum() / 2 or 1

    def frustration(x):
        # frustrated: negative within (x_i x_j = 1, w < 0) or positive across (x_i x_j = -1, w > 0)
        m = np.outer(x, x)
        return float(((A < 0) & (m > 0)).astype(float).__mul__(np.abs(A)).sum() / 2 + ((A > 0) & (m < 0)).astype(float).__mul__(np.abs(A)).sum() / 2) / tot

    best_x, best_f = None, 9
    vals, vecs = np.linalg.eigh(A)
    starts = [np.sign(vecs[:, -1]) + (vecs[:, -1] == 0), np.ones(len(nodes))]
    starts += [rng.choice([-1, 1], len(nodes)) for _ in range(restarts)]
    for x in starts:
        x = x.astype(float)
        improved = True
        while improved:  # greedy single-node flips
            improved = False
            for k in range(len(nodes)):
                field = x[k] * (A[k] @ x - A[k, k] * x[k])  # < 0: node k disagrees with its ties, flipping reduces frustration
                if field < -1e-12:
                    x[k] = -x[k]; improved = True
        f = frustration(x)
        if f < best_f:
            best_f, best_x = f, x.copy()
    return {n: int(best_x[pos[n]]) for n in nodes}, round(best_f, 4)


def bradley_terry(wins, iters=200):
    """wins[(i,j)] = times i directed j. Returns log-strength (centred), with a weak prior."""
    players = sorted({p for k in wins for p in k})
    if not players:
        return {}
    p = {i: 1.0 for i in players}
    W = Counter(); n = Counter()
    for (i, j), c in wins.items():
        W[i] += c; n[(min(i, j), max(i, j))] += c
    for _ in range(iters):
        newp = {}
        for i in players:
            denom = 0.0
            for (a, b), c in n.items():
                if i in (a, b):
                    j = b if a == i else a
                    denom += c / (p[i] + p[j])
            denom += 2 / (p[i] + 1.0)  # prior: one win and one loss against an average opponent
            newp[i] = (W[i] + 1) / denom
        g = np.exp(np.mean(np.log(list(newp.values()))))
        p = {i: v / g for i, v in newp.items()}
    return {i: float(np.log(v)) for i, v in p.items()}


def build():
    """Phase 2 aggregates from teacher labels, weighted by each agent-month's sampling rate.
    The student extends only reliably-predicted concern rings (full-coverage series)."""
    rep = json.loads((OUT / "student_report.json").read_text())
    stance_lab, concern_lab, dup_agree, n_teacher = load_teacher()
    msgs = load_messages()
    teacher_name = "Claude (subagents)"
    # sampling weights: messages in the agent-month / labelled messages in the agent-month
    N, n = Counter(), Counter()
    for mid, (sp, d, _) in msgs.items():
        N[(sp, d[:7])] += 1
    labelled = set(concern_lab) | {k[0] for k in stance_lab}
    for mid in labelled:
        if mid in msgs:
            sp, d, _ = msgs[mid]; n[(sp, d[:7])] += 1
    wt = lambda mid: N[(msgs[mid][0], msgs[mid][1][:7])] / max(1, n[(msgs[mid][0], msgs[mid][1][:7])])
    qtr = lambda m: f"{m[:4]}-{(int(m[5:7]) - 1) // 3 * 3 + 1:02d}"  # quarter, labelled by its first month

    # ---- stance ----
    rows_ = []  # (month, speaker, target, label, weight)
    for (mid, t), lab in stance_lab.items():
        if mid in msgs and t in IDX:
            sp, d, _ = msgs[mid]
            rows_.append((d[:7], sp, t, lab, wt(mid)))
    months = sorted({r[0] for r in rows_})
    periods = {"all": set(months), "pre_rooms": {m for m in months if m < ROOMS_START[:7]}, "post_rooms": {m for m in months if m >= ROOMS_START[:7]}}
    labels = {"all": "All time", "pre_rooms": "Before rooms", "post_rooms": "After rooms"}
    MIN = 8
    method = (f"{teacher_name}: 20 Sonnet subagents labelled {nf_(n_teacher)} messages sampled by agent and month. On 500 messages labelled twice independently, "
              f"targets matched {pct_(AGREE['targets'])}, stances {pct_(AGREE['stances'])} and concern sets {pct_(AGREE['concern'])}; a hand check of 40 labels agreed on {HAND[0]}/{HAND[1]}. "
              "Estimates use those labels directly, weighted by each agent-month's sampling rate.")
    out = {"stances": STANCES, "periods": {}, "period_labels": labels, "min_mentions": MIN, "power": {"periods": {}},
           "quality": {"stance": {"teacher": teacher_name, "teacher_n": n_teacher, "agreement": AGREE, "hand_check": {"n": HAND[1], "agree": round(HAND[0] / HAND[1], 3)}, "method": method,
                                  "label_counts": dict(Counter(r[3] for r in rows_)), "student_macro_f1": rep["stance"]["macro_f1"], "student_per_class": rep["stance"]["per_class"],
                                  "note": "Factions treat oppose and correct together as disagree; oppose alone is 0.5% of labelled mentions."}}}

    def pair_counts(ms):
        pc, raw = defaultdict(Counter), Counter()
        for m, i, j, lab, w in rows_:
            if m in ms:
                pc[(i, j)][lab] += w; raw[(i, j)] += 1
        return pc, raw

    def signed(pc, raw, min_n):
        ties, und = [], defaultdict(lambda: [0.0, 0.0])
        for (i, j), c in pc.items():
            if raw[(i, j)] < min_n:
                continue
            tot = sum(c.values())
            net = (c["support"] - c["oppose"] - c["correct"]) / tot  # oppose and correct merged as "disagree" (oppose alone is too rare)
            ties.append([IDX[i], IDX[j], round(net, 3), raw[(i, j)]])
            key = tuple(sorted((i, j)))
            und[key][0] += net * tot; und[key][1] += tot
        return ties, {k: v[0] / v[1] for k, v in und.items() if v[1]}

    for p, ms in periods.items():
        pc, raw = pair_counts(ms)
        ties, edges = signed(pc, raw, MIN)
        nodes = {a for k in edges for a in k}
        part, fr = balance_partition(nodes, edges)
        strength = Counter()
        for (a, b), w in edges.items():
            strength[a] += w; strength[b] += w
        A = sorted([x for x in nodes if part[x] > 0], key=lambda x: -strength[x])
        B = sorted([x for x in nodes if part[x] < 0], key=lambda x: -strength[x])
        if len(B) > len(A):
            A, B = B, A
        out["periods"][p] = {"order": [IDX[x] for x in A + B], "split_at": len(A), "ties": ties, "frustration": fr,
                             "factions": [[IDX[x] for x in A], [IDX[x] for x in B]], "negative_ties": sum(1 for w in edges.values() if w < 0), "ties_n": len(edges)}
        wins, gave, got = Counter(), Counter(), Counter()
        for m, i, j, lab, w in rows_:
            if m in ms and lab == "direct":
                wins[(i, j)] += 1; gave[i] += 1; got[j] += 1
        bt = bradley_terry(wins)
        out["power"]["periods"][p] = {"scores": [[IDX[i], round(sc, 3), gave[i], got[i]] for i, sc in bt.items() if gave[i] + got[i] >= 10]}
    fr_series = []
    for q in sorted({qtr(m) for m in months}):
        ms = {m for m in months if qtr(m) == q}
        pc, raw = pair_counts(ms)
        _, edges = signed(pc, raw, 3)
        nodes = {a for k in edges for a in k}
        _, fr = balance_partition(nodes, edges, restarts=20)
        tot = sum(sum(c.values()) for c in pc.values()) or 1
        fr_series.append([q, fr, round(sum(c["oppose"] for c in pc.values()) / tot, 4), round(sum(c["correct"] for c in pc.values()) / tot, 4)])
    out["frustration"] = fr_series
    (OUT / "signed_edges.json").write_text(json.dumps(out, separators=(",", ":")))

    # ---- concern (teacher, weighted) ----
    radius_of = lambda rs: float(np.mean([RING_DIST[r] for r in rs])) if rs else None
    per_agent = defaultdict(list)       # agent -> [(rings, w)]
    per_am = defaultdict(list)          # (agent, month) -> [(radius, w)]
    village = defaultdict(list)         # month -> [(radius, w)]
    for mid, rings in concern_lab.items():
        if mid not in msgs:
            continue
        sp, d, _ = msgs[mid]; w = wt(mid); rs = [r for r in rings if r in RING_DIST]
        per_agent[sp].append((rs, w))
        r = radius_of(rs)
        if r is not None:
            q = qtr(d[:7])
            per_am[(sp, q)].append((r, w)); village[q].append((r, w))
    wmean = lambda xs: sum(v * w for v, w in xs) / sum(w for _, w in xs)
    vmean = {m: wmean(v) for m, v in village.items() if v}
    agents = defaultdict(list)
    for (sp, m), xs in sorted(per_am.items()):
        if len(xs) >= 5:
            r = wmean(xs)
            agents[sp].append([m + "-01", round(r, 3), round(r - vmean[m], 3), len(xs)])
    MINM = 60
    summary, share_vals = {}, []
    for sp, lst in per_agent.items():
        if len(lst) < MINM:
            continue
        W_ = sum(w for _, w in lst)
        shares = {r: sum(w for rs, w in lst if r in rs) / W_ for r in RINGS}
        rad = [(radius_of(rs), w) for rs, w in lst if rs]
        summary[sp] = {"shares": {k: round(v, 4) for k, v in shares.items()}, "radius": round(wmean(rad), 3) if rad else 0.0, "n": len(lst),
                       "none_share": round(sum(w for rs, w in lst if not rs) / W_, 3)}
        share_vals += [v for v in shares.values() if v > 0]
    # student-extended full-coverage series for reliably predicted rings
    usable = [r for r in rep["concern"]["usable"]]
    ext = {r: defaultdict(Counter) for r in usable}  # ring -> agent -> month -> [hits, total]
    tot_am = Counter()
    with gzip.open(OUT / "stu_pred_concern.jsonl.gz", "rt") as f:
        for line in f:
            mid, rings, src = json.loads(line)
            sp, d, _ = msgs[mid]
            tot_am[(sp, d[:7])] += 1
            for r in usable:
                if r in rings:
                    ext[r][sp][d[:7]] += 1
    extended = {r: {sp: [[m + "-01", round(c / tot_am[(sp, m)], 4), tot_am[(sp, m)]] for m, c in sorted(by.items())] for sp, by in ext[r].items() if sum(by.values()) >= 20}
                for r in usable}
    goals = []
    for g in rows("village_goals.jsonl.gz"):
        txt = g["goal"].lower()
        if any(k in txt for k in ("poverty", "suffering", "kindness", "help gemini", "charity", "park")):
            goals.append([g["start_time"][:10], (g["end_time"] or "2026-12-31")[:10], g["goal"].strip()])
    co = {"rings": RINGS + ["none"], "ring_cap": round(float(np.percentile(share_vals or [0.1], 90)), 3), "min_msgs": MINM,
          "weeks": sorted({m + "-01" for m in N and {k[1] for k in N}}), "agents": {k: v for k, v in agents.items() if len(v) >= 2},
          "summary": summary, "goals": goals, "extended": extended, "bin": "quarter",
          "quality": {"teacher": teacher_name, "teacher_n": n_teacher, "agreement": AGREE, "hand_check": {"n": HAND[1], "agree": round(HAND[0] / HAND[1], 3)}, "student_macro_f1": rep["concern"]["macro_f1"],
                      "method": method + f" The full-coverage series for {', '.join(usable) or 'no ring'} come from a classifier trained on those labels (held-out F1 {', '.join(f'{r} {rep['concern']['rings'][r]['f1']}' for r in usable)}).",
                      "student_per_ring": {r: v.get("f1") for r, v in rep["concern"]["rings"].items()}}}
    (OUT / "concern.json").write_text(json.dumps(co, separators=(",", ":")))
    for fn in ("signed_edges.json", "concern.json"):
        print(fn, round((OUT / fn).stat().st_size / 1e6, 2), "MB", file=sys.stderr)
    a = out["periods"]["all"]
    print("label counts:", out["quality"]["stance"]["label_counts"], file=sys.stderr)
    print("factions (all):", [[NAMES[i] for i in grp] for grp in a["factions"]], "frustration", a["frustration"], "negative ties", a["negative_ties"], "of", a["ties_n"], file=sys.stderr)
    print("frustration by quarter:", fr_series, file=sys.stderr)
    top = sorted(out["power"]["periods"]["all"]["scores"], key=lambda r: -r[1])
    print("pecking order top:", [(NAMES[i], sc, g, r) for i, sc, g, r in top[:8]], "bottom:", [(NAMES[i], sc, g, r) for i, sc, g, r in top[-5:]], file=sys.stderr)
    print("radius by agent:", sorted(((v["radius"], k, v["n"]) for k, v in summary.items()), reverse=True), file=sys.stderr)


def nf_(x):
    return f"{x:,}"


def pct_(x):
    return "n/a" if x is None else f"{round(100 * x)}%"


if __name__ == "__main__":
    {"embed": embed, "train": train, "build": build}[sys.argv[1]]()
