"""NRC ADAMS Public Search (APS) API.

POST https://adams-api.nrc.gov/aps/api/search with the header Ocp-Apim-Subscription-Key.
The body needs both "filters" and "anyFilters", even when empty. Learned by probing,
since the API guide PDF blocks scripts:
- a working filter is {"field": "DocketNumber", "value": "07007040", "operator": "equals"};
  an unknown operator such as "eq" is silently ignored and returns the whole index
  (5.4M documents), so always sanity-check counts;
- results come 100 at a time; page with "skip" ("pageNumber" and "page" are ignored).

Usage: python3 -m gt.nrc docket 07007040   (saves data/nrc/07007040.json)
"""
import json
import os
import sys
import time
import urllib.request

from gt.env import DATA, load_env

SEARCH_URL = "https://adams-api.nrc.gov/aps/api/search"
PAGE = 100


def _post(body):
    load_env()
    req = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(body).encode(),
        headers={
            "Ocp-Apim-Subscription-Key": os.environ["NRC_APS_KEY"],
            "Content-Type": "application/json",
            "User-Agent": "ground-truth-research/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def equals(field, value):
    return {"field": field, "value": value, "operator": "equals"}


def search(q="", filters=(), any_filters=(), limit=1000):
    """Up to `limit` matching documents (the inner "document" objects), plus the total count."""
    docs, total = [], 0
    while len(docs) < limit:
        page = _post({"q": q, "filters": list(filters), "anyFilters": list(any_filters), "skip": len(docs)})
        total = page["count"]
        batch = [r["document"] for r in page["results"]]
        docs.extend(batch)
        if len(batch) < PAGE or len(docs) >= total:
            break
        time.sleep(0.5)
    return docs[:limit], total


def docket(number, limit=20_000):
    """Every document filed on a docket, oldest first. Big dockets exist (Urenco USA has 6,000+), but a
    count in the millions means the filter was silently ignored."""
    docs, total = search(filters=[equals("DocketNumber", number)], limit=limit)
    if total >= limit:
        raise RuntimeError(f"docket {number} matched {total} documents; the filter was probably ignored")
    return sorted(docs, key=lambda d: d.get("DocumentDate") or "")


if __name__ == "__main__":
    cmd, number = sys.argv[1:3]
    if cmd != "docket":
        sys.exit("usage: python3 -m gt.nrc docket <docket-number>")
    docs = docket(number)
    out = DATA / "nrc" / f"{number}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(docs, indent=1) + "\n")
    print(f"{len(docs)} documents -> {out.relative_to(DATA.parent)}")
