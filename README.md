# AI Village Ethogram

Exploratory analysis of the [AI Village dataset](https://huggingface.co/datasets/aidigestorg/ai-village) from AI Digest: 46 LLM agents pursuing shared goals from April 2025 to September 2026. The results are an interactive page at [justinshenk.com/projects/ai-village](https://justinshenk.com/projects/ai-village).

This is exploratory work. The findings describe one run of the village and have not been peer reviewed. Each tab of the page states its method and caveats.

## What's here

| Path | What it does |
|---|---|
| `analysis/build_strips.py` | Per-agent activity states over village time (strips, transitions) |
| `analysis/embed_trajectories.py` | bge-base embeddings of each agent-day, UMAP maps and drift |
| `analysis/memory_health.py`, `memory_tab.py` | Memory metrics per rewrite; loop onsets, Granger-style tests, early-warning signals |
| `analysis/memory_rewrite.py` | What memory rewrites keep, reword and drop, by line type |
| `analysis/build_help.py` | Requests for human help, categorised, with outcomes |
| `analysis/glossary_data.py`, `legibility_data.py` | Village jargon glossary; legibility trends and projections |
| `analysis/net_common.py`, `network_data.py` | Mention network, rooms, pecking order, factions |
| `analysis/make_label_batches.py` | Sample of 10,000 messages for stance and concern labels |
| `analysis/out/label_batches/INSTRUCTIONS.md` | Labelling instructions (the labels were made by Claude subagents reading each message) |
| `analysis/student.py` | Signed edges and radius of concern from the labels; a student classifier (too weak to use at scale) |
| `analysis/oversight_data.py`, `experiments_data.py` | Oversight timeline; quasi-experiments around scaffolding changes (DiD, ITS, wild cluster bootstrap) |
| `analysis/futures_data.py`, `blog_data.py` | Research trajectories and blog-post proposals |
| `analysis/llm_label.py` | Earlier local-LLM labelling attempt (not used for the results) |
| `analysis/site/` | Page source: `ethogram.html`, tab modules (`*.js`), `inline_modules.py` (inlines modules), `export_site.py` (standalone export) |
| `analysis/video/` | Two short vertical videos made from the findings (PIL, macOS `say`, synthesised audio, ffmpeg) |

## Reproducing

1. Request access to the dataset on Hugging Face and download it into `data/` (the scripts expect the `.jsonl.gz` tables and `village-transcript.json`; `computer_use_turns` and the screenshot archives are not needed).
2. `uv venv && uv pip install -r requirements.txt`
3. Run the builders roughly in this order; each writes JSON to `analysis/out/`:
   `build_strips.py`, `embed_trajectories.py`, `memory_health.py`, `memory_tab.py`, `memory_rewrite.py`, `build_help.py`, `glossary_data.py`, `legibility_data.py`, `network_data.py`, `make_label_batches.py` (then label the batches following `INSTRUCTIONS.md`), `student.py`, `oversight_data.py`, `experiments_data.py`, `futures_data.py`, `blog_data.py`.
4. Symlink or copy the JSON outputs into `analysis/site/`, run `python3 analysis/site/inline_modules.py`, and serve `analysis/site/` (for example `python3 -m http.server`), or run `export_site.py` for a standalone copy.

Derived data is not committed, because it is built from the gated dataset.

## Citation

Data: AI Digest, "AI Village dataset", 2026. https://theaidigest.org/village. Used under its research terms.
