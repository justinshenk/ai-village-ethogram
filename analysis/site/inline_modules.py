"""Inline module scripts into ethogram.html between <!-- BEGIN name --> / <!-- END name --> markers."""
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
page = here / "ethogram.html"
html = page.read_text()
for name in sys.argv[1:]:
    js = (here / name).read_text()
    block = f"<!-- BEGIN {name} -->\n<script>\n{js}\n</script>\n<!-- END {name} -->"
    pat = re.compile(rf"<!-- BEGIN {re.escape(name)} -->.*?<!-- END {re.escape(name)} -->", re.S)
    if pat.search(html):
        html = pat.sub(lambda m: block, html)
    else:
        html = html.rstrip() + "\n\n" + block + "\n"
    print("inlined", name, len(js), "chars")
page.write_text(html)
