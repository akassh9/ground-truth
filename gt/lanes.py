"""The lane map: who is already entrenched in each sector Anti Fund invests in.

Each company gets an entrenchment score from public evidence only (signals.jsonl, the NRC dockets
behind them, and sites.json):
  federal awards since 2020   >=$1B: 5   >=$100M: 3   >=$10M: 2   >=$1M: 1   (multi-year awards from before 2024 count)
  on a contract vehicle       1
  factory-floor hiring        >=100 roles: 3   >=25: 2   >=5: 1
  FAA-registered fleet        >=100 aircraft: 2   >=10: 1
  NRC                         holds a license or construction permit: 3   applied since 2020: 2   active docket: 1
  a verified physical site    2
Tiers: entrenched >= 7 (or $1B+ in federal awards since 2020), building 4-6, early <= 3. Scores are per company, not per lane: Anduril's
footprint counts in every lane it plays in. A lane is "owned" when anyone in it is entrenched,
"contested" when someone is building, otherwise "open" (nobody entrenched on the public record).
Every fact keeps its evidence id and URL, so the Check can cite it and we can verify the citations.

Usage: python3 -m gt.lanes   (writes data/lane_map.json and data/lane_map.md)
"""
import json
import re
from collections import Counter, defaultdict

from gt.env import DATA
from gt.signals import money

FEDERAL = ("federal_contract", "federal_grant", "federal_subaward")
AWARDS_FROM = "2020-01-01"
MAX_SCORE = 16
ISSUED = re.compile(r"issuance of (a |the )?(construction permit|license|operating license)|license issuance|"
                    r"construction permit issuance", re.I)


def _fact(text, signal):
    return {"text": text, "id": signal["id"], "url": signal["evidence_url"]}


def nrc_status(dockets):
    """What a company's own NRC dockets show: a license or permit held, an application, or just activity.
    Read from the raw dockets cached by gt.signals. A license number counts only when it recurs (200+
    documents); a single mention is usually a reference to someone else's license."""
    docs = []
    for number in dockets:
        path = DATA / "raw" / "nrc" / f"{number}.json"
        if path.exists():
            docs += json.loads(path.read_text())
    if not docs:
        return None
    issued = [d for d in docs if ISSUED.search(d["DocumentTitle"]) and "notice of receipt" not in d["DocumentTitle"].lower()]
    licenses = Counter(n for d in docs for n in (d.get("LicenseNumber") or []))
    held = [n for n, k in licenses.most_common() if k >= 200]
    applied = [d for d in docs if "license application" in d["DocumentTitle"].lower()
               and (d.get("DocumentDate") or "") >= AWARDS_FROM and "nureg" not in d["DocumentTitle"].lower()]
    recent = [d for d in docs if (d.get("DocumentDate") or "") >= "2024-01-01"]
    pick = lambda ds: max(ds, key=lambda d: d.get("DocumentDate") or "")
    if issued or held:
        d = pick(issued) if issued else pick([x for x in docs if held[0] in (x.get("LicenseNumber") or [])])
        label = f"Holds NRC license {held[0]}" if held else "Holds an NRC permit"
        return {"points": 3, "text": f"{label}; {d['DocumentTitle'][:110]} ({d.get('DocumentDate')})", "doc": d}
    if applied:
        d = pick(applied)
        return {"points": 2, "text": f"Applied for an NRC license: {d['DocumentTitle'][:110]} ({d.get('DocumentDate')})", "doc": d}
    if recent:
        d = pick(recent)
        return {"points": 1, "text": f"{len(recent)} NRC filings since 2024; latest: {d['DocumentTitle'][:100]} ({d.get('DocumentDate')})",
                "doc": d}
    return None


