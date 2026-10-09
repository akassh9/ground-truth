"""Compare the graders: Akash's blind labels, Jev (System One), Claude Haiku 5.5 and Claude Opus 5.5.

- Jev vs Haiku on every company both judged: position, "does it fight a giant?", and the fund call.
- On the labeled sample: each model's agreement with Akash (head-on / supplier / open), plus Jev's
  log-loss from its probabilities, since Jev is the one grader that states its confidence. "Off the map"
  and "outside our lanes" aren't calls (the map can't judge them), so agreement counts only the companies
  a grader made a call on, and the rest are reported as no call.
- Cost and speed per model, and the market picture across all checked companies.
Calls are compared under one policy computed from each grader's position (POLICY), so call disagreements
reflect judgment rather than policy; head-on with a portfolio company is always a pass.

Usage: .venv/bin/python -m gt.compare   (writes data/private/compare.json; everything stays private)
"""
import csv
import json
import math
import re
import urllib.parse
from collections import Counter, defaultdict

from gt.check import context, fund_call, slugify
from gt.env import DATA

PRIVATE = DATA / "private"
LABEL = {"head_on_with_entrenched": "head_on", "head_on_with_building": "head_on", "complement": "supplier",
         "white_space": "open"}  # off_map and out_of_scope have no label: the map can't judge them
POLICY = {"head_on_with_entrenched": "pass", "head_on_with_building": "look", "complement": "look",
          "white_space": "priority", "off_map": "look", "out_of_scope": "pass"}
UNJUDGED = ("off_map", "out_of_scope")


def policy_call(position, conflicts):
    """The same call rule for every grader, so disagreements reflect judgment, not policy."""
    return "pass" if conflicts else POLICY[position]


PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-opus-5-5": (4.00, 20.00)}  # $ per million input / output tokens


def company_key(name, url):
    """Name plus website host. Names repeat in the export (two different companies share one name), so a name alone
    can match one company's verdict to another company."""
    host = urllib.parse.urlsplit(url if "//" in url else "//" + url).hostname or ""
    return slugify(name), host.removeprefix("www.")


def claude_results(folder):
    out = {}
    for path in folder.glob("[!_]*.json"):
        r = json.loads(path.read_text())
        if "verdict" in r:
            v = r["verdict"]
            position = "out_of_scope" if not v["lanes"] and v["position"] in ("white_space", "off_map") else v["position"]
            out[company_key(r["name"], r.get("url") or "")] = {"position": position, "call": policy_call(position, v["portfolio_conflicts"]),
                                       "own_call": fund_call(v), "usage": r.get("usage", {}),
                                       "seconds": r.get("seconds"), "lanes": v["lanes"], "conflicts": v["portfolio_conflicts"],
                                       "cited": sum(len(o["evidence_ids"]) for o in v["overlaps"]),
                                       "unknown_cited": r.get("unknown_citations", [])}
    return out


def jev_results():
    rows = json.loads((PRIVATE / "pitchbook_clean_triage.json").read_text())
    return {company_key(r["name"], r["url"]): {**r, "call": policy_call(r["position"], r.get("portfolio_conflict"))}
            for r in rows}


def labels():
    path = PRIVATE / "label_me.csv"
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            call = next((v for k, v in row.items() if k.startswith("your_call")), "").strip().lower().replace("-", "_")
            if call in ("head_on", "supplier", "open"):
                out[company_key(row["company"], row.get("website") or "")] = call
    return out


def cost(usage):
    pin, pout = PRICES[usage["model"]]
    return ((usage.get("input_tokens", 0) + 1.25 * usage.get("cache_write", 0)) * pin
            + usage.get("cache_read", 0) * pin * 0.1 + usage.get("output_tokens", 0) * pout) / 1e6


def jev_cost():
    """Dollar cost of the Jev questions behind the current triage. The cache also holds questions that a
    later version of gt/triage.py no longer asks, so summing the whole cache would overstate it."""
    from gt.triage import exists_request, focus_request, key, lane_request, lanes_from, load_cache
    lanes = lanes_from(DATA / "lane_map.json")
    lane_of = {company_key(r["name"], r["url"]): r["lane"]
               for r in json.loads((PRIVATE / "pitchbook_clean_triage.json").read_text())}
    requests = []
    for c in json.loads((PRIVATE / "pitchbook_clean.json").read_text()):
        requests.append(lane_request(c, lanes))
        if lane := lane_of.get(company_key(c["name"], c["url"])):
            requests += [focus_request(c, lanes[lane]), exists_request(c, lanes[lane])]
    cache = load_cache()
    return round(sum(cache[key(q)]["input_tokens"] for q in requests if key(q) in cache) * 0.042 / 1e6, 2)


