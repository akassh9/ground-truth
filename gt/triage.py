"""System One triage with TypeSafe's Jev: sort every company into a lane and a position, cheaply.

Jev (jev-1.13.0, pinned) answers typed questions with a probability for every option; it is built for
quick judgments that code acts on, not for extended reasoning (docs.typesafe.ai). Following TypeSafe's
guidance, every question is atomic and the facts are computed in code:
  1. lane: which lane of Anti Fund's thesis is the main product in? (Choice over the lanes, or none)
  2. focused on that lane: which established company sells the same kind of product to the same buyers?
     (Choice over the lane's companies, each described with its public evidence, or none); does the
     company sell into them? (Noul); does it claim an advantage they couldn't quickly copy? (Noul)
  3. asked on its own, so it can't pull answers away from question 2: do established companies already
     sell this kind of product at all? (Noul) If none on the map does, this separates open space from a
     market the map doesn't track ("off the map").
Position and call are then computed in code with the same rules the Claude Check follows, so the two
can be compared directly. Claude then writes cited verdicts only where they matter (gt/evaluate.py).

Answers are cached in data/private/jev_cache.jsonl; re-runs only send what's missing.
Usage: .venv/bin/python -m gt.triage data/private/pitchbook_clean.json [--lane-map path]
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy

from gt.env import DATA, load_env

MODEL = "jev-1.13.0"
CACHE = DATA / "private" / "jev_cache.jsonl"

LANE_Q = "Which of these sectors is this company's main product in? Judge by what it builds and sells."
HEAD_ON_Q = ("Which of these established companies sells the same kind of product as this company, to the same "
             "buyers? Choose none if none of them does.")
SELLS_Q = "This company sells parts, materials, software or services that established companies in its sector would buy."
WEDGE_Q = "The description claims a specific technical advantage that established companies could not quickly copy."
EXISTS_Q = "Established companies already sell this kind of product to these buyers."


def lanes_from(path):
    lane_map = json.loads(Path(path).read_text())
    descriptions = {c["slug"]: c["description"] for c in json.loads((DATA / "anti_portfolio.json").read_text())["companies"]}
    for lane in lane_map["lanes"]:
        for c in lane["companies"]:
            c["card"] = {"company": c["name"], "what_they_sell": c.get("why") or descriptions.get(c["slug"], ""),
                         "how_established": f"{c['tier']} (score {c['score']} of {lane_map['max_score']})",
                         "public_evidence": [f["text"] for f in c["facts"][:2]]}
    return {lane["slug"]: lane for lane in lane_map["lanes"]}


def lane_request(company, lanes):
    criteria = {slug: f"{lane['name']}: {lane['description']}" for slug, lane in lanes.items()}
    criteria["none"] = "None of these sectors: software only, consumer, services, or another industry."
    return {"state": {"company": company["name"], "description": company["about"]},
            "questions": {"lane": {"type": "choice", "instructions": LANE_Q, "criteria": criteria}}}


def focus_request(company, lane):
    questions = {
        "sells_to_them": {"type": "noul", "instructions": SELLS_Q,
                          "criteria": {"true": "It supplies components, materials, software or services to these companies.",
                                       "false": "It does not sell into them."}},
        "wedge": {"type": "noul", "instructions": WEDGE_Q,
                  "criteria": {"true": "It names a concrete technical advantage that would be hard to copy.",
                               "false": "No such advantage is described."}},
    }
    if lane["companies"]:
        criteria = {c["slug"]: c["card"] for c in lane["companies"]}
        criteria["none"] = "None of them sells the same kind of product to the same buyers."
        questions["head_on_with"] = {"type": "choice", "instructions": HEAD_ON_Q, "criteria": criteria}
    return {"state": {"company": company["name"], "description": company["about"], "sector": lane["name"]},
            "questions": questions}


def exists_request(company, lane):
    return {"state": {"company": company["name"], "description": company["about"], "sector": lane["name"]},
            "questions": {"incumbents_exist": {"type": "noul", "instructions": EXISTS_Q, "criteria": {
                "true": "Established, well-funded companies already sell this kind of product.",
                "false": "No established company sells this kind of product yet."}}}}


def key(request):
    return hashlib.sha1(json.dumps(request, sort_keys=True).encode()).hexdigest()


def load_cache():
    if not CACHE.exists():
        return {}
    return {row["key"]: row for row in map(json.loads, CACHE.read_text().splitlines())}


async def ask(requests, concurrency=24):
    """Send the requests that aren't cached yet; return {key: answers}."""
    cache = load_cache()
    todo = {key(r): r for r in requests if key(r) not in cache}
    if todo:
        load_env()
        gate = asyncio.Semaphore(concurrency)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncTypeSafeClient(api_key=os.environ["TYPESAFE_API_KEY"], retry=RetryPolicy(max_retries=5),
                                       timeout=60.0) as client:
            with CACHE.open("a") as out:
                async def one(k, req):
                    async with gate:
                        questions = {name: (Noul if q["type"] == "noul" else Choice)(instructions=q["instructions"],
                                                                                    criteria=q["criteria"])
                                     for name, q in req["questions"].items()}
                        resp = await client.system_one(req["state"], questions, model=MODEL)
                    answers = {name: {"noul": a.noul} if a.type == "noul" else
                               {"probabilities": a.probabilities, "choice": a.choice, "confidence": a.confidence}
                               for name, a in resp.answers.items()}
                    row = {"key": k, "model": resp.model, "answers": answers, "input_tokens": resp.usage.input_tokens}
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                    cache[k] = row

                first, *rest = todo.items()
                await one(*first)  # alone first, so a bad key or request shape fails fast
                await asyncio.gather(*(one(k, r) for k, r in rest))
    return {k: row for k, row in cache.items()}


