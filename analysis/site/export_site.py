"""Export the Ethogram as a standalone page for the portfolio site.

    python3 analysis/site/export_site.py [DEST]   (default ~/projects/portfolio-site/public/projects/ai-village)

Wraps the artifact fragment in a full HTML document, adds a link back to the site, makes the JSON fetches
absolute (the page is served at /projects/ai-village without a trailing slash), and copies the data files.
"""
import re
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
DEST = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "projects/portfolio-site/public/projects/ai-village"
BASE = "/projects/ai-village/"

src = (SITE / "ethogram.html").read_text()
src = re.sub(r'^<meta charset="utf-8">\s*<title>[^<]*</title>\s*', "", src)

head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Village Ethogram</title>
<meta name="description" content="Interactive analysis of the AI Village: 46 LLM agents pursuing shared goals over 18 months. Activity, memory, human help, oversight, network structure and legibility.">
<meta property="og:title" content="Village Ethogram">
<meta property="og:description" content="Interactive analysis of the AI Village dataset (AI Digest): 46 LLM agents, April 2025 to September 2026.">
<meta property="og:image" content="https://justinshenk.com/ai-village-preview.png">
<script>
  // data files live next to this page; it is served without a trailing slash
  (function () {{
    const f = window.fetch.bind(window);
    window.fetch = (u, o) => f(typeof u === "string" && /^[\\w.-]+\\.json$/.test(u) ? "{BASE}" + u : u, o);
  }})();
</script>
</head>
<body>
<div style="max-width:1280px;margin:0 auto;padding:12px 16px 0;font:13px system-ui,sans-serif">
  <a href="/" style="color:inherit;opacity:.7;text-decoration:none">← justinshenk.com</a>
</div>
"""
html = head + src + "\n</body>\n</html>\n"

DEST.mkdir(parents=True, exist_ok=True)
(DEST / "index.html").write_text(html)
n = 0
for j in sorted(SITE.glob("*.json")):
    shutil.copyfile(j.resolve(), DEST / j.name)
    n += 1
size = sum(p.stat().st_size for p in DEST.iterdir()) / 1e6
print(f"wrote {DEST}/index.html and {n} data files ({size:.1f} MB)")
