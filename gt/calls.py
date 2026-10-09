"""The money around a new company, for the Check: government calls it could answer now, and what the
government already spends on its kind of product.

Open calls come from three free sources, snapshotted into data/open_calls.json (refresh with
`python -m gt.calls` before deploying; the Check skips anything past its close date):
- DoD SBIR/STTR topics that are open or in pre-release, from DSIP (dodsbirsttr.mil). Each topic's Q&A count is
  public: how many questions would-be applicants have asked so far, a rough read on how crowded it is.
- Grants.gov opportunities, posted or forecast, from the agencies that fund companies' hard-tech R&D (DoD, DOE,
  NASA; NSF and USDA only through their small-business programs, since the rest is academic research), kept only
  when companies can apply (eligibility codes or text say so). RFIs, fellowships, education and university-only
  programs are dropped.
- DIU's open solicitations page: Commercial Solutions Openings, challenges and Bridge calls.

market() runs live with each check: federal awards from the last two years whose descriptions use the model's
search phrases, by agency and recipient (USAspending). It's keyword matching on award descriptions, so it reads
demand and crowding; it isn't an exact count. Recipients that are Anti Fund companies are flagged by UEI.

dodsbirsttr.mil fails DNSSEC validation on some resolvers (SERVFAIL). _dsip_dns() then resolves it through
Google's DNS-over-HTTPS with checking disabled; TLS still verifies the real hostname.

Usage: python -m gt.calls   (no keys needed)
"""
import concurrent.futures
import contextlib
import datetime as dt
import functools
import html
import json
import re
import socket
import urllib.parse
import urllib.request

from gt.env import DATA

UA = {"User-Agent": "ground-truth-research/0.1"}
OUT = DATA / "open_calls.json"

DSIP = "www.dodsbirsttr.mil"
DSIP_API = f"https://{DSIP}/topics/api/public/topics"
OPEN, PRE_RELEASE = 591, 592  # DSIP topic status codes
COMPONENTS = {"ARMY": "Army", "NAVY": "Navy", "DAF": "Air Force", "USAF": "Air Force", "AF": "Air Force",
              "SOCOM": "SOCOM", "MDA": "Missile Defense Agency", "DHA": "Defense Health Agency",
              "SDA": "Space Development Agency", "CBD": "Chemical and Biological Defense"}

GRANTS_API = "https://api.grants.gov/v1/api"
GRANT_AGENCIES = ("DOD", "DOE", "NASA", "NSF", "USDA")
SMALL_BUSINESS_ONLY = ("NSF", "USDA")  # everything else they post is academic research or farm programs
SMALL_BUSINESS = re.compile(r"SBIR|STTR|Small Business", re.I)
NOT_HARD_TECH = ("DOD-AMRAA",)  # the Army's medical research programs
NOT_FOR_STARTUPS = re.compile(r"University Research|Instrumentation Program|Young Investigator|Postdoctoral|Fellowship"
                              r"|Academy|Education|STEM|Scholarship|\bRFI\b|Request for Information|Workshop|Conference", re.I)
HARD_TECH = {"ST", "EN", "AG", "ENV", "T", "NR", "O", "BC"}  # funding categories: R&D, energy, agriculture...
BOILERPLATE = re.compile(r"modification|amend|to obtain a copy|regist|exchange|e-?mail|questions about|https?://|www\.|"
                         r"deadline|page \d|date|submitted|submission", re.I)
COMPANY_TYPES = {"22", "23"}  # for-profits other than small businesses; small businesses
COMPANY_TEXT = re.compile(r"for[- ]profit|small business|commercial|industry|private sector|compan(y|ies)"
                          r"|any (type of )?entit|all responsible|open to all", re.I)
ONLY = re.compile(r"only be submitted by|limited to|restricted to|eligible applicants are", re.I)

DIU_PAGE = "https://www.diu.mil/work-with-us/open-solicitations"
DIU_ITEM = re.compile(r'<a href="(/work-with-us/submit-solution/([^"]+))" class="opportunity"[^>]*>\s*'
                      r'<h6[^>]*>(.*?)</h6>\s*<p[^>]*>(.*?)</p>\s*<p[^>]*>Closing: (\d{4}-\d{2}-\d{2})', re.S)

