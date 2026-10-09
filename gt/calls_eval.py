"""Grade the Check's money read: are the calls it picks ones the company could really answer?

Claude Opus 5.5 grades each picked call on its own, seeing only the company's description and the call's listing,
not Haiku's reason for picking it. Also counts how call ids were spelled (exact, repaired by calls.resolve, or
unknown) and how often the spending search found anything.

Usage: .venv/bin/python -m gt.calls_eval data/private/checks-money [data/checks ...]
Writes <first dir>/_calls_eval.json. Grading a private run stays private; publish totals only.
"""
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from gt.check import client

GRADER = "claude-opus-5-5"


class Grade(BaseModel):
    answer: Literal["yes", "no", "unclear"] = Field(description="unclear only when the listing is too thin to tell")
    reason: str = Field(description="One plain sentence")


def grade(company, call):
    listing = "\n".join(f"{k}: {call[k]}" for k in ("agency", "kind", "status", "opens", "closes", "title", "funding",
                                                     "keywords", "summary") if call.get(k))
    response = client().beta.messages.parse(
        model=GRADER, max_tokens=4000, output_format=Grade,
        messages=[{"role": "user", "content": (
            "Could this company credibly submit a proposal or application to this government call, with what it "
            "builds now or a direct extension of it? Small businesses only for SBIR/STTR topics; judge eligibility "
            "and technical fit, not odds of winning.\n\n"
            f"<company>\n{company['name']}: {company.get('about') or company['verdict']['what_it_builds']}\n</company>\n\n"
            f"<call>\n{listing}\n</call>")}])
    return response.parsed_output


def spelling(raw_id, resolved_ids):
    raw = raw_id.strip().strip("[]").strip()
    if raw in resolved_ids:
        return "exact"
    return "repaired" if any(raw.lower().endswith(r.lower()) for r in resolved_ids) else "unknown"


def main():
    dirs = [Path(p) for p in sys.argv[1:]]
    results = [json.loads(p.read_text()) for d in dirs for p in sorted(d.glob("[!_]*.json"))]
    results = [r for r in results if "verdict" in r]
    pairs = [(r, c) for r in results for c in r.get("calls", [])]
    with ThreadPoolExecutor(4) as pool:
        grades = list(pool.map(lambda rc: grade(*rc), pairs))
    by_fit = Counter((c["fit"], g.answer) for (_, c), g in zip(pairs, grades))
    spelled = Counter(spelling(raw["id"], {c["id"] for c in r["calls"]}) for r in results for raw in r["verdict"]["calls"])
    found = [r for r in results if (r.get("market") or {}).get("total", 0) >= 100_000]
    report = {
        "checks": len(results),
        "with_calls": sum(1 for r in results if r.get("calls")),
        "picks": len(pairs),
        "grades": {f"{fit}/{answer}": n for (fit, answer), n in sorted(by_fit.items())},
        "precision": {fit: f"{by_fit[(fit, 'yes')]}/{sum(n for (f, _), n in by_fit.items() if f == fit)}"
                      for fit in ("strong", "possible")},
        "id_spelling": dict(spelled),
        "spending_found": f"{len(found)}/{len(results)}",
        "details": [{"company": r["name"], "call": c["id"], "fit": c["fit"], "grade": g.answer, "reason": g.reason}
                    for (r, c), g in zip(pairs, grades)],
    }
    out = dirs[0] / "_calls_eval.json"
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "details"}, indent=1))


if __name__ == "__main__":
    main()
