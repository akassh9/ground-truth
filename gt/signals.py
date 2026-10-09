"""Build data/signals.jsonl: every physical-world signal for the companies in data/entities.json.

Shared format with Shadow Associate (one JSON object per line):
  company, domain, date, source, kind, headline, detail, evidence_url, confidence
plus extras readers may ignore: company_slug, id (stable, for dedup), amount.

Usage: python3 -m gt.signals   (re-fetches sources at most once a day; raw responses are cached)
"""
import calendar
import hashlib
import json
import re
from collections import Counter
from datetime import date, timedelta
from urllib.parse import urlparse

from gt import faa, jobs, nrc, usaspending
from gt.env import DATA

TODAY = date.today()
AWARDS_SINCE = "2024-01-01"  # older awards only if they're big
BIG_AWARD = 10_000_000
BUSY = 25  # companies with more awards than this only keep awards over $1M or from the last 90 days
ACRONYMS = {"HALEU", "LEU", "UF6", "DOE", "DOD", "IDIQ", "ASV", "LRIP", "COCO", "UAS", "SUAS", "US", "USA", "CBP",
            "NRC", "AI", "RF", "USV", "UUV", "FRC", "IT", "R&D", "OTA", "SBIR", "STTR", "ATAK", "C2"}
SKIP_NRC_TYPES = {"Legal-Affidavit", "- No Document Type Applies", "Meeting Summary", "Memoranda", "E-Mail"}
FACTORY_WORDS = re.compile(r"technician|machinist|welder|assembl|manufactur|production|quality|inspector|"
                           r"fabricat|\bCNC\b|composite|shipyard|\bplant\b|\bmechanics?\b|electrician", re.I)
BOARD_URLS = {"greenhouse": "https://job-boards.greenhouse.io/{}", "ashby": "https://jobs.ashbyhq.com/{}",
              "lever": "https://jobs.lever.co/{}"}


def money(x):
    x = float(x or 0)
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if x >= size:
            return f"${x / size:.1f}".rstrip("0").rstrip(".") + unit
    return f"${x:,.0f}"


def sentence(text):
    """Federal records are ALL CAPS; make them readable but keep acronyms."""
    words = [w.upper() if w.strip("(),.;:").upper() in ACRONYMS or re.fullmatch(r"\([a-z0-9-]{2,7}\)[,.;:]?", w)
             else w for w in (text or "").lower().split()]
    s = " ".join(words)
    return s[:1].upper() + s[1:]


def cached(name, fetch):
    """Fetch once a day; keep the raw response in data/raw/ (gitignored)."""
    path = DATA / "raw" / f"{name}.json"
    if path.exists() and date.fromtimestamp(path.stat().st_mtime) == TODAY:
        return json.loads(path.read_text())
    result = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result))
    return result


def base(co, **fields):
    return {"company": co["name"], "domain": co["domain"], "company_slug": co["slug"],
            "portfolio": co.get("portfolio", False), **fields}


def agency_name(a):
    """Military departments read better than "Department of Defense"; contracting offices read worse."""
    sub = a.get("Awarding Sub Agency") or ""
    return sub if sub and not re.search(r"Office|Procurement|Acquisition", sub) else a["Awarding Agency"]


def award_headline(co, a):
    agency, amount = agency_name(a), a["Award Amount"] or 0
    if a["kind"] == "idv":  # umbrella contracts: the obligated amount says little about the ceiling
        return f"{agency} put {co['name']} on a contract vehicle"
    what = "grant" if a["kind"] == "grant" else "contract"
    return f"{agency} awarded {co['name']} a {money(amount)} {what}" if amount >= 10_000 else \
        f"{agency} awarded {co['name']} a {what}"


def award_signals(co):
    for uei in co.get("uei", []):
        rows = cached(f"usaspending/{co['slug']}-{uei}-awards", lambda: usaspending.awards(uei))
        recent = (TODAY - timedelta(days=90)).isoformat()
        for a in rows:
            day = a.get("Base Obligation Date") or a.get("Start Date")
            amount = a["Award Amount"] or 0
            if day < AWARDS_SINCE and amount < BIG_AWARD:
                continue
            if len(rows) > BUSY and amount < 1_000_000 and day < recent and a["kind"] != "idv":
                continue  # contract vehicles stay: their dollar amount says nothing about their size
            yield base(co, date=day, source="usaspending", kind=f"federal_{a['kind']}",
                       headline=award_headline(co, a), detail=sentence(a.get("Description")),
                       evidence_url=usaspending.award_url(a["generated_internal_id"]),
                       confidence=1.0, amount=amount, id=f"usaspending:{a['generated_internal_id']}")
        for s in cached(f"usaspending/{co['slug']}-{uei}-subawards", lambda: usaspending.subawards(uei)):
            amount = s["Sub-Award Amount"] or 0
            if s.get("Sub-Recipient UEI") != uei or s["Sub-Award Date"] < AWARDS_SINCE or amount <= 0:
                continue  # negative amounts are refunds and corrections
            prime = sentence(s["Prime Recipient Name"]).title()
            yield base(co, date=s["Sub-Award Date"], source="usaspending", kind="federal_subaward",
                       headline=f"{prime} subcontracted {co['name']}"
                                + (f" for {money(amount)}" if amount >= 10_000 else ""),
                       detail=f"{sentence(s.get('Sub-Award Description'))}. Under prime award {s['Prime Award ID']} "
                              f"({s['Awarding Agency']}).",
                       evidence_url=usaspending.award_url(s["prime_award_generated_internal_id"]),
                       confidence=1.0, amount=amount,
                       id=f"usaspending-sub:{s['Sub-Award ID']}:{s['Sub-Award Date']}")


