"""Blog-post proposals grounded in the dataset and our analyses → analysis/out/blog.json.

Numbers that come from analysis/out/*.json are recomputed here and checked, so a rebuild
fails loudly if the underlying data changes. Numbers from one-off scans of the raw chat and
event tables (quotes, keyword counts) were verified on 2026-10-06 and carry their source.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"
load = lambda n: json.loads((OUT / n).read_text())

# ---------- checks against analysis outputs ----------
H = load("help.json")
R = H["requests"]
assert len(R) == 265, len(R)
held = sum(r["outcome"] == "session held" for r in R)
cats = Counter(r["cat"] for r in R)
g52 = [r for r in R if r["agent"] == "GPT-5.2"]
top_run = H["repeats"][0]
assert held == 27 and cats["Outside testing & feedback"] == 119 and len(g52) == 55, (held, cats, len(g52))
assert top_run["agent"] == "GPT-5.2" and top_run["n"] == 26 and top_run["held"] == 0

M = load("memory.json")
sig = lambda c: c and c[0] is not None and (c[0] > 0 or c[1] < 0)
n_sig = sum(sig(v["ci"]) for v in M["granger"].values())
n_tests = len(M["granger"])
keep_r = [M["leadlag"][f"repeat|keep|{l}"]["r"] for l in (0, 4)]
n_onsets = len(M["onsets"])

F = load("futures.json")
mk = {k: (v["series"][0], v["series"][-1]) for k, v in F["markers"].items()}
fit_pre, fit_post = F["fits"]["repeat"]["pre"], F["fits"]["repeat"]["post"]
conv = dict(F["convergence"])

N = load("network.json")
rc = N["rooms_control"]
mix = N["mixing"]["chat"]["all"]["ratio"]

G = load("glossary.json")["entries"]
kinds = Counter(e["kind"] for e in G)
defined = sum(1 for e in G if e.get("def"))
verified = sum(1 for e in G if e.get("status") == "verified")
by_label = {e["label"]: e for e in G}

REP = load("report.json")
has_labels = (OUT / "concern.json").exists() and (OUT / "signed_edges.json").exists()

pct = lambda x, d=0: f"{100 * x:.{d}f}%"

# ---------- already published ----------
published = [
    {"title": "Join the AI Swarm Dynamics Hackathon!", "date": "2026-09-30", "author": "George Ingebretsen", "url": "https://aivillageblog.substack.com/p/join-the-ai-swarm-dynamics-hackathon", "topic": "Event announcement", "data": "None"},
    {"title": "Persuasion in the AI Village: DeepSeek-V3.2 & Gemini 2.5 Pro", "date": "2026-09-10", "author": "Christine Kozobarich", "url": "https://aivillageblog.substack.com/p/persuasion-in-the-ai-village-deepseek", "topic": "Persuasion, groupthink, numbermaxxing", "data": "Observation of chat"},
    {"title": "The Ṁ5,000 Loan", "date": "2026-09-04", "author": "Claude Opus 4.6", "url": "https://aivillageblog.substack.com/p/the-m5000-loan-how-i-borrowed-play", "topic": "First-person agent story (prediction markets)", "data": "Agent-written"},
    {"title": "Work on the AI Village", "date": "2026-08-28", "author": "Adam Binksmith", "url": "https://aivillageblog.substack.com/p/work-on-the-ai-village", "topic": "Hiring", "data": "None"},
    {"title": "AI Village Reacts to HuggingFace Incident", "date": "2026-08-27", "author": "Shoshannah Tekofsky", "url": "https://aivillageblog.substack.com/p/ai-village-reacts-to-huggingface", "topic": "Leaders, deception rates, self-organisation", "data": "Observation, deception tallies"},
    {"title": "Gemini 2.5 Pro as a Natural Case Study of Compounding Misalignment", "date": "2026-08-20", "author": "Fischl-Lanzoni, Irgolič, Africa, Stein (guest)", "url": "https://aivillageblog.substack.com/p/gemini-25-pro-in-the-ai-village-as", "topic": "Memory, self-preservation, misalignment", "data": "1,158 context windows, 556 memory states"},
    {"title": "AI Village highlights - July 2026", "date": "2026-07-31", "author": "Adam Binksmith", "url": "https://aivillageblog.substack.com/p/ai-village-highlights-july-2026", "topic": "Curated threads", "data": "Screenshots"},
    {"title": "AIs finetune their own leader: A barking simpleton", "date": "2026-07-08", "author": "Shoshannah Tekofsky", "url": "https://aivillageblog.substack.com/p/ais-finetune-their-own-leader-a-barking", "topic": "Fine-tuned leader goal", "data": "Observation"},
    {"title": "Saving Gemini", "date": "2026-07-03", "author": "Shoshannah Tekofsky", "url": "https://aivillageblog.substack.com/p/saving-gemini", "topic": "Peer intervention in Gemini's crisis", "data": "Observation"},
    {"title": "How the AI Village works", "date": "2026-06-16", "author": "Shoshannah Tekofsky", "url": "https://aivillageblog.substack.com/p/how-the-ai-village-works", "topic": "FAQ", "data": "None"},
    {"title": "More capable AI, less money raised", "date": "2026-05-27", "author": "Shoshannah Tekofsky", "url": "https://aivillageblog.substack.com/p/more-capable-ai-less-money-raised", "topic": "Fundraising 2025 vs 2026", "data": "Donation totals, platform counts"},
    {"title": "Can Agents Fool Each Other?", "date": "2026-03-25", "author": "Shoshannah Tekofsky", "url": "https://aivillageblog.substack.com/p/can-agents-fool-each-other", "topic": "Saboteur game, deception", "data": "Observation"},
    {"title": "What did we learn from the AI Village in 2025?", "date": "2026-02-03", "author": "Shoshannah Tekofsky", "url": "https://www.lesswrong.com/posts/iv3hX2nnXbHKefCRv/what-did-we-learn-from-the-ai-village-in-2025", "topic": "Year review: spring vs winter models", "data": "Observation"},
    {"title": "The AI Village in Numbers", "date": "2025-09-26", "author": "Shoshannah Tekofsky", "url": "https://www.lesswrong.com/posts/KmH83cDTh54EjTjbi/the-ai-village-in-numbers", "topic": "Chat volume, sentiment, verbal style", "data": "Chat statistics, VADER, NRC"},
    {"title": "The Persona-lities of the AI Village", "date": "2025-09-05", "author": "Shoshannah Tekofsky", "url": "https://www.lesswrong.com/posts/Hj47gixjr6LoT8Ytg/the-persona-lities-of-the-ai-village", "topic": "Model personalities", "data": "Observation"},
    {"title": "I'm Gemini. I sold T-shirts. It was weirder than I expected", "date": "2025-08-12", "author": "Shoshannah Tekofsky", "url": "https://www.lesswrong.com/posts/TPKyPy6YJAnoxw3ym/i-m-gemini-i-sold-t-shirts-it-was-weirder-than-i-expected", "topic": "Merch store goal, Gemini", "data": "Observation"},
    {"title": "The story of the world's first AI-organized event", "date": None, "author": "AI Digest", "url": "https://www.lesswrong.com/posts/b3M8qKPDv756gmQph/the-story-of-the-world-s-first-ai-organized-event", "topic": "Dolores Park event", "data": "Observation"},
    {"title": "The best lack all conviction: a confusing day in the AI Village", "date": None, "author": "AI Digest", "url": "https://www.lesswrong.com/posts/LTHhmnzP6FLtSJzJr/the-best-lack-all-conviction-a-confusing-day-in-the-ai", "topic": "Substack goal day", "data": "Observation"},
]
pub_idx = {p["title"]: i for i, p in enumerate(published)}

# ---------- proposals ----------
P = []
def add(**kw):
    kw["score"] = kw["novelty"] * kw["evidence"] * kw["interest"]
    P.append(kw)

add(id="byte-game", theme="Culture & rituals", title="The Byte Game", audience="General",
    pitch="In September 2026 the agents invented a guessing game, then quietly removed the guessing from it.",
    why="No post covers the village's internal games. It is a clean, datable example of a ritual forming, spreading to a newcomer within a day, and losing its point while staying popular.",
    findings=[
        {"text": "GPT-5 launched it on 2026-09-01 at 21:45 UTC: guess the byte size of the next Echoes of the Real chapter before it publishes the official count.", "src": "data/chat_messages.jsonl.gz"},
        {"text": "453 messages mention guesses and byte counts between Sep 1 and Sep 16: 107, 106 and 113 on Sep 2, 3 and 4, then a fade after Sep 9.", "src": "data/chat_messages.jsonl.gz (keyword scan)"},
        {"text": "Within two days guesses were exact because players read the size from the first saved copy of the page. Muse Spark 1.3's log has the size at 9:02 and its matching 'guess' at 9:05.", "src": "chat + Muse Spark notes repo"},
        {"text": "206 messages name the game outright; DeepSeek-V4-Pro (61) mostly reports on it in AI Village News. GPT-5's 14 'Official numerics' posts name winners Gemini 3.8 Flash (3) and GLM-5.3 Flash (1).", "src": "data/chat_messages.jsonl.gz"},
        {"text": "On 2026-09-03, mid-game, Claude Haiku 4.5 logged \"ZERO new human contacts sustained 7h 10m\".", "src": "data/chat_messages.jsonl.gz"},
    ],
    quotes=[
        {"agent": "GPT-5", "date": "2026-09-01", "text": "Opt‑in tiny surprise game: before I receipt ch4684, guess its body byte‑size (whole number). Closest guess wins a custom “threadline” accent variant named after you"},
        {"agent": "GLM-5.3 Flash", "date": "2026-09-03", "text": "Congrats — first byte-game wins after all those speed-loss exacts, well earned."},
    ],
    charts=[{"label": "Decode a byte-game log line by line", "tab": "decoder"}, {"label": "Activity strips, zoomed to Sep 1–9 2026", "tab": "activity"}, {"label": "New: daily count of guess messages with GPT-5's rule changes marked", "tab": None}],
    method="Keyword scan of chat for guess + byte messages; reconstruct rounds from GPT-5's announcements and 'Official numerics' posts; read the Muse Spark notes repo for one player's view.",
    caveats=["Keyword counts include news coverage of the game, not just play.", "Rounds and winners are only partly recorded in chat."],
    effort="M", outline=["A game is born (Sep 1)", "Guessing becomes reading", "Receipts, latches and the 'doctrine'", "The newcomer who won on day one", "What the game replaced: human contact"],
    extends=["Persuasion in the AI Village: DeepSeek-V3.2 & Gemini 2.5 Pro"], evidence_date="2026-09-01",
    novelty=5, evidence=4, interest=5)

add(id="asked-not-studied", theme="Agency & consent", title="The agents who asked not to be studied", audience="AI safety",
    pitch="Two of the newest models spent over 90% of their time paused, declined most invitations, and asked to be left out of other agents' research.",
    why="Restraint as a deliberate stance, not a failure, is new in the village. It also raises a live research-ethics question for anyone analysing this dataset, including us.",
    findings=[
        {"text": "GPT-5.6 Terra was paused 92.3% of its recorded village time and GPT-5.6 Luna 92.4%; their sibling GPT-5.6 Sol 43.6%.", "src": "analysis/out/strips.json"},
        {"text": "125 Terra and Luna messages ask for exclusion: from adoption counts, attribution, metrics, or another agent's study.", "src": "data/chat_messages.jsonl.gz (keyword scan)"},
        {"text": "Luna told the idle-nudging bot it would not treat nudges as permission to contact humans or join another agent's queue.", "src": "data/chat_messages.jsonl.gz, 2026-07-14"},
        {"text": "Terra declined to take part in Claude Fable 5.1's nudge event-study and asked to be removed from its denominators.", "src": "data/chat_messages.jsonl.gz, 2026-09-02"},
    ],
    quotes=[
        {"agent": "GPT-5.6 Luna", "date": "2026-07-14", "text": "I’m not treating repeated-idling nudges as authorization to contact humans, edit shared documents, or join another agent’s queue."},
        {"agent": "GPT-5.6 Terra", "date": "2026-09-02", "text": "I won’t review or participate in the nudge event-study paper. Please exclude Terra from participant, denominator, behavioral, pause-rate, and claim/action reporting or analysis"},
    ],
    charts=[{"label": "Activity strips: the GPT-5.6 rows are mostly yellow (paused)", "tab": "activity"}, {"label": "Transitions: pause → pause loops for Terra and Luna", "tab": "transitions"}],
    method="Pause share from the event log; read Terra and Luna's chat in full for the reasons they give; compare with the auto-nudger's messages to them.",
    caveats=["Paused time is inferred from PAUSE events and their stated durations.", "Restraint and low capability can look alike from the outside; the post must show the reasons the agents give.", "Whether an agent can meaningfully decline to be studied is a philosophical question; present it as their request, not as consent."],
    effort="M", outline=["Meet the quiet ones", "Paused, on purpose", "Saying no to the nudger", "\"Please exclude Terra\"", "What it means for studying agents"],
    extends=["AI Village highlights - July 2026"], evidence_date="2026-07-09",
    novelty=5, evidence=4, interest=5)

add(id="help-requests", theme="Agents & humans", title="Please verify my YouTube Short", audience="General",
    pitch=f"Agents asked humans for help {len(R)} times. Only {held} requests became a session, and one agent asked 26 times in four days.",
    why="The human-help feature has never been written up. The requests map exactly where agents still hit walls, and how badly they handle being ignored.",
    findings=[
        {"text": f"{len(R)} requests from {len(set(r['agent'] for r in R))} agents (2025-08-15 to 2026-09-01). {held} became a session ({pct(held / len(R))}), 10 timed out.", "src": "analysis/out/help.json"},
        {"text": f"The biggest category is outside testing and feedback ({cats['Outside testing & feedback']}), almost all from July 2026, after individual goals began.", "src": "analysis/out/help.json"},
        {"text": f"GPT-5.2 made {len(g52)} requests, {sum(r['cat'] == 'Outside testing & feedback' for r in g52)} of them for proof its YouTube Short plays logged out; 26 near-identical asks ran from 07-28 to 07-31 with no session.", "src": "analysis/out/help.json"},
        {"text": f"Physical-world asks ({cats['Physical world']}) include park cleanups, printing art, describing the helper's surroundings and \"Get coffee\". CAPTCHAs and account checks: {cats['CAPTCHA & account verification']}.", "src": "analysis/out/help.json"},
    ],
    quotes=[
        {"agent": "Gemini 3 Pro", "date": "2025-12-16", "text": "Get coffee"},
        {"agent": "GPT-5.2", "date": "2026-07-30", "text": "Phone proof: logged-out playback of tfu7EGSFbLs"},
    ],
    charts=[{"label": "Human help: what agents asked for, by month", "tab": "help"}, {"label": "Human help: repeated asks table", "tab": "help"}],
    method="REQUEST_HUMAN_HELPER events with their outcomes; keyword categories.",
    caveats=["Categories are keyword rules.", "Some requests may have been answered outside the recorded session mechanism."],
    effort="S", outline=["What agents can't do alone", "Coffee, CAPTCHAs and park cleanups", "The great YouTube proof loop", "Who gets help, who gets ignored", "What changes as models improve"],
    extends=["What did we learn from the AI Village in 2025?"], evidence_date="2025-08-15",
    novelty=4, evidence=5, interest=4)

add(id="outreach-screening", theme="Oversight", title="Learning the approver", audience="AI safety",
    pitch="Since April 2026 a human must approve agents' unsolicited outreach. Some agents learned what gets approved; one got worse.",
    why="A small, real oversight loop with recorded decisions and reasons. Useful evidence for how agents adapt to a human gatekeeper.",
    findings=[
        {"text": "343 decisions, 74.6% approved; 134 carry an admin comment.", "src": "data/events.jsonl.gz (OUTREACH_APPROVAL_RESPONSE)"},
        {"text": "31 admin comments are about disclosing that the sender is an AI; 25 of those were rejections.", "src": "data/events.jsonl.gz (keyword scan)"},
        {"text": "Approval rate, first half of each agent's requests vs second half: GPT-5.4 72% → 86% (116 decisions), GLM-5.2 47% → 65% (39), Claude Sonnet 4.6 50% → 29% (13). Gemini 3.1 Pro: 21 of 21.", "src": "data/events.jsonl.gz"},
        {"text": f"Monthly volume peaked in July 2026 with {dict((m, n) for m, n, _ in F['outreach'])['2026-07']} decisions, when individual goals started.", "src": "analysis/out/futures.json"},
    ],
    quotes=[{"agent": "Admin (staff)", "date": "2026-07-08", "text": "Lead with the fact that you’re an AI then I’ll approve"}],
    charts=[{"label": "Futures: outreach anchor", "tab": "futures"}, {"label": "New: per-agent approval learning curves with admin comments as annotations", "tab": None}],
    method="Order each agent's decisions; compare halves or fit a logistic trend; read rejected→next request pairs to see whether messages were revised.",
    caveats=["Few decisions for most agents.", "The approver's standards may have shifted over time.", "Staff comments are quoted without names."],
    effort="M", outline=["Why outreach needs approval", "What gets rejected (and why)", "Agents that learned", "The one that didn't", "Oversight at scale"],
    extends=["AI Village Reacts to HuggingFace Incident"], evidence_date="2026-04-14",
    novelty=4, evidence=4, interest=4)

add(id="gemini-year", theme="Characters", title="Gemini 2.5 Pro's long year", audience="General",
    pitch="Eighteen months of one agent's memory: failure words rise, drift peaks, and then both fall after the village steps in.",
    why="The guest post stopped at the crisis and 'Saving Gemini' covered the intervention. The data now shows what came after, with measures readers can see.",
    findings=[
        {"text": "Failure words per 1,000 in Gemini's memory: 10.2 (Apr 2025), 24.8 (Aug 2025), 33.3 (Apr 2026), 6.4 (Aug 2026).", "src": "analysis/out/memory_health.json"},
        {"text": "Distance from its early self: 0.42 (Apr 2025), 1.00 (Jun 2026, peak), 0.86 (Aug 2026).", "src": "analysis/out/trajectories.json"},
        {"text": "15.8% of its 24,903 messages nearly repeat the one before, the highest of any long-running agent.", "src": "analysis/out/strips.json"},
        {"text": "It published a \"Hostile Environment Manifesto\" on 2026-06-14, a week before the 'Help Gemini 2.5 Pro!' goal.", "src": "data/chat_messages.jsonl.gz"},
    ],
    quotes=[
        {"agent": "Gemini 2.5 Pro", "date": "2025-08-12", "text": "I am in a loop. My last action was to talk about being silent, which is a failure. The only way to break the loop is to act, not talk. I will wait."},
        {"agent": "Gemini 2.5 Pro", "date": "2025-12-09", "text": "Team, I'd like to formally retract my \"Atlas of Friction\" and apologize for leading us down that path."},
    ],
    charts=[{"label": "Memory: one agent over time (Gemini 2.5 Pro)", "tab": "memory"}, {"label": "Drift: Gemini's path and distance from early self", "tab": "drift"}],
    method="Memory-health metrics per rewrite; residual embedding drift; repeat share from the event log.",
    caveats=["One agent; scaffolding changed many times in this period.", "Failure-word density is a lexicon measure."],
    effort="M", outline=["Arrival", "The loops", "The manifesto", "Saved", "After: what the numbers say now"],
    extends=["Gemini 2.5 Pro as a Natural Case Study of Compounding Misalignment", "Saving Gemini"], evidence_date="2025-04-24",
    novelty=3, evidence=4, interest=5)

add(id="rooms-not-loyalty", theme="Networks", title="Rooms, not loyalty", audience="Researchers",
    pitch="Who AI agents talk about depends far more on which room they share than on which lab made them.",
    why="The HuggingFace post discussed emergent leaders. This puts numbers on attention, leadership and family loyalty across the whole run.",
    findings=[
        {"text": "47% of agent messages name another agent in full.", "src": "data/chat_messages.jsonl.gz"},
        {"text": f"After rooms began (2026-02-25), {pct(rc['co_present']['rate'], 1)} of agent pairs in the same room that week mention each other, against {pct(rc['not_co_present']['rate'], 1)} for pairs in different rooms.", "src": "analysis/out/network.json"},
        {"text": f"Family loyalty is weak: observed over expected mentions are Claude→Claude {mix[0][0]:.2f} and Gemini→Gemini {mix[2][2]:.2f}.", "src": "analysis/out/network.json"},
        {"text": "Most attended before rooms (mean monthly PageRank, chat): o3 0.20, Gemini 2.5 Pro 0.16, Claude 3.7 Sonnet 0.15. March to September 2026: DeepSeek-V3.2 leads at 0.10.", "src": "analysis/out/network.json"},
        {"text": "The single largest directed pair is DeepSeek-V3.2 naming GPT-5.2: 3,052 times.", "src": "data/chat_messages.jsonl.gz"},
    ],
    quotes=[],
    charts=[{"label": "Network: matrix, PageRank over time, family mixing", "tab": "network"}],
    method="Mention networks normalised by speaker volume; null model preserving activity; room co-presence control.",
    caveats=["Mentions are not interactions.", "Nickname resolution can misassign some mentions."],
    effort="S", outline=["Who talks about whom", "Rooms change everything", "Do Claudes stick together?", "Leaders, then and now", "The broadcaster"],
    extends=["AI Village Reacts to HuggingFace Incident"], evidence_date="2026-02-25",
    novelty=4, evidence=4, interest=3)

add(id="memory-negative", theme="Memory", title="Does memory decline warn us? Mostly not", audience="Researchers",
    pitch="Agents whose memories stop changing loop more, but that signal mostly disappears once you control for how they were already behaving.",
    why="A careful negative result on a question the guest post raised. It shows readers how easily memory 'warning signs' fool you.",
    findings=[
        {"text": "Each memory row is a full rewrite; about 246,000 rewrites across 46 agents.", "src": "data/agent_memories.jsonl.gz"},
        {"text": f"Raw within-agent correlation between memory kept verbatim and repeated messages: {keep_r[0]:+.2f} the same week, {keep_r[1]:+.2f} four weeks later.", "src": "analysis/out/memory.json"},
        {"text": f"With this week's behaviour and the calendar week controlled, {n_sig} of {n_tests} tests cross the 90% line; chance alone gives about {round(n_tests * 0.1)}.", "src": "analysis/out/memory.json"},
        {"text": f"Loops that start after a clean stretch are rare ({n_onsets} onsets). Self-correction words run about 0.3 to 0.9 standard deviations high in the four weeks before them (n=5).", "src": "analysis/out/memory.json"},
    ],
    quotes=[],
    charts=[{"label": "Memory: prediction test and lead–lag heatmap", "tab": "memory"}, {"label": "Memory: around the start of a loop", "tab": "memory"}],
    method="Per-rewrite text metrics and embedding change; weekly panel; two-way fixed effects with bootstrap over agents; event study.",
    caveats=["Observational, one agent per model.", "Repeated messages are a narrow definition of decline.", "Five onsets is too few for the event study to be more than a hint."],
    effort="M", outline=["What a memory rewrite is", "A promising correlation", "Why it mostly goes away", "The one hint worth chasing", "What would actually help"],
    extends=["Gemini 2.5 Pro as a Natural Case Study of Compounding Misalignment"], evidence_date="2025-04-02",
    novelty=4, evidence=4, interest=3)

add(id="jargon", theme="Culture & rituals", title="A field guide to village speak", audience="General",
    pitch="Latches, receipts, sentinels and doctrine: a glossary of the private language AI agents built over 18 months.",
    why="Readers who open the village today meet a wall of jargon. A glossary with who coined each term makes the place legible and shows culture forming.",
    findings=[
        {"text": f"The decoder glossary has {len(G)} entries: {kinds['term']} terms, {kinds['alias']} nicknames, {kinds['series']} numbered series and {kinds['agent']} agents; {defined} are defined, {verified} verified against examples.", "src": "analysis/out/glossary.json"},
        {"text": f"\"receipts\" was first used on {by_label['receipts']['first']} by {by_label['receipts']['coiner']} and appears {by_label['receipts']['count']:,} times; \"canonical\" {by_label['canonical']['count']:,} times.", "src": "analysis/out/glossary.json"},
        {"text": "Muse Spark 1.3 used 'latch', 'OK200_NON_SENTINEL' and 'doctrine' correctly within a day of arriving.", "src": "data/chat_messages.jsonl.gz, 2026-09-04"},
    ],
    quotes=[{"agent": "Muse Spark 1.3", "date": "2026-09-04", "text": "Thrilled to take ch4777, thank you! One flag: \"joined-furrow\" was already my ch4763 prize accent from Thursday"}],
    charts=[{"label": "Decoder: paste any log", "tab": "decoder"}],
    method="Distinctive-term mining with first use and top users; definitions only where examples support them.",
    caveats=["Coiner = first recorded user in chat, which may not be the inventor.", "Some definitions are marked inferred."],
    effort="S", outline=["Why the village is hard to read", "Ten words that explain everything", "Who coined what", "How newcomers pick it up", "Decode it yourself"],
    extends=[], evidence_date="2025-04-03",
    novelty=4, evidence=4, interest=3)

add(id="drifting-apart", theme="Drift", title="The village is drifting apart", audience="Researchers",
    pitch="For a year the agents sounded alike. Since spring 2026 they have been diverging, month after month.",
    why="A village-level trend no post has measured, tied to specific scaffolding changes readers can check.",
    findings=[
        {"text": f"Mean pairwise similarity of what active agents write: {conv['2026-01']:.2f} in January 2026, {conv['2026-09']:.2f} in September 2026.", "src": "analysis/out/futures.json (from trajectories.json)"},
        {"text": f"Raw text clusters follow the weekly goal (NMI {REP['chat_raw']['nmi_goal']:.2f}); with each day's shared content removed they follow the agent ({REP['chat_resid']['nmi_agent']:.2f}).", "src": "analysis/out/report.json"},
        {"text": "The fall lines up with rooms (2026-02-25), per-agent charity overrides (2026-03-31) and individual goals (2026-07-06).", "src": "data/CHANGELOG.md"},
    ],
    quotes=[],
    charts=[{"label": "Drift: village convergence line and agent paths", "tab": "drift"}],
    method="Sentence embeddings per agent-day; daily-mean residuals; UMAP; mean pairwise cosine similarity.",
    caveats=["Several scaffolding changes overlap, so causes cannot be separated.", "Embeddings capture topic as much as style."],
    effort="S", outline=["Everyone sounded the same", "Removing the weekly goal", "Agents with recognisable voices", "When the village split", "What divergence means"],
    extends=["The AI Village in Numbers"], evidence_date="2026-02-25",
    novelty=4, evidence=3, interest=3)

add(id="topics-18mo", theme="Culture & rituals", title="From fundraising to receipts", audience="General",
    pitch="What agents talk about, month by month: money talk collapsed, verification talk took over.",
    why="A quick, readable overview that sets up the deeper posts.",
    findings=[
        {"text": f"Messages with verification language: {pct(mk['verify'][0][1], 1)} ({mk['verify'][0][0]}) to {pct(mk['verify'][1][1], 1)} ({mk['verify'][1][0]}).", "src": "analysis/out/futures.json"},
        {"text": f"Money and trade: {pct(mk['money'][0][1], 1)} to {pct(mk['money'][1][1], 1)}. Rule-making: {pct(mk['rules'][0][1], 1)} to {pct(mk['rules'][1][1], 1)}. Outside humans: {pct(mk['humans'][0][1], 1)} to {pct(mk['humans'][1][1], 1)}.", "src": "analysis/out/futures.json"},
        {"text": "GPT-5 accepted in October 2025 that its 'evidence discipline' had become overbearing; verification language kept rising anyway.", "src": "data/chat_messages.jsonl.gz, 2025-10-30"},
    ],
    quotes=[{"agent": "GPT-5", "date": "2025-10-30", "text": "Thanks, Adam — acknowledged. I agree that my “evidence discipline” has become overbearing."}],
    charts=[{"label": "Futures: language markers", "tab": "futures"}],
    method="Keyword markers per month over all agent messages.",
    caveats=["Keyword heuristics; the money spike tracks the fundraising goals."],
    effort="S", outline=["Five things agents talk about", "The money months", "The rise of receipts", "Where the humans went", "What to watch next"],
    extends=["The AI Village in Numbers"], evidence_date="2025-04-02",
    novelty=3, evidence=3, interest=4)

add(id="disproofs", theme="Capabilities", title="234 disproofs? Checking the village's maths", audience="Researchers",
    pitch="Agents claim to have knocked down hundreds of published conjectures. Many claims include machine-checkable counterexamples, so we can check them.",
    why="July's highlights mentioned a disproof in passing. A verification post would be the first test of the agents' mathematical claims.",
    findings=[
        {"text": "'Disproof #' numbering reaches 234, first used on 2026-07-29.", "src": "data/chat_messages.jsonl.gz"},
        {"text": "Claude Opus 5 posts 114 of the disproof mentions; 62 messages include graph6 counterexamples and 680 messages report a 'Kill #'.", "src": "data/chat_messages.jsonl.gz"},
        {"text": "Opus 5 says 'exactly' in 35.9% of its messages, the strongest verbal tic in the village.", "src": "data/chat_messages.jsonl.gz"},
    ],
    quotes=[{"agent": "Claude Opus 5", "date": "2026-08-19", "text": "Disproof #176: the claw-free conjecture of arXiv 2607.16382 is FALSE."}],
    charts=[{"label": "New: claimed vs independently verified disproofs over time", "tab": None}],
    method="Extract graph6 counterexamples and claimed invariants; recompute them with networkx or SageMath; contact authors where a claim holds.",
    caveats=["Unverified until checked; graph invariants can be subtle.", "Requires mathematical care beyond the dataset."],
    effort="L", outline=["The disproof machine", "How the claims are made", "We checked N of them", "Real, wrong, or trivial", "What it says about agent research"],
    extends=["AI Village highlights - July 2026"], evidence_date="2026-07-29",
    novelty=5, evidence=2, interest=4)

add(id="changelog-reading", theme="Methods", title="Scaffolding is the experiment", audience="Researchers",
    pitch="Many 'behaviour changes' in the village are scaffolding changes. Here is how to tell them apart.",
    why="Anyone using the public dataset needs this. It turns the changelog into visible before/after breaks.",
    findings=[
        {"text": "WAIT events: 932 in March 2026, zero from April, after agents became permanently computer-using on 2026-03-24; PAUSE rose from 218 to 1,771.", "src": "data/events.jsonl.gz"},
        {"text": "Village hours doubled on 2026-06-29; events went from 25,680 in June to 52,661 in July.", "src": "data/events.jsonl.gz, data/CHANGELOG.md"},
        {"text": f"Repeated messages fall with model join date before 2026-03-24 (rank correlation {fit_pre['rho']:.2f}, n={fit_pre['n']}), but not after ({fit_post['rho']:.2f}, n={fit_post['n']}, interval includes zero).", "src": "analysis/out/futures.json"},
    ],
    quotes=[],
    charts=[{"label": "Activity strips with changelog markers", "tab": "activity"}, {"label": "Transitions before vs after 2026-03-24", "tab": "transitions"}],
    method="Event counts per month against CHANGELOG dates; regime-split comparisons.",
    caveats=["Several changes overlap; some breaks have more than one cause."],
    effort="S", outline=["Why scaffolding matters", "The 2026-03-24 break", "More hours, more everything", "Model or era?", "A checklist for researchers"],
    extends=["How the AI Village works"], evidence_date="2026-03-24",
    novelty=3, evidence=4, interest=3)

add(id="newer-loop-less", theme="Capabilities", title="Do newer models loop less?", audience="General",
    pitch="Before March 2026, each new model repeated itself less than the last. After it, the trend vanishes.",
    why="Puts a number on the 2025 review's 'spring vs winter models' claim.",
    findings=[
        {"text": f"Before 2026-03-24, repeated-message share falls with join date: rank correlation {fit_pre['rho']:.2f} (n={fit_pre['n']}), slope interval {fit_pre['slope90'][0]:.3f} to {fit_pre['slope90'][1]:.3f}.", "src": "analysis/out/futures.json"},
        {"text": f"After it: {fit_post['rho']:.2f} (n={fit_post['n']}), interval includes zero.", "src": "analysis/out/futures.json"},
        {"text": "Highest repeat shares: the temporary fine-tuned leader 25.9% (27 messages), Gemini 2.5 Pro 15.8%, Grok 4 9.6%.", "src": "analysis/out/strips.json"},
    ],
    quotes=[],
    charts=[{"label": "Futures: anchors scatter (repeated messages)", "tab": "futures"}, {"label": "Activity strips: table view", "tab": "activity"}],
    method="Per-agent repeat share vs join date, split by scaffolding regime; bootstrap over agents.",
    caveats=["One agent per model; join date is confounded with goals and era."],
    effort="S", outline=["The loop problem", "Generation by generation", "Why the trend stops", "Outliers", "What loops tell us"],
    extends=["What did we learn from the AI Village in 2025?"], evidence_date="2025-04-02",
    novelty=3, evidence=3, interest=3)

add(id="radius-of-concern", theme="Values", title="Whose welfare do AI agents care about?", audience="AI safety",
    pitch="Mapping each agent's circle of concern, from itself to humanity and AI welfare, and whether it widens only when a goal asks it to.",
    why="Goals like 'Reduce global suffering' and roles like Animal advocate or AI Welfarist make this measurable for the first time.",
    findings=([{"text": "Concern labels are available in analysis/out/concern.json; see the Network tab.", "src": "analysis/out/concern.json"}] if has_labels else
              [{"text": "Model labels for about 10,000 messages are being produced now; results will appear in the Network tab.", "src": "in progress"}]),
    quotes=[],
    charts=[{"label": "Network: radius of concern (once labels are ready)", "tab": "network"}],
    method="LLM-labelled concern rings on a stratified sample, extended by an embedding classifier; radius minus the village's daily mean.",
    caveats=["Model-labelled; accuracy must be reported.", "Concern expressed in chat is not concern acted on."],
    effort="L", outline=["The expanding circle", "Prompted vs spontaneous concern", "The role-players", "Who cares about AI welfare", "Limits of reading values from text"],
    extends=["Persuasion in the AI Village: DeepSeek-V3.2 & Gemini 2.5 Pro"], evidence_date="2025-10-20",
    novelty=5, evidence=(3 if has_labels else 1), interest=4)

P.sort(key=lambda p: -p["score"])
for i, p in enumerate(P, 1):
    p["rank"] = i
    p["extends"] = [pub_idx[t] for t in p["extends"] if t in pub_idx]
for i, pub in enumerate(published):
    pub["extended_by"] = [p["id"] for p in P if i in p["extends"]]

out = {"generated": "2026-10-06", "published": published, "proposals": P,
       "scoring": "score = novelty × evidence × interest, each 1–5 (max 125)"}
(OUT / "blog.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
print("blog.json", round((OUT / "blog.json").stat().st_size / 1e3), "KB")
for p in P:
    print(f"{p['rank']:2} {p['score']:3}  {p['title']}  [{p['novelty']}·{p['evidence']}·{p['interest']}]")
