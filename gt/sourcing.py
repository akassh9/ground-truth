"""Sourcing: companies at formation, found in the public record before most investors know them.

- NRC letters of intent: a company's first formal step toward a nuclear license. Each one is a reactor,
  fuel or enrichment company announcing itself to the regulator.
- FAA new makers: aircraft makers whose first registered aircraft is recent. Noisy (vintage types,
  foreign manufacturers), so these are candidates, not findings. Only corporate makers are kept;
  individual owners never leave this module.

Usage: .venv/bin/python -m gt.sourcing   (writes data/sourcing.json)
"""
import json
import re
from collections import defaultdict

from gt import faa, nrc
from gt.env import DATA

SINCE = "2025-06-01"
CORPORATE = re.compile(r"\b(INC|LLC|CORP|CORPORATION|TECHNOLOGIES|SYSTEMS|AEROSPACE|INDUSTRIES|AVIATION|LABS|ROBOTICS|"
                       r"DEFENSE|DYNAMICS|AERONAUTICS)\b")
# established manufacturers and regulators that show up but aren't new companies
NOT_NEW = re.compile(r"LEONARDO|BAE SYSTEMS|ISRAEL AIRCRAFT|KOREAN AIR|VOUGHT|EXEDY|ENTERGY|NRC/|RIO ALGOM|"
                     r"ATKINSREALIS|CANDU|NEWCLEO|KOYA", re.I)


def known_names():
    """Portfolio and incumbent names, so sourcing only surfaces companies we don't already track."""
    names = {c["name"].lower() for c in json.loads((DATA / "anti_portfolio.json").read_text())["companies"]}
    inc = DATA / "incumbents.json"
    if inc.exists():
        names |= {c["name"].lower() for c in json.loads(inc.read_text())["companies"]}
    return names


def nrc_new_entrants(since=SINCE):
    docs, _ = nrc.search(q='"letter of intent"', limit=400)
    seen, out = set(), []
    known = known_names()
    for d in sorted(docs, key=lambda d: d.get("DocumentDate") or "", reverse=True):
        title, when = d["DocumentTitle"], d.get("DocumentDate") or ""
        org = (d.get("AuthorAffiliation") or [""])[0].strip()
        if when < since or "intent" not in title.lower() or not org or NOT_NEW.search(org) or NOT_NEW.search(title):
            continue
        name = org.lower().split(",")[0]
        docket = (d.get("DocketNumber") or [""])[0]
        if name in seen or (docket and docket in seen) or any(k in name for k in known):
            continue
        seen |= {name, docket} - {""}
        out.append({"company": org.split(",")[0], "date": when, "source": "nrc", "what": title,
                    "docket": (d.get("DocketNumber") or [""])[0], "evidence_url": d["Url"]})
    return out


def faa_new_makers(since="2025-01-01", minimum=2):
    faa.download()
    models = {r["CODE"]: (r["MFR"], r["MODEL"]) for r in faa._rows("ACFTREF.txt")}
    first, count, model_names = {}, defaultdict(int), defaultdict(set)
    for r in faa._rows("MASTER.txt"):
        maker, model = models.get(r["MFR MDL CODE"], ("", ""))
        day = faa._iso(r["CERT ISSUE DATE"])
        if not maker or not day:
            continue
        count[maker] += 1
        model_names[maker].add(model)
        first[maker] = min(first.get(maker, day), day)
    known = known_names()
    out = []
    for maker, day in first.items():
        if day < since or count[maker] < minimum or not CORPORATE.search(maker) or NOT_NEW.search(maker):
            continue
        if any(k in maker.lower() for k in known):
            continue
        out.append({"company": maker.title(), "date": day, "source": "faa", "aircraft": count[maker],
                    "what": f"First FAA-registered aircraft {day}; {count[maker]} registered; models: "
                            + ", ".join(sorted(model_names[maker])[:4]),
                    "evidence_url": faa.name_search_url(faa.core_name(maker))})
    return sorted(out, key=lambda c: (-c["aircraft"], c["date"]))


if __name__ == "__main__":
    found = {"nrc": nrc_new_entrants(), "faa": faa_new_makers()}
    (DATA / "sourcing.json").write_text(json.dumps(found, indent=1) + "\n")
    for source, rows in found.items():
        print(f"\n{source}: {len(rows)}")
        for r in rows[:15]:
            print(f"  {r['date']}  {r['company'][:36]:36} {r['what'][:80]}")