def nrc_signals(co):
    for docket in co.get("nrc_dockets", []):
        for doc in cached(f"nrc/{docket}", lambda: nrc.docket(docket)):
            types = doc.get("DocumentType") or ["Document"]
            title = doc["DocumentTitle"].strip()
            if SKIP_NRC_TYPES & set(types) or title.startswith("Enclosure") or "Attendee" in title:
                continue
            if (doc.get("DocumentDate") or "") < AWARDS_SINCE and "license application" not in title.lower():
                continue  # big dockets go back decades; keep recent filings and any license application
            frm = ", ".join(doc.get("AuthorAffiliation") or []) or "unknown"
            to = ", ".join(doc.get("AddresseeAffiliation") or []) or "unknown"
            yield base(co, date=doc["DocumentDate"], source="nrc", kind="nrc_" + re.sub(r"\W+", "_", types[0].lower()),
                       headline=title, detail=f"{types[0]} on NRC docket {docket}, from {frm} to {to}.",
                       evidence_url=doc["Url"], confidence=1.0, id=f"nrc:{doc['AccessionNumber']}")


def hiring_signals(co):
    if not co.get("jobs"):
        return
    postings = cached(f"jobs/{co['slug']}", lambda: jobs.snapshot(co["slug"], co["jobs"]))
    board, slug = next(iter(co["jobs"].items()))
    board_url = BOARD_URLS[board].format(slug)
    recent = [p for p in postings if p["published"] >= (TODAY - timedelta(days=30)).isoformat()]
    top = ", ".join(f"{loc} ({n})" for loc, n in Counter(p["location"] for p in postings).most_common(3))
    yield base(co, date=TODAY.isoformat(), source="jobs", kind="hiring_snapshot",
               headline=f"{co['name']} has {len(postings):,} open roles, {len(recent):,} posted in the last 30 days",
               detail=f"Most openings: {top}.", evidence_url=board_url, confidence=1.0,
               open_roles=len(postings), recent_roles=len(recent), id=f"jobs:{co['slug']}:{TODAY.isoformat()}")
    factory = [p for p in postings if FACTORY_WORDS.search(p["title"])]
    if factory:
        yield base(co, date=TODAY.isoformat(), source="jobs", kind="hiring_production",
                   headline=f"{len(factory):,} of {co['name']}'s {len(postings):,} open roles are on the factory floor",
                   detail="Examples: " + "; ".join(sorted({p["title"].strip() for p in factory})[:6]) + ".",
                   evidence_url=board_url, confidence=0.8, factory_roles=len(factory),
                   id=f"jobs-production:{co['slug']}:{TODAY.isoformat()}")
    for place, label in co.get("hiring_places", {}).items():
        hits = [p for p in postings if place.lower() in p["location"].lower()]
        if hits:
            newest = hits[0]
            yield base(co, date=newest["published"], source="jobs", kind="hiring_at_site",
                       headline=f"{co['name']} is hiring for {len(hits)} roles at {label}",
                       detail=f"Newest: {newest['title'].strip()} (posted {newest['published']}). Others include: "
                              + "; ".join(sorted({p["title"].strip() for p in hits[1:]})[:5]) + ".",
                       evidence_url=newest["url"], confidence=1.0, roles=len(hits),
                       id=f"jobs-site:{co['slug']}:{place}:{TODAY.isoformat()}")


def model_title(text):
    """'CPJ-100' and 'BDXL' stay as they are; 'ROADRUNNER' becomes 'Roadrunner'."""
    return " ".join(w if any(ch.isdigit() for ch in w) or len(w) <= 4 else w.title() for w in text.split())


def plural(n, word):
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def month_name(ym):
    return f"{calendar.month_name[int(ym[5:7])]} {ym[:4]}"


