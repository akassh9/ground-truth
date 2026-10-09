# Ground Truth

**What physical companies leave behind, and where the giants already are.**

The write-up, with every figure and the live Check: https://audience-of-one.vercel.app/ground-truth (the Check takes a
passcode, since every check costs real money). `gt/blog_export.py` copies the figures' data and the Check's backend
into the blog; `site/` is a standalone version of the same views.

VC data tools watch software signals: GitHub stars, web traffic, LinkedIn moves. Companies that build factories, ships and reactors leave a different trail:
- federal contracts
- FAA registrations
- NRC dockets
- hiring at new sites
- the ground itself, seen from orbit

Ground Truth reads that trail for Anti Fund's physical portfolio and for the incumbents around it. It turns the trail into a map of who is already entrenched in each lane, then runs every new company against that map.

Built in a week by Akash Khanikor as part of an application to Anti Fund (Member of Technical Staff / Associate).

## What it does

| Piece | What it answers | Code |
|---|---|---|
| **From orbit** | What is happening at the sites they're building? Monthly Sentinel-2 frames, NAIP "before" photos, and every filing on one timeline. | `gt/satellite.py` |
| **Signals** | What did each company do this month? Federal awards and subcontracts, FAA fleets and reservations, NRC filings, factory-floor and site hiring. All of it goes into one file, `data/signals.jsonl`, in a stable format other tools read. | `gt/signals.py` and one module per source |
| **The lane map** | In each lane of Anti Fund's thesis, who is already entrenched? An explainable score built only from public evidence. | `gt/lanes.py` |
| **Triage (System One)** | Which lane is this company in, who would it go head-on with, and does it sell into them? TypeSafe's Jev (`jev-1.13.0`) answers atomic typed questions with probabilities, and code combines the answers into a position and a call. 912 companies cost $0.08. | `gt/triage.py` |
| **The Check (System Two)** | Would this new company fight a giant, sell to one, or sit in open space? Or is its market off our map, so the map can't say? Does it conflict with the portfolio? Claude Haiku 5.5 returns a typed, cited verdict for about $0.0015, and every cited evidence id is verified against the map. Opus 5.5 runs only as the comparison grader. | `gt/check.py` |
| **Found in the record** | Which companies are forming right now? New NRC letters of intent, and new aircraft makers registering airframes with the FAA. | `gt/sourcing.py` |

## Sources (all public, all free)

| Source | Access | Used for |
|---|---|---|
| USAspending.gov | REST API, no key | contracts, contract vehicles, grants, subcontracts (matched by UEI) |
| FAA aircraft registry | daily 73 MB zip | registered fleets, reserved tail numbers, aircraft makers |
| NRC ADAMS public search | REST API, free key | dockets, letters of intent, license applications |
| Greenhouse, Lever, Ashby job boards | public JSON | open roles, factory-floor roles, hiring by site |
| Copernicus Sentinel-2, USDA NAIP | public STAC catalogs | site imagery |

Look-alike names are the main hazard. "SARONIC INVESTMENTS LLC" isn't Saronic; "HELION" sits inside "ANTHELION"; the `merge` job board belongs to Merge.dev. To guard against them:
- Every identifier in `data/entities.json` was checked by hand.
- Rejected look-alikes are listed so nobody adds them back.
- Matching uses UEIs, docket numbers and whole-word names, never substrings.

## The entrenchment score

| Evidence | Points |
|---|---|
| Federal awards since 2020 | ≥$1B: 5, ≥$100M: 3, ≥$10M: 2, ≥$1M: 1 |
| On a federal contract vehicle | 1 |
| Factory-floor hiring | ≥100 roles: 3, ≥25: 2, ≥5: 1 |
| FAA-registered fleet | ≥100 aircraft: 2, ≥10: 1 |
| NRC | license or construction permit held: 3, application: 2, active docket: 1 |
| A verified physical site we track | 2 |

**Tiers** (out of 16): 7 or more is entrenched, 4–6 is building, anything lower is early. Scores are per company, not per lane. The score measures what is on the ground and in the record, not valuation. A heavily funded company with little physical footprint scores low, and that is the point.

## Checks on the checker
- The Check may cite only evidence ids that exist in the lane map. `cited_ids_ok()` verifies every citation, and the evaluation reports how many were unknown.
- `gt/evaluate.py` runs the Check over a labeled test set (head-on, supplier, open) and reports agreement, citation validity and time per check.
- `gt/compare.py` puts the graders side by side: Akash's blind labels, Jev, Haiku and Opus. Calls are compared under one policy computed from each grader's position, so a disagreement means different judgment, not a different policy. Jev's probabilities are also scored with log-loss.
- Akash labeled 25 companies by hand before seeing any model output. When a model said head-on, he almost always agreed (Jev 8 of 9, Haiku 6 of 7, Opus 5 of 6). When a model said open, he mostly didn't: he could name a competitor the map doesn't track. So the Check now answers "off the map" when the map doesn't cover a market, instead of calling it open. Those 25 companies are never used for tuning.
- The position follows from the cited overlaps by fixed rules, enforced in code (`settle_position`), so a verdict can't contradict its own evidence. Only "open" versus "off the map" is left to the model.
- Names repeat (two different companies with the same name raised this year), so results are matched on name plus website.
- Fund policy lives in code, not in prompts: a company that goes head-on with a portfolio company is a pass (`fund_call`).
- Website text is treated as untrusted. The live endpoint only fetches public addresses, including after redirects, and caps input sizes.
- Private data (PitchBook exports) stays in `data/private/`, which is gitignored and never exported to the site.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install anthropic typesafe-sdk pillow numpy openpyxl
cp .env.example .env          # add NRC_APS_KEY, SEC_USER_AGENT, ANTHROPIC_API_KEY, TYPESAFE_API_KEY
.venv/bin/python -m gt.signals    # fetch and normalize every source
.venv/bin/python -m gt.lanes      # score entrenchment, build the lane map
.venv/bin/python -m gt.check "Company" https://company.com
.venv/bin/python -m gt.triage companies.json          # Jev first pass over a list
.venv/bin/python -m gt.evaluate companies.json        # Haiku verdicts, saved per company, resumable
.venv/bin/python -m gt.compare    # the graders side by side (private: reads data/private/)
.venv/bin/python -m gt.export     # copy public data into the site
.venv/bin/python -m gt.serve &    # local API for the live Check
npm --prefix site install && npm --prefix site run dev
```

## Layout

```
gt/            one module per source, plus lanes, check, sourcing, evaluate, export
data/          entities, incumbents, signals, lane map, frames (raw downloads in data/raw/, gitignored)
site/          Preact + Vite front end
api/check.py   Vercel function for the live Check
```
