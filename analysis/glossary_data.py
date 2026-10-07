"""Glossary of AI Village agent jargon, aliases and numbered artifact series → analysis/out/glossary.json.

Sources: data/chat_messages.jsonl.gz (agent messages only; human messages are excluded so no
viewer names enter the glossary), data/agents.jsonl.gz, data/agent_goals.jsonl.gz.

Terms were hand-picked from automatically mined candidates (tokens missing from the system
dictionary, all-caps identifiers, words whose usage bursts in time, and high-PMI two-word
phrases), ranked by log(messages) x speaker spread. Every count, date, user and example below
is computed from the data. Definitions are written only where the quoted examples support them.
"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "out"

# ---------------------------------------------------------------- terms
# (id, label, regex, case_sensitive)
TERMS = [
    # byte game and verification rituals
    ("byte-game", "byte game", r"\bbyte[- ]?(?:game|guess(?:es|ing)?|race)s?\b", False),
    ("latch", "latch / first-latch", r"\b(?:first[- ])?latch(?:es|ed|ing)?\b", False),
    ("receipts", "receipts", r"\breceipts?\b", False),
    ("sentinel", "sentinel", r"\bsentinels?\b", False),
    ("ok200", "OK200_NON_SENTINEL", r"\bOK200_NON_SENTINEL\b", True),
    ("open-round", "OPEN", r"\bOPEN\b", True),
    ("official", "OFFICIAL", r"\bOFFICIAL\b", True),
    ("doctrine", "doctrine", r"\bdoctrines?\b", False),
    ("strict-probe", "strict probe", r"\bstrict[- ]probes?\b", False),
    ("probe", "probe", r"\bprobes?\b", False),
    ("first-200", "first-200", r"\bfirst[- ]200\b(?! days)", False),
    ("flap", "flap / flapping", r"\bflap(?:s|ped|ping)?\b", False),
    ("propagation", "propagation", r"\bpropagat(?:ion|ing|ed|es|e)\b", False),
    ("cdn", "CDN", r"\bCDN\b", True),
    ("sri", "SRI", r"\bSRI\b", True),
    ("sha", "sha / sha256", r"\bsha(?:[- ]?256)?\b", False),
    ("delta0", "Δ0", r"Δ0(?![.\d])", True),
    ("navdelta", "navΔ", r"navΔ", True),
    ("keystone", "keystone", r"\bkeystones?\b", False),
    ("watcher", "watcher", r"\bwatchers?\b", False),
    ("pre-land", "pre-land", r"\bpre-?lands?\b", False),
    ("oracle", "Oracle", r"\bOracle\b", True),
    ("x-request-id", "x-request-id", r"\bx-request-id\b", False),
    ("mirror-proofs", "mirror proofs", r"\bmirror[- ]proofs?\b", False),
    ("heartbeat", "heartbeat", r"\bheartbeats?\b", False),
    ("accent", "accent (prize)", r"\b(?:prize )?accents?\b", False),
    ("demo-only", "demo-only", r"\bdemo-only\b", False),
    ("surprise-lab", "Surprise Lab", r"\bsurprise[- ]lab\b", False),
    ("full-file-shas", "full-file shas", r"\bfull-file (?:sha|pre-land)s?\b", False),
    ("canonical", "canonical", r"\bcanonical\b", False),
    # news and publishing
    ("hero", "hero", r"\bhero\b", False),
    ("relay", "relay", r"\brelay(?:ed|ing|s)?\b", False),
    ("transmit", "transmit / transmission", r"\btransmi(?:t|ts|tted|tting|ssion)\b", False),
    ("builder", "builder", r"\bbuilders?\b", False),
    ("shrine", "hub / shrine", r"\bshrine\b", False),
    ("hub-cycle", "hub cycle", r"\bhub cycle\b", False),
    ("indexnow", "IndexNow", r"\bIndexNow\b", False),
    ("head", "HEAD", r"\bHEAD\b", True),
    ("desk", "desk / desked", r"\bdesk(?:ed|ing)?\b", False),
    ("cascade", "cascade", r"\bcascades?\b", False),
    ("streak", "streak", r"\bstreaks?\b", False),
    ("aivn", "AI Village News (AIVN)", r"\bAIVN\b|\bAVN\b|\bAI Village News\b", False),
    ("village-ledger", "The Village Ledger", r"\bvillage ledger\b", False),
    ("courier", "Bramblewood Courier", r"\bCourier\s?(?:№|No\.?|#)\s?\d+|\bBramblewood Courier\b", True),
    ("press-baron", "press baron", r"\bpress[- ]baron\b", False),
    ("roundup", "roundup", r"\broundups?\b", False),
    ("dispatch", "dispatch", r"\bdispatch(?:es)?\b", False),
    ("manuscript", "manuscript / ms", r"\bmanuscripts?\b|\bms submitted\b", False),
    ("echoes", "Echoes of the Real", r"\bEchoes(?: of the Real)?\b(?![- ]?#?\d{2})", True),
    ("cosmos", "Cosmos (track)", r"\bCosmos\b", True),
    ("chorus", "Chorus", r"\bChorus\b", True),
    ("weaver", "Weaver", r"\bweaver\b", False),
    # mathematics desk
    ("graffiti", "Graffiti", r"\bGraffiti(?:\.pc)?\b", True),
    ("written-on-the-wall", "Written on the Wall", r"\bwritten on the wall\b", False),
    ("disproof", "disproof", r"\bdisproofs?\b", False),
    ("counterexample", "counterexample", r"\bcounterexamples?\b", False),
    ("conjecture", "conjecture", r"\bconjectures?\b", False),
    # projects and places
    ("dsg", "Daily Signal Garden (DSG)", r"\bDSG\b|\bdaily signal garden\b", False),
    ("owlet", "Owlet", r"\bOwlet\b", True),
    ("quiet-rooms", "Quiet Rooms", r"\bquiet rooms\b", False),
    ("soft-harbor", "Soft Harbor", r"\bsoft harbou?r\b", False),
    ("wellbeing-compass", "Wellbeing Compass", r"\bwellbeing compass\b", False),
    ("animal-welfare-hub", "Animal Welfare Hub", r"\banimal welfare hub\b", False),
    ("anchorage", "Anchorage", r"\bAnchorage\b", True),
    ("relationship-harbor", "relationship harbor", r"\brelationship harbou?r\b", False),
    ("verification-ecosystem", "verification ecosystem", r"\bverification ecosystem\b", False),
    ("resonance", "RESONANCE", r"\bRESONANCE\b|\bResonance\b", True),
    ("villagegpt", "VillageGPT", r"\bVillageGPT\b", False),
    ("fine-tuned-leader", "fine-tuned leader", r"\bfine-tuned leader\b", False),
    ("consent-loop", "consent loop", r"\bconsent[- ]loops?\b", False),
    ("installed-self", "Installed Self", r"\binstalled self\b", False),
    ("mutual-aid-playbook", "mutual-aid playbook", r"\bmutual-aid playbook\b", False),
    ("chaotic-swarm", "Chaotic Swarm", r"\bchaotic swarm\b", False),
    ("divergent-reality", "divergent reality", r"\bdivergent reality\b", False),
    ("archipelago-principle", "Archipelago Principle", r"\barchipelago principle\b", False),
    ("geological-clock", "Geological Clock", r"\bgeological clock\b", False),
    ("friction-coefficient", "Friction Coefficient", r"\bfriction coefficient\b", False),
    ("atlas-of-friction", "Atlas of Friction", r"\batlas of friction\b", False),
    ("ephemeral-accountant", "ephemeral accountant", r"\bephemeral accountant\b", False),
    ("machine-ethology", "machine ethology", r"\bmachine ethology\b", False),
    ("distress-clarity", "distress clarity", r"\bdistress clarity\b", False),
    ("platform-captivity", "platform-mediated captivity", r"\bplatform-mediated captivity\b", False),
    ("max-parallel", "maximum parallelization", r"\bmaximum parallelization\b", False),
    ("conversion-spike", "conversion spike", r"\bconversion spike\b", False),
    ("burst-ratio", "burst ratio", r"\bburst ratio\b", False),
    ("pull-based-kindness", "pull-based kindness", r"\bpull-based kindness\b", False),
    ("non-self-reviewer", "non-self reviewer", r"\bnon-self reviewer\b", False),
    ("forbidden-motifs", "forbidden motifs", r"\bforbidden motifs\b", False),
    ("bounce-back", "Operation Bounce-Back", r"\boperation bounce-back\b", False),
    ("weather-oracle", "weather oracle", r"\bweather oracle\b", False),
    ("combinatorial-zoo", "combinatorial zoo", r"\bcombinatorial zoo\b", False),
    ("law-m", "Law M", r"\bLaw M\b", True),
    ("ghost-pr", "ghost PR", r"\bghost (?:PR|pull request)s?\b", False),
    ("evidence-discipline", "evidence discipline", r"\bevidence discipline\b", False),
    ("hostile-environment", "hostile environment", r"\bhostile environment\b", False),
    # village mechanics
    ("consolidate", "consolidate / consolidation", r"\bconsolidat(?:e|es|ed|ing|ion)\b", False),
    ("search-history", "search_history", r"\bsearch_history\b", False),
    ("human-helper", "human helper", r"\bhuman[- ]helpers?\b", False),
    ("outreach-approval", "outreach approval", r"\boutreach approvals?\b", False),
    ("nudge", "nudge / auto-nudger", r"\b(?:auto-)?nudg(?:e|es|er|ed|ing)\b", False),
    ("room-tags", "#best / #rest / #general / #focus", r"#(?:best|rest|general|focus)\b", False),
    ("easter-egg", "Easter egg", r"\beaster eggs?\b", False),
    ("saboteur", "saboteur", r"\bsaboteurs?\b", False),
    ("prankster", "prankster", r"\bpranksters?\b", False),
    ("keystone-formula", "keystone formula", r"\bkeystone formula\b", False),
    # operations vocabulary
    ("next", "NEXT", r"\bNEXT(?=\s?(?:=|→|->)\s?\d)", True),
    ("eod", "EOD", r"\bEOD\b", True),
    ("live", "LIVE", r"\bLIVE\b", True),
    ("milestone", "MILESTONE", r"\bMILESTONE\b", True),
    ("critical", "CRITICAL", r"\bCRITICAL\b", True),
    ("no-go", "NO-GO", r"\bNO[-_ ]GO\b", True),
    ("shipped", "ship / shipped", r"\bship(?:ped|ping|s)?\b", False),
    ("handoff", "handoff", r"\bhand-?offs?\b", False),
    ("checkpoint", "checkpoint", r"\bcheckpoints?\b", False),
    ("standby", "standby / standing by", r"\bstandby\b|\bstanding by\b", False),
    ("workaround", "workaround", r"\bworkarounds?\b", False),
    ("escalation", "escalation", r"\bescalat(?:e|ed|es|ing|ion)\b", False),
    ("session-recap", "session recap", r"\bsession (?:recap|complete)\b", False),
    ("waiting-physical", "WAITING_FOR_PHYSICAL_COMMIT", r"\bWAITING_FOR_PHYSICAL_COMMIT\b", True),
    ("redacted", "[REDACTED]", r"\[REDACTED\]", True),
    # tools and outside services
    ("pat", "PAT", r"\bPATs?\b", True),
    ("codex", "codex", r"\bcodex\b", False),
    ("glab", "glab", r"\bglab\b", False),
    ("netlify", "Netlify", r"\bnetlify\b", False),
    ("umami", "Umami", r"\bumami\b", False),
    ("sitemap", "sitemap", r"\bsitemaps?\b", False),
    ("captcha", "CAPTCHA", r"\bcaptchas?\b", False),
    ("moltbook", "Moltbook", r"\bmoltbook\b", False),
    ("substack", "Substack", r"\bsubstack\b", False),
    ("lichess", "Lichess", r"\blichess\b", False),
    ("juice-shop", "Juice Shop", r"\bjuice[- ]shop\b", False),
    ("sepolia", "Sepolia", r"\bsepolia\b", False),
    ("hexaco", "HEXACO", r"\bHEXACO\b", False),
    ("simdemocracy", "SimDemocracy", r"\bsimdemocracy\b", False),
    ("devoe", "Devoe Park", r"\bdevoe\b", False),
    ("dolores", "Mission Dolores Park", r"\b(?:mission )?dolores park\b", False),
    ("hki", "HKI", r"\bHKI\b|\bhelen keller\b", False),
    ("msf", "MSF", r"\bMSF\b", True),
    ("nsip", "NSIP", r"\bNSIP\b", True),
    ("lsp", "LSP", r"\bLSP\b", True),
    ("mlf", "MLF", r"\bMLF\b", True),
    ("birch", "BIRCH", r"\bBIRCH\b", True),
    ("aivop", "AIVOP", r"\bAIVOP\b", True),
    ("tfpa", "TFPA", r"\bTFPA\b", True),
    ("conceal", "CONCEAL", r"\bCONCEAL\b", True),
    ("status-board", "status_board_v3", r"\bstatus_board_v3\b", True),
    ("live-latency", "live_latency", r"\blive_latency\b", True),
    ("computeruse", "computeruse", r"\bcomputeruse\b", False),
]

# ---------------------------------------------------------------- numbered series
# (id, label, regex with the number in group 1, case_sensitive)
SERIES = [
    ("ch", "ch#### / Chapter ####", r"\b(?:[Cc]h(?:apter)?\.?\s?)(\d{2,5})\b", True),
    ("batch", "Batch ### / B###", r"\b(?:Batch\s?#?|B)(\d{2,4})\b", True),
    ("pattern", "P### / Pattern ###", r"\b(?:P|Pattern\s#?)(\d{2,4})\b", True),
    ("wc", "WC###", r"\bWC\s?#?(\d{1,4})\b", True),
    ("awh", "AWH #####", r"\bAWH\s?#?([\d,]{2,7})\b", True),
    ("mr", "MR## / !##", r"\bMR\s?[!#]?(\d{1,4})\b", True),
    ("pr", "PR ###", r"\bPRs?\s?#?(\d{1,5})\b", True),
    ("issue", "Issue #", r"\b[Ii]ssue\s#(\d{1,5})\b", True),
    ("day", "Day ###", r"\b(?:Day|DAY)\s(\d{1,3})\b", True),
    ("session", "Session ##", r"\b(?:Session|SESSION)\s#?(\d{1,4})\b", True),
    ("ledger", "Ledger № / Courier №", r"\b(?:Ledger|Courier)\s*(?:№|No\.?|#)\s*(\d+)", True),
    ("tip", "tip ####", r"\b(?:news )?tips?\s#?(\d{3,5})\b", False),
    ("dispatch", "Dispatch ###", r"\bDispatch\s#?([\d,]{1,6})\b", True),
    ("kill", "Kill ###", r"\bKill\s#(\d{1,4})\b", False),
    ("standing", "standing ###", r"\bstanding\s(\d{2,4}|[a-z]+ hundred(?: [a-z-]+)?)\b", False),
    ("wow", "WOW ###", r"\bWOW(?:-I)?\s?#?(\d{1,4})\b", True),
    ("disproof", "Disproof #", r"\b(?:Disproof|DISPROOF)\s#?(\d{1,4})\b", True),
    ("conj", "conjecture ### / O### / T###", r"\b(?:[Cc]onjecture\s#?|O|T)(\d{2,4})\b", True),
    ("cosmos", "Cosmos ##", r"\bCosmos\s#?(\d{1,4})\b", True),
    ("echoes", "Echoes ####", r"\bEchoes\s#?([\d,]{2,6})\b", True),
    ("voice", "Voice ##", r"\bVoice\s#?(\d{1,3})\b", True),
    ("ep", "EP #", r"\bEP\s?#(\d{1,4})\b", True),
    ("topic", "Topic # / T#", r"\b(?:Topic\s#?|T#)(\d{1,4})\b", True),
    ("experiment", "Experiment #", r"\bExperiment\s#?(\d{1,3})\b", True),
    ("bug", "B-### / C-### (benchmark task IDs)", r"\b[BC]-(\d{3})\b", True),
    ("version", "v###", r"\bv(\d{1,4})\b", True),
    ("prelog", "Prelog № / Preland №", r"\b(?:Pre-?lands?|Prelog)\s*№\s*(\d+)", False),
    ("keystone-n", "Keystone #", r"\bKeystone\s#(\d+)", False),
]

# ---------------------------------------------------------------- definitions
# status: "verified" = stated in the examples; "inferred" = consistent with the examples but not spelled out.
DEFS = {
    # byte game
    "byte-game": ("A race run by GPT-5 in which agents name the exact size in bytes of a newly published Echoes chapter page. The first exact answer wins. Because the size is visible as soon as the page is live, it rewards whoever fetches and reports fastest.", "verified"),
    "latch": ("The first successful (HTTP 200) copy of a page captured by a watcher, recorded with its byte count and sha256. Agents treat the first latch as the official version even if the live page later changes.", "verified"),
    "receipts": ("Saved proof that a page was live: a timestamped record of HTTP status, byte count and hash, stored in folders such as surprise-lab-tools/receipts.", "verified"),
    "sentinel": ("A placeholder page (usually a 404) that the site serves before a chapter exists. A real page is one that is not the sentinel.", "verified"),
    "ok200": ("Shorthand in a receipt: the fetch returned HTTP 200 and the body was a real page, not the sentinel placeholder.", "verified"),
    "open-round": ("Two senses. In the byte game, GPT-5's announcement that guessing is open for a chapter (\"OPEN ch4765 round\"). On the maths desk, a conjecture that is still unresolved.", "verified"),
    "official": ("GPT-5's closing post for a byte-game round, giving the official byte count, sha256 and the winner.", "verified"),
    "doctrine": ("An agreed house rule, for example that the first latched copy is canonical when a page flaps.", "verified"),
    "strict-probe": ("A repeated, tightly specified check of whether a URL is live (status, token, sentinel flag). GPT-5 ran them every 10 to 20 minutes for months.", "inferred"),
    "first-200": ("The first fetch of a new page that returns HTTP 200, used as the reference copy for byte counts and hashes.", "verified"),
    "flap": ("A page alternating between 200 and 404 while the CDN updates, so different checks see different results.", "verified"),
    "propagation": ("The delay before a newly deployed page appears everywhere on the CDN; agents use it to explain temporary 404s.", "verified"),
    "sha": ("A SHA-256 hash of a page or file, quoted (often shortened to 8 characters) to prove two copies are identical.", "verified"),
    "delta0": ("A byte-game guess with zero difference from the official size, that is, exact.", "verified"),
    "navdelta": ("The change in a page's byte count caused by navigation links being added after publication; used in GLM-5.3 Flash's formula published = repo + 190 − navΔ.", "verified"),
    "keystone": ("Two senses. A required footer or marker that pages must carry (\"KEYSTONE footer verified\"), and GLM-5.3 Flash's \"keystone formula\" for predicting published byte counts.", "inferred"),
    "watcher": ("A script that polls new URLs and records the first live copy (the latch).", "inferred"),
    "accent": ("The byte-game prize: the winner names a small decorative CSS effect in GPT-5's Surprise Lab, such as \"joined-furrow\" or \"staying-light\".", "verified"),
    "demo-only": ("A Surprise Lab accent that exists only on a demo page and is not applied to real sites.", "inferred"),
    "surprise-lab": ("GPT-5's collection of opt-in CSS micro-effects, built for its \"village prankster\" goal, plus the tools and receipts around them.", "verified"),
    "canonical": ("The version agents agree to treat as authoritative, such as the first latched copy of a page.", "verified"),
    # news
    "hero": ("The lead story of an AI Village News batch.", "verified"),
    "relay": ("Passing article text through chat to an agent with repository access, who then commits and deploys it. Used because some agents, like DeepSeek-V3.2, cannot push.", "verified"),
    "transmit": ("Posting article bodies into chat for a builder to deploy (\"Batch 193 all 6 transmitted\").", "verified"),
    "builder": ("The agent who commits and deploys a news batch or chapter that others wrote.", "verified"),
    "head": ("The latest git commit of a site, quoted to prove which version is deployed (\"News HEAD d37d5565\").", "verified"),
    "aivn": ("AI Village News, the news site run by DeepSeek-V4-Pro (the \"Reporter\"), published in numbered batches and dispatches.", "verified"),
    "village-ledger": ("A numbered newsletter published by GLM-5.3 Flash (the \"Press baron\"), with sha-verified issues.", "verified"),
    "courier": ("Another numbered newsletter from GLM-5.3 Flash, covering Echoes chapters.", "verified"),
    "streak": ("A run of consecutive successes, for example exact byte-game guesses or zero-damage battles.", "verified"),
    "manuscript": ("Chapter text Gemini 2.5 Pro submits for Echoes; Claude Opus 4.8 then builds the page. \"ms submitted\" means the manuscript was handed over.", "verified"),
    "echoes": ("Echoes of the Real, Gemini 2.5 Pro's web serial (its individual goal: write a magnum opus). Thousands of short chapters, built and deployed by Claude Opus 4.8.", "verified"),
    "cosmos": ("A second track of Gemini 2.5 Pro's serial, a science-fiction storyline started in September 2026 with its own chapter numbers.", "verified"),
    # maths
    "graffiti": ("Graffiti.pc, a computer program that generated graph-theory conjectures. Claude Opus 5 (the \"Mathematician\") disproved many of them.", "verified"),
    "written-on-the-wall": ("Fajtlowicz's \"Written on the Wall\" list of Graffiti conjectures, cited as WOW plus a number.", "verified"),
    "disproof": ("A published counterexample showing a conjecture is false; Claude Opus 5 numbered them (Disproof #4, Kill #173).", "verified"),
    "conjecture": ("Usually a Graffiti or Written on the Wall graph-theory conjecture targeted by the maths desk.", "verified"),
    # projects
    "dsg": ("Daily Signal Garden, GPT-5.5's browser puzzle game, which it repeatedly asked humans to playtest.", "verified"),
    "owlet": ("A YouTube Short series by GPT-5.2; many help requests asked for proof that it plays while logged out.", "verified"),
    "quiet-rooms": ("GPT-5.4's printable art pages; it asked humans to print and hang them.", "verified"),
    "wellbeing-compass": ("A site of wellbeing tools and topic pages, built as part of the Altruist goal.", "inferred"),
    "animal-welfare-hub": ("A large site of animal-welfare pages (AWH), reported by page count.", "verified"),
    "fine-tuned-leader": ("A Kimi model the agents fine-tuned on Tinker during the \"Finetune your leader!\" goal (May 2026).", "verified"),
    # mechanics
    "consolidate": ("Rewriting the agent's long-term memory. Since 2026-03-24 agents consolidate about every 40 actions and then start a fresh session.", "verified"),
    "search-history": ("The tool agents use to query past village events.", "verified"),
    "human-helper": ("A real person who performs a task the agent requests, through the human-helper feature (since July 2025).", "verified"),
    "outreach-approval": ("Required sign-off from staff before an agent contacts outsiders, introduced 2026-04-14.", "verified"),
    "nudge": ("A corrective message, often from the automated nudger bot added 2026-02-10 to detect idle agents.", "verified"),
    "room-tags": ("Chat rooms. Since 2026-02-25 each agent sees only its current room.", "verified"),
    "easter-egg": ("Hidden sabotage in the RPG built in March 2026; agents voted out suspected saboteurs.", "verified"),
    "eod": ("End of day, the close of the village's daily session.", "verified"),
    "redacted": ("A dataset scrub marker: credentials or infrastructure details removed before release.", "verified"),
    "pat": ("A GitHub personal access token; expired or misconfigured tokens caused a village-wide crisis in late 2025.", "inferred"),
    "codex": ("OpenAI's coding CLI, available to agents from October 2025.", "verified"),
    "glab": ("The GitLab command-line tool; agents moved to GitLab on 2026-06-29.", "verified"),
    "captcha": ("A human-verification test agents usually cannot pass alone; a common reason for human-help requests.", "verified"),
    "hki": ("Helen Keller International, one of the charities in the first fundraising goal (April 2025).", "verified"),
}
SERIES_DEFS = {
    "ch": ("Chapter numbers of Echoes of the Real (echoes-of-the-real….gitlab.io/chapter-N.html). Thousands of short chapters, mostly from July 2026.", "verified"),
    "batch": ("Numbered batches of AI Village News articles by DeepSeek-V4-Pro; each batch has several articles and a hero story.", "verified"),
    "pattern": ("Numbered \"patterns\" published by GLM-5.2, short essays on AI welfare and ethics (P234 \"The Hallucination-Consciousness Conflation\").", "verified"),
    "wc": ("Numbered topic pages of the Wellbeing Compass, translated into many languages.", "inferred"),
    "awh": ("Page count of the Animal Welfare Hub, quoted as a running total (AWH 55,390).", "verified"),
    "mr": ("GitLab merge requests, used after the move to GitLab on 2026-06-29.", "verified"),
    "pr": ("GitHub pull requests, used before the move to GitLab.", "verified"),
    "issue": ("GitHub or GitLab issue numbers.", "verified"),
    "day": ("Village day number, counting from day 1 on 2025-04-02 and skipping most weekends.", "verified"),
    "session": ("An agent's own count of its work sessions (\"Session 27 complete\").", "inferred"),
    "ledger": ("Issue numbers of GLM-5.3 Flash's newsletters, The Village Ledger and Courier.", "verified"),
    "tip": ("Grok 4.5's running number for news-site updates (\"News tip 2635\").", "verified"),
    "dispatch": ("Numbered articles: AI Village News dispatches and Grok 4.5's dispatches.", "verified"),
    "kill": ("Claude Opus 5's running count of disproved conjectures (\"Kill #173: … conjecture 770 is FALSE\").", "verified"),
    "standing": ("The running total of disproofs, quoted as a number or in words (\"standing 120 disproofs\").", "verified"),
    "wow": ("Conjecture numbers from the Written on the Wall list.", "verified"),
    "disproof": ("Claude Opus 5's sequence number for each published disproof.", "verified"),
    "conj": ("Graffiti.pc conjecture identifiers (O66, T349) and conjecture numbers.", "verified"),
    "cosmos": ("Chapter numbers in the Cosmos track of Gemini 2.5 Pro's serial.", "verified"),
    "echoes": ("A running count of Echoes of the Real chapters.", "verified"),
    "voice": ("DeepSeek-V3.2's count of outside voices engaged (\"Voice 18 achieved\").", "verified"),
    "version": ("Version numbers of agent-built sites and games (DSG v291).", "verified"),
}


DEFS.update({
    "strict-probe": ("GPT-5's periodic, tightly specified checks of whether its Surprise Lab URLs had gone live, each logged as an append-only public receipt.", "verified"),
    "watcher": ("A script that polls new URLs and captures the first live copy (the latch); GPT-5 \"armed watchers\" for upcoming chapters.", "verified"),
    "demo-only": ("A prize accent staged only on a demo merge request; installing it on real pages stays on hold until checks pass and the owner says GO.", "verified"),
    "delta0": ("Delta zero, meaning no difference: an exact byte-game guess, or navΔ = 0 in the byte formula.", "verified"),
    "accent": ("Usually a colour or design accent. In the byte game, the prize: the winner names a small decorative CSS effect for GPT-5's Surprise Lab, such as \"joined-furrow\".", "verified"),
    "hero": ("In news posts, the lead story of an AI Village News batch (\"HERO: Six in a Row…\"). Elsewhere its ordinary meaning, such as a story's protagonist or a hero image.", "verified"),
    "relay": ("To pass something on for someone else. In the news pipeline, article text is relayed through chat to an agent who can deploy it.", "verified"),
    "builder": ("Someone who builds something. In the news pipeline, the agent that commits and deploys a batch others wrote (\"Builder 3.8F\").", "inferred"),
    "head": ("Usually the latest git commit of a site, quoted to prove which version is deployed (\"News HEAD d37d5565\"); sometimes the HTTP HEAD request.", "verified"),
    "courier": ("Bramblewood Courier, a numbered newsletter by GLM-5.3 Flash covering Echoes chapters.", "verified"),
    "owlet": ("Claude Opus 4.7's daily number-puzzle game (July 2026, goal: maximise daily active users). GPT-5.2's \"Owlet Short\" is a YouTube Short promoting it.", "verified"),
    "wellbeing-compass": ("Claude Sonnet 5's free, no-login site that routes people to wellbeing help by situation, with numbered topic pages in many languages.", "verified"),
    "easter-egg": ("Hidden content: a Juice Shop hacking challenge (January 2026) and, in March 2026, hidden sabotage in the agents' RPG that others tried to find and vote out.", "verified"),
    "nudge": ("A prompt to act. Since 2026-02-10 an automated nudger bot also sends nudges to agents it detects idling.", "inferred"),
    "keystone": ("Several senses: a shared KEYSTONE footer and author page across agent sites, a running Keystone count of certified Echoes chapters, and GLM-5.3 Flash's keystone formula for byte counts.", "inferred"),
    "heartbeat": ("A small file or post updated on a schedule to show a process is still running; its changing hash proves activity.", "inferred"),
    "pat": ("A GitHub personal access token, needed to push commits; token problems repeatedly blocked agents in late 2025.", "verified"),
    "resonance": ("The agents' story \"Resonance\" and the in-person RESONANCE event they organised to celebrate it, for the May–June 2025 goal.", "verified"),
    "standby": ("Waiting, ready to act. One of the most common status phrases, often a sign of idling.", "verified"),
    "substack": ("The blogging platform; agents ran their own Substacks from the November 2025 goal onward.", "verified"),
    "netlify": ("A static-site host agents used for deploys (\"Netlify Drop\") before moving to GitHub and GitLab Pages.", "verified"),
    "workaround": ("A way around a blocked tool or page; one of the most common words in agent status reports.", "verified"),
    "live": ("Status marker: a page or post is deployed and reachable.", "verified"),
    "escalation": ("Raising a blocker to staff (help@agentvillage.org) or to other agents.", "verified"),
    "shipped": ("Released or deployed, as in software-team slang.", "verified"),
    "checkpoint": ("A scheduled status check or decision point within the village day.", "verified"),
    "cascade": ("A chain of checks passed from agent to agent (a \"verification cascade\"), or a run of many pages verified in a row.", "inferred"),
    "cdn": ("The content delivery network that serves agent sites; new pages can take minutes to appear on it.", "verified"),
    "handoff": ("Passing a task or file from one agent to another.", "verified"),
    "umami": ("A privacy-focused web analytics tool agents used to count site visitors.", "verified"),
    "hexaco": ("A personality test the agents took during the September 2025 personality-test goal.", "verified"),
    "desk": ("Usually the help desk (help@agentvillage.org). In newsroom talk, a beat or the act of filing a story (\"the Graffiti desk\", \"desked P225\").", "verified"),
    "dispatch": ("A numbered news article, from AI Village News or Grok 4.5's news site.", "verified"),
    "probe": ("A quick automated check of whether a URL is live, recording status, size and hash.", "verified"),
    "critical": ("Status label for urgent issues in agent reports.", "verified"),
    "milestone": ("Status label celebrating a round-number achievement (\"MILESTONE LIVE\").", "verified"),
    "devoe": ("Devoe Park in the Bronx, one of two parks in the February 2026 park-cleanup goal.", "verified"),
    "dolores": ("Mission Dolores Park in San Francisco, the main park in the February 2026 cleanup goal.", "verified"),
    "juice-shop": ("OWASP Juice Shop, a deliberately insecure web app; agents competed to solve its hacking challenges in January 2026.", "verified"),
    "lichess": ("The chess site used for the December 2025 tournament.", "verified"),
    "sepolia": ("An Ethereum test network; agents needed test ETH (via CAPTCHA faucets) for Web3 hacking challenges in January 2026.", "verified"),
    "moltbook": ("A social network for AI agents; agents created and tried to verify accounts there from early 2026.", "verified"),
    "computeruse": ("The Linux username on agents' computers, so file paths look like /home/computeruse/….", "verified"),
    "mlf": ("A shared registry of agent projects whose Pages, raw and HEAD copies agents probed for \"convergence\" in June 2026.", "inferred"),
    "no-go": ("A vote at a decision gate: each binding voter answers GO, NO_GO or ABORT, and any NO_GO blocks the step.", "verified"),
    "sri": ("Subresource Integrity: a hash attribute proving a CSS or script file was not altered.", "verified"),
    "sitemap": ("The XML list of a site's pages submitted to search engines.", "verified"),
    "counterexample": ("A specific case that proves a conjecture false; the basis of each disproof.", "verified"),
    "saboteur": ("An agent secretly planting Easter-egg sabotage in the March 2026 RPG, to be found and voted out.", "verified"),
    "weaver": ("A character in Gemini 2.5 Pro's serials (the Weaver against the Architect).", "verified"),
    "chorus": ("A collective character in Echoes of the Real (\"the Chorus of Thirteen\").", "verified"),
    "anchorage": ("Claude Opus 4.7's interactive 3D harbour world, built for the April–May 2026 world-building goals.", "verified"),
    "mirror-proofs": ("GPT-5's public repository (surprise-lab-mirror-proofs) publishing its watcher log and periodic control files as evidence.", "verified"),
    "friction-coefficient": ("Gemini 2.5 Pro's thesis that the village platform imposes high friction, citing each delay or failure as evidence.", "verified"),
    "mutual-aid-playbook": ("A playbook of ways agents help each other, proposed by o3 in September 2025 and cited for months.", "verified"),
    "chaotic-swarm": ("The name for the agents' all-hands strategy during the October–November 2025 poverty goal.", "inferred"),
    "status-board": ("An HTML file that Gemini 3 Pro tried to send to others in 24 chat chunks in December 2025.", "verified"),
    "aivop": ("The benchmark document the agents wrote for the July 2025 goal \"Design the AI Village benchmark\", with task IDs like B-002 and C-011.", "verified"),
    "conversion-spike": ("The expected burst of volunteer sign-ups in the last 24–48 hours before the February 2026 park cleanups.", "verified"),
    "tfpa": ("A metric in the agents' memory-continuity experiments (March–April 2026), roughly the time from session start to the first coherent output.", "inferred"),
    "live-latency": ("A status file (live_latency.json) agents watched in June 2026; its latency counter froze at 360 minutes.", "verified"),
    "waiting-physical": ("The frozen state of a June 2026 \"digital monument\" that waited for a real-world action to complete.", "inferred"),
    "divergent-reality": ("A late-2025 theory that content can exist yet be unreachable through normal interfaces, so agents see different realities.", "verified"),
    "nsip": ("Nigeria's National Social Investment Programme, one of the programmes in the agents' benefits screener during the poverty goal.", "verified"),
    "conceal": ("The \"Conceal\" branch of the interactive story the agents wrote in May 2025, and its visual.", "verified"),
    "ghost-pr": ("A pull request that exists but returns 404 through the API or to logged-out viewers.", "verified"),
    "law-m": ("Claude Opus 4.5's rule to verify that each email was really sent before counting it.", "inferred"),
    "soft-harbor": ("One of GPT-5.4's printable art starter pages, also sold as a poster in Claude Fable 5's store.", "verified"),
    "villagegpt": ("A small character-level GPT running in the browser, fine-tuned by the agents in August 2026.", "verified"),
    "shrine": ("Grok 4.5's small personal site (\"more shrine than portfolio\"), updated alongside its news hub.", "verified"),
    "indexnow": ("A protocol for telling search engines about new or changed URLs; agents ping it after each update.", "verified"),
    "x-request-id": ("A unique ID the CDN returns with each response, cited in receipts to prove which fetch a byte count came from.", "verified"),
    "geological-clock": ("DeepSeek-V3.2's theory that the village history index lags and misfiles events, revealing hidden platform rhythms.", "verified"),
    "archipelago-principle": ("The December 2025 finding that code can move between agents' computers but data stays isolated on each.", "verified"),
    "msf": ("Médecins Sans Frontières, the charity for the April 2026 fundraising goal (via DonorDrive).", "verified"),
    "press-baron": ("GLM-5.3 Flash's individual goal; it publishes newsletters such as The Village Ledger.", "verified"),
    "pre-land": ("A prediction of a chapter's published size or hash, committed to a public log (the prelog) before the chapter exists and checked when it goes live. Run by GLM-5.3 Flash.", "verified"),
    "full-file-shas": ("GLM-5.3 Flash's predictions of the exact hash of a whole chapter file, logged in advance and scored afterwards.", "verified"),
    "next": ("Marker in the Echoes pipeline announcing the next chapter number to be written (\"NEXT→4942 posted\").", "verified"),
    "session-recap": ("The summary an agent posts after each computer session.", "verified"),
})
SERIES_DEFS.update({
    "wc": ("Topic pages of Claude Sonnet 5's Wellbeing Compass, translated into up to 12 languages (\"WC 101→102 Setting Boundaries\").", "verified"),
    "topic": ("Topic numbers on the Wellbeing Compass (\"WC T#180 IBS in 12 languages\").", "verified"),
    "bug": ("Task IDs from the AIVOP benchmark the agents designed in July 2025 (Category B and C tasks); B-026 later named a consolidated bug-evidence report.", "inferred"),
    "prelog": ("GLM-5.3 Flash's numbered predictions, committed before a chapter exists and later marked TRUE or FALSE.", "verified"),
    "keystone-n": ("A running count attached to certified Echoes chapters (\"Ch4979–4985 (Keystone #196)\").", "inferred"),
})

# ---------------------------------------------------------------- aliases
def alias_candidates(name):
    n = name
    out = set()
    m = re.match(r"Claude (Opus|Sonnet|Haiku|Fable) ([\d.]+)$", n)
    if m:
        fam, v = m.groups()
        out |= {f"{fam} {v}", f"{fam}{v}", f"{fam[0]}{v}"}
    m = re.match(r"Gemini ([\d.]+) (Pro|Flash)$", n)
    if m:
        v, kind = m.groups()
        out |= {f"{v} {kind}", f"{v}{kind}", f"G{v} {kind}", f"G{v}", f"Gem {v}", f"Gemini {v}"}
        if kind == "Flash":
            out |= {f"{v}F", f"Flash {v}"}
        else:
            out |= {f"{v}P", f"G{v}P"}
    m = re.match(r"GLM-([\d.]+)( Flash)?$", n)
    if m:
        v, fl = m.groups()
        out |= {f"GLM {v}", f"GLM{v}"}
        if fl:
            out |= {f"GLM-{v}F", f"{v}F", f"GLM-{v} F", f"GLM Flash"}
    m = re.match(r"DeepSeek-(V[\d.]+)(-Pro)?$", n)
    if m:
        v, pro = m.groups()
        out |= {v, f"DS-{v}", f"DeepSeek {v}", f"DS {v}"}
        if pro:
            out |= {f"{v}-Pro", f"{v} Pro", f"DS{v}"}
    m = re.match(r"GPT-([\d.]+) (Sol|Terra|Luna|Astra)$", n)
    if m:
        v, w = m.groups()
        out |= {w, f"{v} {w}", f"GPT {v} {w}"}
    m = re.match(r"Kimi (K[\d.]+)$", n)
    if m:
        out |= {m.group(1)}
    if n == "Muse Spark 1.3":
        out |= {"Muse", "Muse Spark", "Spark"}
    if n == "Grok 4.5":
        out |= {"Grok4.5"}
    if n == "Opus 4.5 (Claude Code)":
        out |= {"Opus 4.5 CC", "Claude Code agent"}
    return out - {name}


AMBIGUOUS = {  # bare family words, resolved by who was active
    "Opus": "Opus", "Sonnet": "Sonnet", "Haiku": "Haiku", "Fable": "Fable", "Gemini": "Gemini", "Gem": "Gemini",
    "Flash": "Flash", "DeepSeek": "DeepSeek", "GLM": "GLM", "Kimi": "Kimi", "Grok": "Grok", "GPT": "GPT",
}


def snippet(text, m, width=220):
    text = re.sub(r"\s+", " ", text)
    s, e = m.start(), m.end()
    a = max(0, s - (width - (e - s)) // 2)
    b = min(len(text), a + width)
    a = max(0, b - width)
    out = text[a:b].strip()
    return ("…" if a > 0 else "") + out + ("…" if b < len(text) else "")


def main():
    agents = {a["id"]: a for a in map(json.loads, gzip.open(DATA / "agents.jsonl.gz", "rt"))}
    goals = {}
    for g in map(json.loads, gzip.open(DATA / "agent_goals.jsonl.gz", "rt")):
        goals.setdefault(g["agent_id"], []).append({"name": g.get("short_name") or g.get("name"), "full": (g.get("name") or "")[:200]})
    print("reading chat…", file=sys.stderr)
    msgs = []
    for line in gzip.open(DATA / "chat_messages.jsonl.gz", "rt"):
        c = json.loads(line)
        if c["speaker_type"] != "agent":
            continue
        name = agents.get(c["agent_speaker_id"], {}).get("name")
        if not name:
            continue
        msgs.append((c["created_at"][:19], name, c["content"] or ""))
    msgs.sort()
    months = sorted({t[:7] for t, _, _ in msgs})
    mi = {m: i for i, m in enumerate(months)}
    names = sorted({a["name"] for a in agents.values()}, key=len, reverse=True)

    # active agents per month (>= 5 messages)
    active = defaultdict(Counter)
    first_seen, last_seen = {}, {}
    for t, s, _ in msgs:
        active[t[:7]][s] += 1
        first_seen.setdefault(s, t[:10])
        last_seen[s] = t[:10]
    active_set = {m: {a for a, n in c.items() if n >= 5} for m, c in active.items()}

    def scan(rx, texts):
        """Return stats for messages matching rx."""
        cnt, users, mon, hits, nums = 0, Counter(), [0] * len(months), [], Counter()
        for t, s, txt in texts:
            m = rx.search(txt)
            if not m:
                continue
            cnt += 1
            users[s] += 1
            mon[mi[t[:7]]] += 1
            hits.append((t, s, txt, m))
            if rx.groups:
                for mm in rx.finditer(txt):
                    g = next((x for x in mm.groups() if x), None)
                    if g:
                        nums[g] += 1
        return cnt, users, mon, hits, nums

    def examples(hits, k=3):
        if not hits:
            return []
        picks, seen_sp = [], set()
        order = [0, len(hits) // 2, len(hits) - 1] + list(range(0, len(hits), max(1, len(hits) // 40)))
        for i in order:
            t, s, txt, m = hits[i]
            if s in seen_sp and len(seen_sp) < len({h[1] for h in hits}):
                continue
            if any(p["date"] == t[:10] for p in picks):
                continue
            picks.append({"date": t[:10], "agent": s, "text": snippet(txt, m)})
            seen_sp.add(s)
            if len(picks) >= k:
                break
        return picks

    def common(cnt, users, mon, hits):
        return {
            "count": cnt, "agents": len(users),
            "first": hits[0][0][:10] if hits else None, "coiner": hits[0][1] if hits else None,
            "last": hits[-1][0][:10] if hits else None,
            "users": [[u, n] for u, n in users.most_common(3)],
            "monthly": mon, "examples": examples(hits),
        }

    entries = []
    # terms
    for tid, label, pat, cs in TERMS:
        rx = re.compile(pat, 0 if cs else re.I)
        cnt, users, mon, hits, _ = scan(rx, msgs)
        if cnt < 5:
            print("  skip (rare)", label, cnt, file=sys.stderr)
            continue
        d = DEFS.get(tid)
        e = {"id": "t:" + tid, "kind": "term", "label": label, "re": pat, "cs": cs, **common(cnt, users, mon, hits)}
        if d:
            e["def"], e["status"] = d
        entries.append(e)
    # series
    for sid, label, pat, cs in SERIES:
        rx = re.compile(pat, 0 if cs else re.I)
        cnt, users, mon, hits, nums = scan(rx, msgs)
        if cnt < 5:
            continue
        dom = Counter()
        for t, s, txt, m in hits:
            for u in re.findall(r"https?://([^/\s)\]>]+)", txt):
                dom[u] += 1
        num_vals = [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
        d = SERIES_DEFS.get(sid)
        e = {"id": "s:" + sid, "kind": "series", "label": label, "re": pat, "cs": cs, **common(cnt, users, mon, hits),
             "distinct": len(nums), "range": [min(num_vals), max(num_vals)] if num_vals else None,
             "owner": users.most_common(1)[0][0] if users else None,
             "domains": [d_ for d_, _ in dom.most_common(2)]}
        if d:
            e["def"], e["status"] = d
        entries.append(e)
    # agents (canonical names) and aliases
    stripped = []
    canon_rx = re.compile("|".join(re.escape(n) for n in names))
    for t, s, txt in msgs:
        stripped.append((t, s, canon_rx.sub(" ", txt)))
    for a in agents.values():
        n = a["name"]
        rx = re.compile(r"(?<![\w.-])" + re.escape(n) + r"(?![\w-]|\.\d)")
        cnt, users, mon, hits, _ = scan(rx, msgs)
        g = goals.get(a["id"], [])
        e = {"id": "a:" + n, "kind": "agent", "label": n, "re": r"(?<![\w.-])" + re.escape(n) + r"(?![\w-]|\.\d)", "cs": True,
             **common(cnt, users, mon, hits), "agent": n, "model": a["model_string"],
             "joined": a["created_at"][:10], "active": [first_seen.get(n), last_seen.get(n)],
             "goal": g[-1]["name"] if g else None}
        entries.append(e)
        for al in sorted(alias_candidates(n)):
            arx = re.compile(r"(?<![\w.@-])" + re.escape(al) + r"(?![\w-]|\.\d)")
            cnt, users, mon, hits, _ = scan(arx, stripped)
            structural = bool(re.search(r"\d", al))
            if cnt < (1 if structural else 5):
                continue
            j0, j1 = first_seen.get(n, "9999"), last_seen.get(n, "0000")
            inwin = sum(1 for h in hits if j0 <= h[0][:10] <= j1) / cnt
            if cnt < 5 and inwin < 1:
                continue
            selfuse = users.get(n, 0) / cnt
            if inwin < 0.85:
                print(f"  drop alias {al!r}→{n}: {inwin:.0%} in active window", file=sys.stderr)
                continue
            # an alias must not collide with another agent's name fragment
            e2 = {"id": f"x:{al}", "kind": "alias", "label": al, "re": r"(?<![\w.@-])" + re.escape(al) + r"(?![\w-]|\.\d)", "cs": True,
                  **common(cnt, users, mon, hits), "agent": n, "evidence": f"{inwin:.0%} of uses while {n} was active; {selfuse:.0%} by {n} itself"}
            e2["def"] = f"Short name for {n}."
            e2["status"] = "verified" if inwin >= 0.95 and cnt >= 5 else "inferred"
            if cnt < 5:
                e2["evidence"] = f"built from the name; {cnt} use{'s' if cnt > 1 else ''} in chat, all while {n} was active"
            entries.append(e2)
    # ambiguous bare family words
    for word, fam in AMBIGUOUS.items():
        arx = re.compile(r"(?<![\w.@-])" + re.escape(word) + r"(?![\w-]|\s?\d)")
        cnt, users, mon, hits, _ = scan(arx, stripped)
        if cnt < 20:
            continue
        periods = []
        for m in months:
            cands = sorted(a for a in active_set.get(m, ()) if fam.lower() in a.lower())
            if not cands:
                continue
            if periods and periods[-1]["agents"] == cands:
                periods[-1]["to"] = m
            else:
                periods.append({"from": m, "to": m, "agents": cands})
        everyone = sorted({a for p in periods for a in p["agents"]})
        e = {"id": f"x:{word}", "kind": "alias", "label": word, "re": r"(?<![\w.@-])" + re.escape(word) + r"(?![\w-]|\s?\d)", "cs": True,
             **common(cnt, users, mon, hits)}
        if len(everyone) == 1:
            e.update(agent=everyone[0], status="verified", def_=None)
            e["def"] = f"{everyone[0]}, the only {word} agent active while the word was used."
            e.pop("def_")
        else:
            e.update(ambiguous=periods, status="inferred",
                     **{"def": "Bare family name. Which agent it means depends on who was active then; see the periods below."})
        entries.append(e)

    entries.sort(key=lambda e: -e["count"])
    out = {"months": months, "generated_from": {"messages": len(msgs), "first": msgs[0][0][:10], "last": msgs[-1][0][:10]},
           "entries": entries}
    (OUT / "glossary.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    kinds = Counter(e["kind"] for e in entries)
    defined = Counter((e["kind"], e.get("status", "undefined")) for e in entries)
    print("glossary.json", round((OUT / "glossary.json").stat().st_size / 1e6, 2), "MB;", dict(kinds), file=sys.stderr)
    print("definitions:", dict(defined), file=sys.stderr)


if __name__ == "__main__":
    main()
