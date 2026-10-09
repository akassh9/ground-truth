"""A private shortlist from the PitchBook export: companies in Anti Fund's lanes that neither model puts
head-on with anyone on the map, that don't conflict with the portfolio, and that aren't already in it. Only
open space and suppliers to the giants qualify. "Off the map" companies are left out: established competitors
exist, the map just can't see them.

Writes data/private/shortlist.csv with each company's latest deal from the export (date, size, series, lead
investor). Everything here stays private.

Usage: .venv/bin/python -m gt.shortlist
"""
import csv
import json
import re
from collections import Counter
from datetime import datetime

from gt.compare import PRIVATE, company_key, jev_results
from gt.env import DATA

KEEP = ("white_space", "complement")


def latest_deals():
    """Each company's most recent deal in the raw export, keyed like the cleaned list (gt/evaluate.from_table)."""
    with open(PRIVATE / "pitchbook.csv", newline="", encoding="utf-8-sig") as f:
        table = list(csv.reader(f))
    start = next(i for i, row in enumerate(table) if any("compan" in c.lower() for c in row) and len([c for c in row if c]) >= 3)
    latest = {}
    for row in table[start + 1:]:
        r = dict(zip(table[start], row))
        if not r.get("Companies", "").strip():
            continue
        name = re.sub(r"\s*\([^)]*\)\s*$", "", r["Companies"]).strip()
        url = r.get("Company Website", "").strip()
        url = url if not url or url.startswith("http") else "https://" + url
        try:
            when = datetime.strptime(r.get("Deal Date", ""), "%d-%b-%Y")
        except ValueError:
            when = datetime.min
        k = company_key(name, url)
        if k not in latest or when > latest[k]["when"]:
            latest[k] = {"when": when, "deal_date": when.date().isoformat() if when != datetime.min else "",
                         "deal_size_m": r.get("Deal Size", ""), "series": r.get("Series", ""),
                         "lead": r.get("Lead/Sole Investors", ""), "hq": r.get("HQ Location", "")}
    return latest


def portfolio():
    """Anti Fund's own companies (some raised rounds in the export window); they aren't prospects."""
    companies = json.loads((DATA / "anti_portfolio.json").read_text())["companies"]
    return {company_key(c["name"], c.get("url") or "")[1] for c in companies} - {""}


def main():
    jev, deals, owned = jev_results(), latest_deals(), portfolio()
    out = []
    for path in (PRIVATE / "checks").glob("[!_]*.json"):
        r = json.loads(path.read_text())
        v, k = r["verdict"], company_key(r["name"], r.get("url") or "")
        j = jev.get(k)
        if not v["lanes"] or v["portfolio_conflicts"] or v["position"] not in KEEP or not j or j["position"] not in KEEP:
            continue
        if k[1] in owned:
            continue
        deal = {key: val for key, val in deals.get(k, {}).items() if key != "when"}
        out.append({"company": r["name"], "website": r.get("url", ""), "lane": v["lanes"][0], "haiku": v["position"],
                    "jev": j["position"], "what_it_builds": v["what_it_builds"], "buyers": v["buyers"],
                    "why": v["reasoning"], "wedge": v["wedge"],
                    "sells_into": "; ".join(o["company"] for o in v["overlaps"] if o["relationship"] == "supplier_to_them"),
                    **deal})
    out.sort(key=lambda r: (r["lane"], r.get("deal_date", "")), reverse=True)
    fields = ["company", "website", "lane", "haiku", "jev", "what_it_builds", "buyers", "why", "wedge", "sells_into",
              "deal_date", "deal_size_m", "series", "lead", "hq"]
    with open(PRIVATE / "shortlist.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} on the shortlist -> data/private/shortlist.csv")
    print("both say supplier:", sum(r["haiku"] == r["jev"] == "complement" for r in out),
          "| both say open:", sum(r["haiku"] == r["jev"] == "white_space" for r in out))
    print("by lane:", dict(Counter(r["lane"] for r in out).most_common()))


if __name__ == "__main__":
    main()
