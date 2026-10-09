"""Copy what the website needs into site/public/data/. Public facts only. The one thing taken from
data/private/ is evidence(): counts and rates from the model comparison, never a company name or a deal
field (Akash cleared aggregates from his PitchBook export for publication, 2026-10-08).

Usage: .venv/bin/python -m gt.export
"""
import json
import re
import shutil

from gt.env import DATA, ROOT

OUT = ROOT / "site" / "public" / "data"
ADMIN = re.compile(r"safeguards|facility clearance|appointment|reviewing official|\\bSGI\\b|attendee", re.I)  # NRC paperwork
FRAME_WIDTH = 960  # satellite frames are re-encoded as WebP at this width to keep the page light


def write(name, obj):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")))


def portfolio():
    keep = ("slug", "name", "url", "description", "group", "invested", "stages")
    return [{k: c[k] for k in keep} for c in json.loads((DATA / "anti_portfolio.json").read_text())["companies"]]


def signals():
    return [json.loads(line) for line in (DATA / "signals.jsonl").read_text().splitlines()]


def site_list():
    path = DATA / "sites.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        raw = raw["sites"] if "sites" in raw else [{"slug": k, **v} for k, v in raw.items() if isinstance(v, dict)]
    return raw


def site_relevant(signal):
    """A site timeline shows what bears on that site: NRC filings, hiring there, and major programs.
    A company's hundreds of small awards elsewhere would bury it."""
    if signal["source"] == "nrc":
        return not ADMIN.search(signal["headline"])
    if signal["kind"] == "hiring_at_site":
        return True
    return signal["source"] == "usaspending" and (signal.get("amount") or 0) >= 100e6


def frames(site, all_signals):
    """Re-encode a site's frames and pair them with the owning company's dated filings."""
    from PIL import Image  # only needed here; lives in .venv

    src = DATA / "frames" / site["slug"]
    manifest_path = src / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    entries = manifest["frames"] if isinstance(manifest, dict) and "frames" in manifest else manifest
    dest = OUT / "sites" / site["slug"]
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for e in entries:
        if (e.get("snow_pct") or 0) > 30:
            continue  # a snowed-over month says nothing about construction
        name = e.get("file") or e.get("path") or f"{e['month']}.png"
        img_path = src / name.split("/")[-1]
        if not img_path.exists():
            continue
        img = Image.open(img_path).convert("RGB")
        if img.width > FRAME_WIDTH:
            img = img.resize((FRAME_WIDTH, round(img.height * FRAME_WIDTH / img.width)), Image.LANCZOS)
        webp = img_path.stem + ".webp"
        img.save(dest / webp, "WEBP", quality=74, method=6)
        out.append({"label": e.get("month") or img_path.stem, "date": e.get("date") or e.get("acquired") or e.get("datetime", ""),
                    "file": f"/data/sites/{site['slug']}/{webp}", "credit": e.get("credit", ""),
                    "kind": "aerial" if "naip" in img_path.stem.lower() else "satellite"})
    out.sort(key=lambda f: (f["kind"] != "aerial", f["date"] or f["label"]))
    company = site.get("company")
    milestones = json.loads((DATA / "site_milestones.json").read_text()).get(site["slug"], []) \
        if (DATA / "site_milestones.json").exists() else []
    filings = sorted([{k: s[k] for k in ("date", "source", "kind", "headline", "evidence_url")}
                      for s in all_signals if s["company_slug"] == company and site_relevant(s)]
                     + [{**m, "source": "news", "kind": "milestone"} for m in milestones],
                     key=lambda s: s["date"])
    return {"slug": site["slug"], "label": site.get("label", site["slug"]), "company": company,
            "verified": site.get("verified", False), "frames": out, "filings": filings}


HEAD_ON = ("head_on_with_entrenched", "head_on_with_building")


def evidence():
    """Aggregates for the site's evidence section, built field by field so nothing per-company can leak."""
    private = DATA / "private"
    if not (private / "compare.json").exists():
        return None
    r = json.loads((private / "compare.json").read_text())
    m, cost = r["market"], r["cost_and_speed"]
    out = {
        "companies": m["checked"], "in_lanes": m["in_thesis"], "portfolio_conflicts": m["portfolio_conflicts"],
        "positions": {k: m["positions"].get(k, 0) for k in (*HEAD_ON, "complement", "white_space", "off_map")},
        "fights_a_giant": r["jev_vs_haiku"]["fights_a_giant"], "citations": r["citations"],
        "refused_by_haiku": r["refused_by_haiku"],
        "cost": {k: {"companies": v["companies"], "usd": v["usd"], "median_seconds": v.get("median_seconds")}
                 for k, v in cost.items()},
    }
    # the blind hand labels, scored before the "off the map" answer existed (data/private/v1): when a model
    # said head-on, how often did Akash agree; when it said open (or outside the lanes), how often did he
    v1 = private / "v1" / "compare.json"
    if v1.exists():
        rows = json.loads(v1.read_text())["vs_akash"]["companies"]
        said = {"head_on": HEAD_ON, "open": ("white_space", "out_of_scope")}
        out["labels"] = {"labeled": len(rows), **{grader: {kind: {
            "n": sum(x[grader] in positions for x in rows),
            "agree": sum(x[grader] in positions and x["akash"] == kind for x in rows)}
            for kind, positions in said.items()} for grader in ("jev", "haiku", "opus")}}
    return out


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    all_signals = signals()
    write("portfolio.json", portfolio())
    # the feed shows Anti Fund's own companies; incumbents' evidence reaches the site through the lane map
    write("signals.json", [x for x in all_signals if x.get("portfolio")])
    if (DATA / "lane_map.json").exists():
        write("lane_map.json", json.loads((DATA / "lane_map.json").read_text()))
    # only sites whose location was verified go public
    exported_sites = [s for s in (frames(site, all_signals) for site in site_list() if site.get("verified")) if s and s["frames"]]
    write("sites.json", exported_sites)
    if (DATA / "sourcing.json").exists():
        found = json.loads((DATA / "sourcing.json").read_text())
        # FAA new makers are noisy; publish only those registering aircraft at volume
        write("sourcing.json", {"nrc": found["nrc"], "faa": [r for r in found["faa"] if r["aircraft"] >= 10]})
    files = sorted((DATA / "checks").glob("[!_]*.json")) if (DATA / "checks").exists() else []  # skip _report.json
    checks = [c for c in (json.loads(p.read_text()) for p in files) if "verdict" in c]
    write("checks.json", [{k: c[k] for k in ("name", "url", "verdict", "aliases") if k in c} for c in checks])
    if found_evidence := evidence():
        write("evidence.json", found_evidence)
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"exported {len(all_signals)} signals, {len(exported_sites)} sites, {len(checks)} checks -> site/public/data "
          f"({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