def entrenchment(signals, sites=(), nrc=None):
    score, facts, points = 0, [], {}  # points: what earned the score, so the site can show why

    def earn(what, n):
        nonlocal score
        if n:
            score += n
            points[what] = points.get(what, 0) + n

    awards = [s for s in signals if s["kind"] in FEDERAL and s["date"] >= AWARDS_FROM and (s.get("amount") or 0) > 0]
    total = sum(s["amount"] for s in awards)
    if total >= 1e6:
        earn("federal awards", 5 if total >= 1e9 else 3 if total >= 100e6 else 2 if total >= 10e6 else 1)
        biggest = max(awards, key=lambda s: s["amount"])
        facts.append(_fact(f"{money(total)} in federal awards since 2020; largest: {biggest['headline']} ({biggest['date']})",
                           biggest))
    vehicles = sorted((s for s in signals if s["kind"] == "federal_idv"), key=lambda s: s["date"], reverse=True)
    if vehicles:
        earn("contract vehicle", 1)
        facts.append(_fact(f"On {len(vehicles)} federal contract vehicle(s); latest: {vehicles[0]['detail'][:90]}",
                           vehicles[0]))
    for s in signals:
        if s["kind"] == "hiring_production":
            n = s["factory_roles"]
            earn("factory hiring", 3 if n >= 100 else 2 if n >= 25 else 1 if n >= 5 else 0)
            facts.append(_fact(s["headline"], s))
        elif s["kind"] == "hiring_at_site":
            facts.append(_fact(s["headline"], s))
        elif s["kind"] == "faa_fleet":
            earn("FAA fleet", 2 if s["aircraft"] >= 100 else 1 if s["aircraft"] >= 10 else 0)
            facts.append(_fact(f"{s['headline']}. {s['detail']}", s))
    if nrc:
        earn("NRC", nrc["points"])
        doc = nrc["doc"]
        facts.append({"text": nrc["text"], "id": f"nrc:{doc['AccessionNumber']}", "url": doc["Url"]})
    for site in sites:
        earn("site", 2)
        facts.append({"text": f"Physical site tracked from orbit: {site.get('label', site.get('slug'))}",
                      "id": f"site:{site.get('slug')}", "url": site.get("source_url", "")})
        break
    # $1B+ of federal money is entrenched on its own, whatever else the record misses
    tier = "entrenched" if score >= 7 or total >= 1e9 else "building" if score >= 4 else "early"
    return {"score": score, "tier": tier, "facts": facts, "points": points}


def load_sites():
    """Verified sites only: an unverified parcel shouldn't earn points."""
    path = DATA / "sites.json"
    sites = defaultdict(list)
    if path.exists():
        raw = json.loads(path.read_text())
        if isinstance(raw, dict):  # {"sites": [...]} or {slug: site}
            raw = raw["sites"] if "sites" in raw else [{"slug": k, **v} for k, v in raw.items() if isinstance(v, dict)]
        for site in raw:
            if site.get("verified"):
                sites[site.get("company")].append(site)
    return sites


def build():
    inc = json.loads((DATA / "incumbents.json").read_text())
    portfolio_names = {c["slug"]: c["name"] for c in json.loads((DATA / "anti_portfolio.json").read_text())["companies"]}
    dockets = {e["slug"]: e.get("nrc_dockets", []) for e in json.loads((DATA / "entities.json").read_text())["companies"]}
    dockets |= {c["slug"]: c.get("nrc_dockets", []) for c in inc["companies"]}
    by_company = defaultdict(list)
    for line in (DATA / "signals.jsonl").read_text().splitlines():
        s = json.loads(line)
        by_company[s["company_slug"]].append(s)
    sites = load_sites()

    members = defaultdict(list)
    for slug, lanes in inc.get("portfolio_lanes", {}).items():
        for lane in lanes:
            members[lane].append({"slug": slug, "name": portfolio_names.get(slug, slug), "portfolio": True})
    for c in inc["companies"]:
        for lane in c.get("lanes", []):
            members[lane].append({"slug": c["slug"], "name": c["name"], "portfolio": False, "why": c.get("why", "")})

    scored = {}
    lanes = []
    for lane in inc["lanes"]:
        companies = []
        for m in members.get(lane["slug"], []):
            if m["slug"] not in scored:
                scored[m["slug"]] = entrenchment(by_company.get(m["slug"], []), sites.get(m["slug"], []),
                                                 nrc_status(dockets.get(m["slug"], [])))
            companies.append({**m, **scored[m["slug"]]})
        companies.sort(key=lambda c: c["score"], reverse=True)
        tiers = {c["tier"] for c in companies}
        status = "owned" if "entrenched" in tiers else "contested" if "building" in tiers else "open"
        lanes.append({**lane, "status": status, "anti_fund_has": [c["name"] for c in companies if c["portfolio"]],
                      "companies": companies})
    out = {"note": "Entrenchment from public records only; see gt/lanes.py for the scoring.", "max_score": MAX_SCORE,
           "lanes": lanes}
    (DATA / "lane_map.json").write_text(json.dumps(out, indent=1) + "\n")
    (DATA / "lane_map.md").write_text(markdown(lanes))
    return lanes


STATUS = {"owned": "a giant is entrenched", "contested": "someone is building", "open": "nobody entrenched on the record"}


def markdown(lanes):
    lines = ["# Lane map: where the giants already are", ""]
    for lane in lanes:
        held = ", ".join(lane["anti_fund_has"]) or "none"
        lines += [f"## {lane['name']} ({STATUS[lane['status']]})", f"{lane['description']} Anti Fund portfolio here: {held}.", ""]
        for c in lane["companies"]:
            tag = " (portfolio)" if c["portfolio"] else ""
            lines.append(f"- **{c['name']}**{tag}: {c['tier']}, score {c['score']}")
            lines += [f"  - {f['text']}" for f in c["facts"][:4]]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    for lane in build():
        top = ", ".join(f"{c['name']} {c['score']}" for c in lane["companies"][:4])
        print(f"{lane['status']:10} {lane['name'][:38]:38} {top}")