def decide(company, lane, lane_p, focus, exists):
    """Position and call from Jev's answers, with the same rules as the Claude Check (gt/check.py)."""
    sells, wedge = focus["sells_to_them"]["noul"], focus["wedge"]["noul"]
    exists = exists["incumbents_exist"]["noul"]
    head = focus.get("head_on_with")
    p_none = head["probabilities"].get("none", 1.0) if head else 1.0
    rival = None
    if head:
        slug = max((s for s in head["probabilities"] if s != "none"), key=lambda s: head["probabilities"][s])
        rival = next(c for c in lane["companies"] if c["slug"] == slug)
    if rival and 1 - p_none >= 0.5:
        position = "head_on_with_entrenched" if rival["tier"] == "entrenched" else "head_on_with_building"
    elif sells >= 0.5:
        position = "complement"
    elif exists >= 0.5:
        position = "off_map"  # established sellers exist, but none is on the map, so the map can't call it open
    else:
        position = "white_space"
    conflict = bool(rival and rival["portfolio"] and position.startswith("head_on"))
    if conflict or (position == "head_on_with_entrenched" and wedge < 0.7):
        call = "pass"
    elif position == "white_space":
        call = "priority"
    else:
        call = "look"  # off_map included: the market needs checking outside the map
    return {"name": company["name"], "url": company.get("url", ""), "lane": lane["slug"], "lane_p": lane_p,
            "position": position, "call": call, "rival": rival["name"] if rival and position.startswith("head_on") else None,
            "portfolio_conflict": conflict, "sells_to_them": sells, "wedge": wedge,
            # probabilities for scoring against labels (head-on / supplier / open), plus the share the map can't judge
            "probs": {"head_on": 1 - p_none, "supplier": p_none * sells,
                      "open": p_none * (1 - sells) * (1 - exists), "off_map": p_none * (1 - sells) * exists}}


def triage(companies, lane_map_path=DATA / "lane_map.json"):
    lanes = lanes_from(lane_map_path)
    first = [lane_request(c, lanes) for c in companies]
    answers = asyncio.run(ask(first))
    results, focused = [], []
    for c, req in zip(companies, first):
        probs = answers[key(req)]["answers"]["lane"]["probabilities"]
        slug = max(probs, key=probs.get)
        if slug == "none":
            results.append({"name": c["name"], "url": c.get("url", ""), "lane": None, "lane_p": probs["none"],
                            "position": "out_of_scope", "call": "pass", "probs": None})
            continue
        focused.append((c, slug, probs[slug], focus_request(c, lanes[slug]), exists_request(c, lanes[slug])))
    answers = asyncio.run(ask([f[3] for f in focused] + [f[4] for f in focused]))
    for c, slug, p, focus, exists in focused:
        results.append(decide(c, lanes[slug], p, answers[key(focus)]["answers"], answers[key(exists)]["answers"]))
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("companies")
    ap.add_argument("--lane-map", default=str(DATA / "lane_map.json"))
    args = ap.parse_args()
    src = Path(args.companies)
    results = triage(json.loads(src.read_text()), args.lane_map)
    out = src.with_name(src.stem + "_triage.json")
    out.write_text(json.dumps(results, indent=1) + "\n")
    from collections import Counter
    print(f"{len(results)} companies -> {out}")
    print("positions:", dict(Counter(r["position"] for r in results).most_common()))
    print("calls:", dict(Counter(r["call"] for r in results).most_common()))
    tokens = sum(row.get("input_tokens", 0) for row in load_cache().values())
    print(f"Jev input tokens so far: {tokens:,} (about ${tokens * 0.042 / 1e6:.2f})")
