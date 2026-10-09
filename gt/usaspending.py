"""USAspending.gov API: federal contracts, grants and subcontracts. No key needed.

POST /api/v2/search/spending_by_award/ with filters.recipient_search_text, which matches
recipient names and UEIs (exact UEIs avoid name collisions like "SARONIC INVESTMENTS LLC").
Each request takes one award-type group at a time (contracts, IDVs, grants); mixing them errors.
With "subawards": true the same text matches the *sub*-awardee, so a startup's subcontracts
from primes like Lockheed show up too. Paging: "page" plus page_metadata.hasNext.
DoD awards appear about 90 days after they're made.
"""
import json
import time
import urllib.request

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
SINCE = "2007-10-01"  # earliest date the search endpoint covers
GROUPS = {
    "contract": ["A", "B", "C", "D"],
    "idv": ["IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E"],
    "grant": ["02", "03", "04", "05"],
}
FIELDS = ["Award ID", "Recipient Name", "Recipient UEI", "Start Date", "Base Obligation Date", "Award Amount",
          "Awarding Agency", "Awarding Sub Agency", "Description", "generated_internal_id",
          "Place of Performance State Code"]
SUB_FIELDS = ["Sub-Award ID", "Sub-Awardee Name", "Sub-Recipient UEI", "Sub-Award Date", "Sub-Award Amount",
              "Awarding Agency", "Prime Award ID", "Prime Recipient Name", "Sub-Award Description",
              "prime_award_generated_internal_id"]


def _post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "ground-truth-research/0.1"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def _search(text, codes, fields, sort, subawards=False, until=None, max_pages=20):
    rows, page = [], 1
    period = [{"start_date": SINCE, "end_date": until or time.strftime("%Y-%m-%d")}]
    while page <= max_pages:
        body = {"filters": {"recipient_search_text": [text], "award_type_codes": codes, "time_period": period},
                "fields": fields, "limit": 100, "page": page, "sort": sort, "order": "desc"}
        if subawards:
            body["subawards"] = True
        result = _post(body)
        rows.extend(result["results"])
        if not result.get("page_metadata", {}).get("hasNext"):
            break
        page += 1
        time.sleep(0.3)
    return rows


def awards(text):
    """Prime awards (contracts, IDVs, grants) whose recipient matches `text` (ideally a UEI)."""
    out = []
    for kind, codes in GROUPS.items():
        for row in _search(text, codes, FIELDS, "Award Amount"):
            out.append({"kind": kind, **row})
    return out


def subawards(text):
    """Subcontracts where the sub-awardee matches `text`, deduplicated (the API repeats some rows)."""
    seen, out = set(), []
    for row in _search(text, GROUPS["contract"], SUB_FIELDS, "Sub-Award Amount", subawards=True):
        key = (row["Sub-Award ID"], row["Sub-Award Date"], row["Sub-Award Amount"])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def award_url(generated_internal_id):
    return f"https://www.usaspending.gov/award/{generated_internal_id}"