USASPENDING = "https://api.usaspending.gov/api/v2/search/spending_by_category"
AWARD_TYPES = ["A", "B", "C", "D", "02", "03", "04", "05"]  # contracts and grants
NOT_A_RECIPIENT = re.compile(r"REDACTED|MULTIPLE RECIPIENTS|PRIVATE INDIVIDUAL|MISCELLANEOUS", re.I)


def _json(url, body=None, timeout=60):
    headers = {**UA, **({"Content-Type": "application/json"} if body is not None else {})}
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as resp:
        return json.load(resp)


def _text(s, limit=None):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
    return t[:limit].rsplit(" ", 1)[0] + "…" if limit and len(t) > limit else t


def _ms_date(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat() if ms else None


def _us_date(s):
    """Grants.gov's MM/DD/YYYY, or None."""
    return dt.datetime.strptime(s, "%m/%d/%Y").date().isoformat() if s else None


def _number(x):
    try:
        return float(x)
    except (TypeError, ValueError):  # Grants.gov sends "none" for no ceiling
        return 0.0


def _dollars(n):
    n = _number(n)
    return f"${n / 1e6:,.1f}M" if n >= 1e6 else f"${n:,.0f}"


@contextlib.contextmanager
def _dsip_dns():
    real = socket.getaddrinfo
    try:
        real(DSIP, 443)
        ip = None
    except socket.gaierror:
        answers = _json("https://dns.google/resolve?" + urllib.parse.urlencode({"name": DSIP, "type": "A", "cd": 1}))
        ip = next(a["data"] for a in answers.get("Answer", []) if a.get("type") == 1)
        socket.getaddrinfo = lambda host, *a, **k: real(ip if host == DSIP else host, *a, **k)
    try:
        yield
    finally:
        socket.getaddrinfo = real


def dsip():
    """Open and pre-release DoD SBIR/STTR topics, with each topic's objective and keywords."""
    param = {"searchText": None, "components": None, "programYear": None, "solicitationCycleNames": ["openTopics"],
             "releaseNumbers": [], "topicReleaseStatus": [OPEN, PRE_RELEASE], "modernizationPriorities": None,
             "sortBy": "finalTopicCode,asc", "technologyAreaIds": [], "component": None, "program": None}
    topics, page = [], 0
    with _dsip_dns():
        while True:
            query = urllib.parse.urlencode({"searchParam": json.dumps(param), "size": 100, "page": page})
            batch = _json(f"{DSIP_API}/search?{query}")
            topics += batch["data"]
            if not batch["data"] or len(topics) >= batch["total"]:
                break
            page += 1
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            details = list(pool.map(lambda t: _json(f"{DSIP_API}/{t['topicId']}/details"), topics))
    return [{
        "id": t["topicCode"],
        "source": "DoD SBIR/STTR",
        "agency": COMPONENTS.get(t["component"], t["component"]),
        "kind": f"{t['program']} topic",
        "title": _text(t["topicTitle"]),
        "status": "open" if t["topicStatus"] == "Open" else "pre-release",
        "opens": _ms_date(t.get("topicStartDate")),
        "closes": _ms_date(t.get("topicEndDate")),
        "questions": t.get("topicQuestionCount") or 0,
        "keywords": _text(d.get("keywords"), 150),
        "summary": _text(d.get("objective"), 220),
        "url": f"https://{DSIP}/topics-app/?baa={t['cycleName']}",
    } for t, d in zip(topics, details)]


def _open_to_companies(syn):
    types = {a["id"] for a in syn.get("applicantTypes") or []}
    eligibility = _text(syn.get("applicantEligibilityDesc"))
    return bool(types & COMPANY_TYPES) or bool(COMPANY_TEXT.search(eligibility)) \
        or (types == {"99"} and not ONLY.search(eligibility))


def _for_startups(hit):
    agency, title = hit["agencyCode"].split("-")[0], html.unescape(hit["title"])
    return agency in GRANT_AGENCIES and hit["agencyCode"] not in NOT_HARD_TECH and not NOT_FOR_STARTUPS.search(title) \
        and (agency not in SMALL_BUSINESS_ONLY or bool(SMALL_BUSINESS.search(title)))


def _agency(hit):
    """"DOE (Idaho Field Office)": the sub-agency alone rarely says who's paying."""
    top = {"DOD": "DoD", "DOE": "DOE", "NASA": "NASA", "NSF": "NSF", "USDA": "USDA"}[hit["agencyCode"].split("-")[0]]
    sub = {"Advanced Research Projects Agency Energy": "ARPA-E"}.get(html.unescape(hit["agency"]).strip(),
                                                                     html.unescape(hit["agency"]).strip())
    return top if sub.upper() in (top.upper(), "") or "National Science Foundation" in sub else f"{top} ({sub})"


def _gist(desc, limit):
    """What a listing funds. Grants.gov synopses often open with amendment notes and portal instructions instead."""
    sentences = re.split(r"(?<=[.!?])\s+", _text(desc).replace("U.S.", "US"))
    return _text(" ".join(s for s in sentences if not BOILERPLATE.search(s)), limit)


def grants():
    """Posted and forecast Grants.gov opportunities in hard-tech categories that companies can apply for."""
    hits = _json(f"{GRANTS_API}/search2", {"oppStatuses": "forecasted|posted", "eligibilities": "22|23|25|99",
                                           "rows": 5000})["data"]["oppHits"]
    hits = [h for h in hits if _for_startups(h)]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        details = list(pool.map(lambda h: _json(f"{GRANTS_API}/fetchOpportunity", {"opportunityId": int(h["id"])})["data"], hits))
    out = []
    for h, d in zip(hits, details):
        syn = d.get("synopsis") or d.get("forecast") or {}
        categories = {c["id"] for c in syn.get("fundingActivityCategories") or []}
        if not categories & HARD_TECH or not _open_to_companies(syn):
            continue
        instruments = {i.get("description", "") for i in syn.get("fundingInstruments") or []}
        ceiling = _number(syn.get("awardCeiling"))
        out.append({
            "id": h["number"],
            "source": "Grants.gov",
            "agency": _agency(h),
            "kind": "cooperative agreement" if instruments == {"Cooperative Agreement"} else "grant",
            "title": _text(h["title"]),
            "status": "open" if h["oppStatus"] == "posted" else "forecast",
            "opens": _us_date(h.get("openDate")),
            "closes": _us_date(h.get("closeDate")),
            "funding": f"up to {_dollars(ceiling)} per award" if ceiling > 0 else "",
            "summary": _gist(syn.get("synopsisDesc") or syn.get("forecastDesc"), 220),
            "url": f"https://www.grants.gov/search-results-detail/{h['id']}",
        })
    return out


def diu():
    """DIU's open solicitations: CSOs, challenges and Bridge calls (scraped; DIU has no API)."""
    req = urllib.request.Request(DIU_PAGE, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        page = resp.read().decode("utf-8", errors="ignore")
    return [{"id": code, "source": "DIU", "agency": "Defense Innovation Unit", "kind": _text(kind),
             "title": _text(title), "status": "open", "opens": None, "closes": closes,
             "url": "https://www.diu.mil" + path}
            for path, code, kind, title, closes in DIU_ITEM.findall(page)]


def snapshot():
    calls, failed = [], []
    for name, fetch in (("dsip", dsip), ("grants", grants), ("diu", diu)):
        try:
            calls += fetch()
        except Exception as e:  # one source down shouldn't block the rest
            failed.append(f"{name}: {e}")
    OUT.write_text(json.dumps({"as_of": dt.date.today().isoformat(), "calls": calls}, indent=1) + "\n")
    return calls, failed


@functools.lru_cache(maxsize=1)
def _snapshot():
    if not OUT.exists():
        return {"as_of": None, "calls": []}
    return json.loads(OUT.read_text())


def as_of():
    return _snapshot()["as_of"]


@functools.lru_cache(maxsize=4)
def _open_on(day):
    return [c for c in _snapshot()["calls"] if not c.get("closes") or c["closes"] >= day]


def open_calls():
    """Calls in the snapshot that haven't closed yet. Ones without a close date (rolling) stay in."""
    return _open_on(dt.date.today().isoformat())


def context():
    """The open calls as compact text for the Check's cached system prompt, one line each."""
    lines = []
    for c in open_calls():
        when = ", ".join(x for x in (c.get("opens") and c["status"] != "open" and f"opens {c['opens']}",
                                     c.get("closes") and f"closes {c['closes']}") if x) or "rolling"
        extra = "; ".join(x for x in (c.get("funding"), c.get("keywords") and f"keywords: {c['keywords']}",
                                      c.get("summary")) if x)
        lines.append(f"- [{c['id']}] {c['agency']} {c['kind']}, {c['status']} ({when}): {c['title']}. {extra}".rstrip())
    return "\n".join(lines)


def resolve(verdict_calls):
    """The model's picks joined to the snapshot, for display: (calls, unknown ids). An id the snapshot doesn't
    have, or a call that has closed since, is dropped and reported, the way cited_ids_ok() reports evidence."""
    known = {c["id"]: c for c in open_calls()}
    spelled = {cid.lower(): cid for cid in known}  # Claude sometimes adds a prefix ("DIU PROJ00711") or changes case
    picked, unknown, seen = [], [], set()
    for pick in verdict_calls:
        pick = pick if isinstance(pick, dict) else pick.model_dump()
        cid = pick["id"].strip().strip("[]").strip()
        cid = spelled.get(cid.lower()) or spelled.get(re.split(r"[:\s]+", cid)[-1].lower()) or cid
        if cid in seen:
            continue
        seen.add(cid)
        if cid in known:
            picked.append({**known[cid], "fit": pick["fit"], "why": pick["why"]})
        else:
            unknown.append(cid)
    return picked[:5], unknown


def money(verdict):
    """Everything the Check shows under the money: the picked calls joined to the snapshot, any ids it couldn't
    find, and the live spending read. A spending lookup that fails leaves market empty instead of failing the check."""
    picked, unknown = resolve(verdict.calls)
    try:
        spend = market(verdict.award_terms)
    except Exception:
        spend = None
    return {"calls": picked, "unknown_calls": unknown, "market": spend, "calls_as_of": as_of()}


@functools.lru_cache(maxsize=1)
def portfolio_ueis():
    """Anti Fund's physical companies by UEI, hand-checked in entities.json; matched by UEI, never by name."""
    return {uei for c in json.loads((DATA / "entities.json").read_text())["companies"] for uei in c.get("uei", [])}


def _category(kind, filters, limit=100, page=1):
    return _json(f"{USASPENDING}/{kind}/", {"category": kind, "filters": filters, "limit": limit, "page": page}, timeout=30)


def market(terms, years=2):
    """Federal awards from the last `years` whose descriptions use any of the search phrases: the total, the top
    buyers and how many recipients already share the money. None if there's nothing to search for."""
    terms = [t.strip() for t in terms if t and t.strip()][:4]
    if not terms:
        return None
    today = dt.date.today()
    since = (today - dt.timedelta(days=365 * years)).isoformat()
    filters = {"keywords": terms, "award_type_codes": AWARD_TYPES,
               "time_period": [{"start_date": since, "end_date": today.isoformat()}]}
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        agencies = pool.submit(_category, "awarding_agency", filters)
        pages = [pool.submit(_category, "recipient", filters, 100, p) for p in (1, 2, 3)]
        agencies = agencies.result()["results"]
        recipients = [r for p in pages for r in p.result()["results"]]
    total = sum(a["amount"] for a in agencies)
    named, ours = {}, set()  # one company can appear under several UEIs (parent and subsidiaries); merge by name
    for r in recipients:
        if r.get("name") and not NOT_A_RECIPIENT.search(r["name"]):
            named[r["name"]] = named.get(r["name"], 0) + r["amount"]
            if r.get("uei") in portfolio_ueis():
                ours.add(r["name"])
    top = sorted(named.items(), key=lambda kv: -kv[1])[:3]
    return {
        "terms": terms,
        "since": since,
        "total": round(total),
        "agencies": [{"name": a["name"], "amount": round(a["amount"])} for a in agencies[:3]],
        "recipients": len(named),
        "more_recipients": len(recipients) >= 300,
        "top": [{"name": name, "amount": round(amount), "portfolio": name in ours} for name, amount in top],
        "portfolio": sorted(ours),
        "url": "https://www.usaspending.gov/keyword_search/" + urllib.parse.quote(terms[0]),
    }


if __name__ == "__main__":
    calls, failed = snapshot()
    by_source = {}
    for c in calls:
        by_source[c["source"]] = by_source.get(c["source"], 0) + 1
    print(f"{len(calls)} open calls -> {OUT}: {by_source}")
    for f in failed:
        print(f"  failed {f}")