def faa_signals(co, fleet):
    """One company can register aircraft under several legal names (Shield AI, Martin UAV, Heron Systems),
    so everything is combined across them before any signal is made."""
    cores = [faa.core_name(n) for n in co.get("legal_names", [])]
    found = [fleet.get(c) or {} for c in cores]
    owned = [a for f in found for a in f.get("owned", [])]
    reserved = [r for f in found for r in f.get("reserved", [])]
    models = [m for f in found for m in f.get("models", [])]
    if not cores:
        return
    url = faa.name_search_url(cores[0])
    show = lambda a: model_title(a["model"]) if faa.core_name(a["maker"]) in cores else \
        f"{a['maker'].title()} {model_title(a['model'])}"
    if owned:
        latest = max(a["registered"] for a in owned if a["registered"])
        top = ", ".join(f"{m} ({n})" for m, n in Counter(show(a) for a in owned).most_common(4))
        yield base(co, date=latest, source="faa", kind="faa_fleet",
                   headline=f"{co['name']} has {len(owned):,} aircraft registered with the FAA",
                   detail=f"Most registered: {top}. Newest registration: {latest}.",
                   evidence_url=url, confidence=0.9, aircraft=len(owned),
                   id=f"faa-fleet:{co['slug']}:{TODAY.isoformat()}")
        for ym, days in by_recent_month([a["registered"] for a in owned], months=12).items():
            kinds = Counter(show(a) for a in owned if (a["registered"] or "").startswith(ym))
            yield base(co, date=max(days), source="faa", kind="faa_registrations",
                       headline=f"{co['name']} registered {plural(len(days), 'aircraft').replace('aircrafts', 'aircraft')} with the FAA in {month_name(ym)}",
                       detail="Models: " + ", ".join(f"{m} ({n})" for m, n in kinds.most_common(4)) + ".",
                       evidence_url=url, confidence=0.9, id=f"faa-reg:{co['slug']}:{ym}")
    for ym, days in by_recent_month([r["reserved"] for r in reserved], months=18).items():
        yield base(co, date=max(days), source="faa", kind="faa_reservations",
                   headline=f"{co['name']} reserved {plural(len(days), 'tail number')} with the FAA in {month_name(ym)}",
                   detail="Reserving tail numbers usually comes before new aircraft are registered.",
                   evidence_url=url, confidence=0.9, count=len(days), id=f"faa-rsv:{co['slug']}:{ym}")
    if models:
        names = sorted({model_title(m) for m in models})
        yield base(co, date=TODAY.isoformat(), source="faa", kind="faa_manufacturer",
                   headline=f"The FAA lists {co['name']} as the maker of {len(names)} aircraft models",
                   detail="Models: " + ", ".join(names[:12]) + ".", evidence_url=url, confidence=0.9,
                   id=f"faa-maker:{co['slug']}:{TODAY.isoformat()}")


def by_recent_month(days, months):
    cutoff = (TODAY - timedelta(days=31 * months)).isoformat()
    return {ym: d for ym, d in faa.by_month(d for d in days if d and d >= cutoff).items()}


def companies():
    """Anti Fund's physical portfolio (entities.json), then the incumbents they compete with (incumbents.json)."""
    portfolio = {c["slug"]: c for c in json.loads((DATA / "anti_portfolio.json").read_text())["companies"]}
    for entity in json.loads((DATA / "entities.json").read_text())["companies"]:
        p = portfolio[entity["slug"]]
        yield {**entity, "name": p["name"], "domain": urlparse(p["url"]).netloc.removeprefix("www."), "portfolio": True}
    incumbents = DATA / "incumbents.json"
    if incumbents.exists():
        for entity in json.loads(incumbents.read_text())["companies"]:
            if entity["slug"] not in portfolio:
                yield {**entity, "domain": entity.get("domain", "").removeprefix("www."), "portfolio": False}


def build():
    signals, cos = {}, list(companies())
    cores = sorted({faa.core_name(n) for co in cos for n in co.get("legal_names", [])})
    key = hashlib.md5("|".join(cores).encode()).hexdigest()[:8]
    fleet = cached(f"faa/extract-{key}", lambda: faa.extract(cores))
    for co in cos:
        for make in (award_signals, nrc_signals, hiring_signals):
            for s in make(co):
                signals[s["id"]] = s
        for s in faa_signals(co, fleet):
            signals[s["id"]] = s
    rows = sorted(signals.values(), key=lambda s: (s["date"], s["company"]), reverse=True)
    out = DATA / "signals.jsonl"
    out.write_text("".join(json.dumps(s) + "\n" for s in rows))
    return rows


if __name__ == "__main__":
    rows = build()
    print(f"{len(rows)} signals -> data/signals.jsonl")
    for (company, source), n in sorted(Counter((s["company"], s["source"]) for s in rows).items()):
        print(f"  {company:22} {source:12} {n}")