def citations(graded):
    """Cited evidence ids that aren't in the lane map shown to the model: truncated (the start of exactly one id it
    was shown, like a fact id missing its date), miscopied (not shown, but a real record in our public data, such
    as a sibling contract number) and invented (nowhere at all)."""
    known = set(re.findall(r"^\s*- \[([^\]]+)\]", context(), flags=re.M))
    record = (DATA / "signals.jsonl").read_text()
    unknown = [i for r in graded.values() for i in r["unknown_cited"]]
    truncated = [i for i in unknown if len([k for k in known if k.startswith(i)]) == 1]
    miscopied = [i for i in unknown if i not in truncated and ":" in i and i.split(":", 1)[1] in record]
    return {"total": sum(r["cited"] for r in graded.values()), "truncated": len(truncated), "miscopied": len(miscopied),
            "invented": len(unknown) - len(truncated) - len(miscopied)}


def agreement(pairs):
    pairs = list(pairs)
    return {"n": len(pairs), "agree": sum(a == b for a, b in pairs),
            "rate": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None}


def main():
    jev, checked = jev_results(), claude_results(PRIVATE / "checks")  # checked: Haiku, plus Opus where Haiku refused
    haiku = {k: r for k, r in checked.items() if r["usage"]["model"] == "claude-haiku-5-5"}
    opus = claude_results(PRIVATE / "checks" / "compare-claude-opus-5-5")
    both = [k for k in haiku if k in jev]
    report = {"jev_vs_haiku": {
        "position": agreement((jev[k]["position"], haiku[k]["position"]) for k in both),
        "fights_a_giant": agreement((jev[k]["position"].startswith("head_on"), haiku[k]["position"].startswith("head_on")) for k in both),
        "call": agreement((jev[k]["call"], haiku[k]["call"]) for k in both),
        "confusion": Counter(f"jev {jev[k]['position']} / haiku {haiku[k]['position']}" for k in both).most_common(12),
    }}

    gold = labels() if (PRIVATE / "label_me.csv").exists() else {}
    if gold:
        table = {}
        for name, graded in (("jev", jev), ("haiku", haiku), ("opus", opus)):
            keys = [k for k in gold if k in graded and graded[k]["position"] in LABEL]
            table[name] = {**agreement((gold[k], LABEL[graded[k]["position"]]) for k in keys),
                           "no_call": Counter(graded[k]["position"] for k in gold if k in graded and graded[k]["position"] in UNJUDGED)}
        keys = [k for k in gold if k in jev and jev[k].get("probs")]
        if keys:  # Jev states probabilities (only for companies it puts in a lane); score them
            table["jev"]["log_loss"] = round(sum(-math.log(max(jev[k]["probs"][gold[k]], 1e-6)) for k in keys) / len(keys), 3)
            table["jev"]["log_loss_n"] = len(keys)
        table["labeled"] = len(gold)
        table["companies"] = [{"company": k[0], "akash": gold[k],
                               **{name: graded[k]["position"] if k in graded else None
                                  for name, graded in (("jev", jev), ("haiku", haiku), ("opus", opus))},
                               "jev_p_akash": round(jev[k]["probs"][gold[k]], 3) if k in jev and jev[k].get("probs") else None}
                              for k in gold]
        report["vs_akash"] = table

    seconds = sorted(r["seconds"] for r in haiku.values() if r["seconds"])
    report["cost_and_speed"] = {
        "jev": {"companies": len(jev), "usd": jev_cost()},
        "haiku": {"companies": len(haiku), "usd": round(sum(cost(r["usage"]) for r in haiku.values()), 2),
                  "median_seconds": seconds[len(seconds) // 2] if seconds else None},
        "opus": {"companies": len(opus), "usd": round(sum(cost(r["usage"]) for r in opus.values()), 2),
                 "median_seconds": sorted(r["seconds"] for r in opus.values() if r["seconds"])[len(opus) // 2] if opus else None},
    }
    # every cited evidence id must exist in the lane map; a refusal is a Haiku verdict that Opus had to give
    report["citations"] = {"haiku": citations(haiku), "opus": citations(opus)}
    report["refused_by_haiku"] = len(checked) - len(haiku)

    in_thesis = {k: r for k, r in checked.items() if r["position"] != "out_of_scope"}
    by_lane = defaultdict(Counter)
    for r in in_thesis.values():
        for lane in r["lanes"][:1]:
            by_lane[lane][r["position"] if r["position"].startswith("head_on") else LABEL.get(r["position"], r["position"])] += 1
    report["market"] = {
        "checked": len(checked), "in_thesis": len(in_thesis),
        "positions": Counter(r["position"] for r in in_thesis.values()),
        "portfolio_conflicts": sum(1 for r in in_thesis.values() if r["conflicts"]),
        "by_lane": {lane: dict(c) for lane, c in sorted(by_lane.items(), key=lambda kv: -sum(kv[1].values()))},
    }
    (PRIVATE / "compare.json").write_text(json.dumps(report, indent=1, default=dict) + "\n")
    print(json.dumps(report, indent=1, default=dict))


if __name__ == "__main__":
    main()
