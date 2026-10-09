"""Public job boards (Greenhouse, Lever, Ashby). No keys needed.

- Greenhouse: boards-api.greenhouse.io/v1/boards/{slug}/jobs; "first_published" dates each posting.
- Lever: api.lever.co/v0/postings/{slug}?mode=json; "createdAt" is epoch milliseconds.
- Ashby: api.ashbyhq.com/posting-api/job-board/{slug}; "publishedAt" is ISO.
Slugs collide across companies ("merge", "orbital" belong to other firms), so every slug in
data/entities.json was checked against the postings' own company description.
A snapshot is saved per company per day under data/jobs/, so hiring history builds up over time.
"""
import json
import time
import urllib.request
from datetime import date, datetime, timezone

from gt.env import DATA


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ground-truth-research/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _greenhouse(slug):
    for j in _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")["jobs"]:
        yield {"title": j["title"], "location": j["location"]["name"],
               "published": (j.get("first_published") or j["updated_at"])[:10], "url": j["absolute_url"]}


def _lever(slug):
    for j in _get(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        created = datetime.fromtimestamp(j["createdAt"] / 1000, tz=timezone.utc)
        yield {"title": j["text"], "location": j.get("categories", {}).get("location") or "",
               "published": created.date().isoformat(), "url": j["hostedUrl"]}


def _ashby(slug):
    for j in _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
        if j.get("isListed", True):
            yield {"title": j["title"], "location": j.get("location") or "",
                   "published": j["publishedAt"][:10], "url": j["jobUrl"]}


BOARDS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def snapshot(company_slug, boards):
    """Fetch every open posting for a company and save today's snapshot. Returns the postings."""
    postings = []
    for board, slug in boards.items():
        postings.extend(BOARDS[board](slug))
        time.sleep(0.3)
    postings.sort(key=lambda p: p["published"], reverse=True)
    out = DATA / "jobs" / company_slug / f"{date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(postings, indent=1) + "\n")
    return postings
