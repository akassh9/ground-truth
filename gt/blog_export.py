"""Copy what the Audience of One post needs into the blog repo, which is now the only place Ground Truth is shown.

Two things go over:
- the figures' data (public/ground-truth/): the site time-lapses, the lane map, the portfolio's signals, the
  public example verdicts and the evaluation totals. Only files gt.export already serves publicly; run it first.
- the live Check's backend: api/check.py, the five gt modules it needs, its data (the lane map, the open-calls
  snapshot, the portfolio's UEIs) and requirements.txt, so the blog's own Vercel project runs the Check. The copies
  are overwritten on every export; edit them here, not there. Refresh the snapshot first: python -m gt.calls.

Usage: .venv/bin/python -m gt.blog_export ~/c/work/react-app-audit
"""
import json
import shutil
import sys
from pathlib import Path

from gt.env import DATA, ROOT

SITE_DATA = ROOT / "site" / "public" / "data"
SITES = ("general-matter-paducah", "arsenal-1")
FIGURE_DATA = ("lane_map.json", "signals.json", "checks.json", "evidence.json")
BACKEND = ("gt/__init__.py", "gt/env.py", "gt/check.py", "gt/calls.py", "gt/api.py", "api/check.py", "requirements.txt")
BACKEND_DATA = ("lane_map.json", "open_calls.json", "entities.json")
NOTE = "Copied from the ground-truth repo by gt.blog_export; edit it there, not here.\n"


def figures(dest):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    sites = [s for s in json.loads((SITE_DATA / "sites.json").read_text()) if s["slug"] in SITES]
    for site in sites:
        shutil.copytree(SITE_DATA / "sites" / site["slug"], dest / site["slug"])
        for frame in site["frames"]:
            frame["file"] = frame["file"].replace("/data/sites/", "/ground-truth/")
    (dest / "sites.json").write_text(json.dumps(sites, separators=(",", ":")))
    for name in FIGURE_DATA:
        shutil.copy(SITE_DATA / name, dest / name)


def backend(blog):
    for rel in BACKEND:
        (blog / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, blog / rel)
    (blog / "data").mkdir(exist_ok=True)
    for name in BACKEND_DATA:
        shutil.copy(DATA / name, blog / "data" / name)
    (blog / "gt" / "README.md").write_text(NOTE)


def main(blog):
    blog = Path(blog).expanduser()
    figures(blog / "public" / "ground-truth")
    backend(blog)
    size = sum(p.stat().st_size for p in (blog / "public" / "ground-truth").rglob("*") if p.is_file())
    print(f"figure data ({size / 1e6:.1f} MB) and the Check's backend -> {blog}")


if __name__ == "__main__":
    main(sys.argv[1])
