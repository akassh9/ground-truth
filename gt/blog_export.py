"""Copy what the Audience of One post needs into the blog repo: the site time-lapses (frames and filings)
and the evaluation totals. Only files the Ground Truth site already serves publicly (run gt.export first).

Usage: .venv/bin/python -m gt.blog_export ~/c/work/react-app-audit/public/ground-truth
"""
import json
import shutil
import sys
from pathlib import Path

from gt.env import ROOT

SITE_DATA = ROOT / "site" / "public" / "data"
SITES = ("general-matter-paducah", "arsenal-1")


def main(dest):
    dest = Path(dest).expanduser()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    sites = [s for s in json.loads((SITE_DATA / "sites.json").read_text()) if s["slug"] in SITES]
    for site in sites:
        shutil.copytree(SITE_DATA / "sites" / site["slug"], dest / site["slug"])
        for frame in site["frames"]:
            frame["file"] = frame["file"].replace("/data/sites/", "/ground-truth/")
    (dest / "sites.json").write_text(json.dumps(sites, separators=(",", ":")))
    shutil.copy(SITE_DATA / "evidence.json", dest / "evidence.json")
    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    print(f"{len(sites)} sites and the evaluation totals -> {dest} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1])
