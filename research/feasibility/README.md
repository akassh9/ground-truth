# Ground Truth: data feasibility (probed 2026-10-08)

Three background checks probed which physical-world sources are usable this week. Marks: **(unverified)** = tried and couldn't confirm; † = from documentation, not verified live.

## 1. Filings, contracts and registries

| Verdict | Source | Notes |
|---|---|---|
| **Use, no key** | USAspending API | Contracts, grants, subcontracts; matched by UEI. Daily updates; search from FY2008. DoD awards appear ~90 days late†. |
| **Use, no key** | FAA aircraft registry (daily 72.8 MB zip) + Part 107 waiver table (`?saa_field_media_file=<name>`) | Clean owner names. N-number reservations are a leading signal. Experimental certs = certification code 4 in the master file. Drones under 55 lb are in a separate, non-public registry†. |
| **Use, no key, throttled** | Federal Register API | One integration covers NRC, DOE, DOJ consortium notices, PHMSA hazmat permits, arms sales, FERC. Blocked after ~10 quick calls ("Support Code 12"), so cache and poll slowly. |
| **Use, free key (Akash signs up)** | NRC ADAMS search API | New API returns 401 without a developer-portal subscription key; the old host adams.nrc.gov no longer resolves. |
| Optional | LBNL "Queued Up" (15.6 MB xlsx), ERCOT monthly report | Developer names mostly only in ERCOT (93.6%) and NYISO (100%). Little overlap with this portfolio. |
| Skip / manual | FCC equipment authorizations, ELS, ULS search, fccid.io, fcc.report | Akamai/Cloudflare block scripts; ELS errors (503). Official grantee list stops 2021-03-22. Manual browser lookups only. |
| Skip | SBIR.gov API (403), bulk CSV (367.6 MB, last updated 2026-01-01) | Use a USAspending keyword search instead. |
| Skip | SAM.gov API | Free key, but 10 requests/day without a role. |
| Skip | energy.gov / LPO, defense.gov, DIU, AFWERX, Blue UAS (DoD certs), CAISO | Blocked or not scriptable. |

What turned up:
- **Saronic** (UEI JZ14WLJDYM71): 2 contracts and 6 subcontracts, including a $29.0M Navy unmanned-boat (Corsair) contract on 2026-07-01 and a 2024 Lockheed Martin subcontract. Federal Register: 9 hits, mostly DOJ consortium-membership notices.
- **Anduril:** 293 contracts, 26 umbrella contracts and 108 subcontracts in USAspending (latest: CBP, $9.0M, 2026-08-25). 664 FAA registry records, which are N-number reservations (e.g., N1001C, N10044, reserved 2026-05-16, Costa Mesa). 14 Part 107 waivers, latest issued 2026-09-23. Federal Register: 22 hits, including a hazmat permit (2026-08-06) and an arms-sale notice (2026-07-22).
- **General Matter:** DOE enrichment master contracts (HALEU 2024-10-16, LEU 2024-12-10) and a $900M task order on 2026-03-15.
- **Helion:** a DOE grant in 2015 ($3.97M). No hits in the Federal Register.
- **Radiant:** a DOE grant in 2022 and Air Force microreactor contracts in 2021 and 2023.
- **Oklo, Kairos:** DOE awards 2020–23. Federal Register: Kairos 29 hits, Oklo 17.
- **Discovery leads** from USAspending keyword search: Velocor Industries (Air Force autonomous VTOL, $110K) and Empower Battery Technology (Air Force drone batteries, $75K).
- **Westmag: not found anywhere.** We need its legal entity name. **"Aeon"** is ambiguous and needs a legal name or UEI.

Red flags:
- **Name collisions:** "Helion Solar LLC", "TOKLO TECHNOLOGIES", "SARONIC INVESTMENTS LLC", and "general matter" as a common phrase. Match on UEI, CAGE code or address, not names.
- **Personal data:** waivers name a responsible person, and the registry lists individual owners. Keep both out of anything public.
- **Data quirks:** some waiver issue dates are in the future; Saronic's boat contract is coded as "intelligence support"; N-number reservations aren't aircraft.
- **Fragile sources:** cache snapshots and never call sources live during a demo.

## 2. Satellite imagery and site permits

Sites, bounding boxes [W,S,E,N] and timelines:
- **Anduril Arsenal-1**, Pickaway County, OH. Working bbox [-82.96, 39.77, -82.90, 39.81]; active graded site near 39.796, -82.915. **The exact parcel is unverified.** Check it against Pickaway County GIS (the CT Realty parcel); the area is full of look-alike warehouses.
  - Timeline: announced 2025-01-16; construction "quietly" from ~July 2025; production March 2026; first Fury 2026-07-27 (unverified).
- **Helion Orion**, 1476 Nixon Rapids Lane, Malaga, WA. Parcel 212205000050 (80 acres) near Rock Island Dam. Estimated bbox [-120.115, 47.320, -120.085, 47.345] (unverified).
  - Timeline: SEPA 25-139 approved May–June 2025; excavation under way by July 2025; announced 2025-07-30; county building permit October 2025; state Department of Health licenses June 2026.
- **General Matter**, Paducah, KY. "Leasing Parcel A" at the south end of the old gaseous diffusion plant. Bbox [-88.825, 37.095, -88.800, 37.107]; fresh bare soil near 37.101, -88.813.
  - Timeline: DOE lease and groundbreaking 2025-08-05; tree clearing ~February 2026; soil hauling since June 2026; DOE environmental finding EA-2327 ~July–August 2026; NRC licence application ~late September 2026 (unverified).
- **Saronic Port Alpha**, Port of Brownsville, TX. 835 acres, with an option on ~4,400. Groundbreaking 2026-09-30, so nothing is visible yet.

Free Sentinel-2 L2A (Earth Search STAC, cloud cover under 20%, 2024-01-01 to 2026-10-08):

| Site | Scenes | Months with a clear scene | Visible at 10 m? |
|---|---|---|---|
| Arsenal-1 | 59 | 25 of 34 | **Yes**: 775k–924k sq ft buildings, 500 acres of grading |
| Helion | 168 | 34 of 34 | Marginal: blends into the desert scrub |
| General Matter | 70 | 29 of 34 | **Yes, very obvious**: forest to bare dirt, no buildings yet |
| Saronic | 65 | 26 of 34 | Not yet |

- **Scene list:** `stac_items.json`. Previews: `previews/` (composite: top-left Arsenal-1, top-right Helion, bottom-left General Matter, bottom-right Saronic).
- **Frame URL pattern** (Planetary Computer, no login): `https://planetarycomputer.microsoft.com/api/data/v1/item/bbox/{W},{S},{E},{N}.png?collection=sentinel-2-l2a&item={id}&assets=visual&asset_bidx=visual|1,2,3&nodata=0&max_size=800`
- **Credit line:** "Contains modified Copernicus Sentinel data 2024–2026".
- **Free "before" frames:** NAIP aerial photos (public domain): OH 2023 at 0.3 m, WA 2023 at 0.6 m, KY 2022 at 0.6 m, TX 2022 at 0.6 m.
- **High-res, optional:**
  - SkyFi: self-serve, archive from $15/image, tasking from $200/image. Its publishing licence is ambiguous, so get permission in writing.
  - Vantor via SkyWatch: archive $14–25/km², 1 km² minimum (unverified for individuals).
  - EOS: SuperView-1 $14/km², GEOSAT-2 $5/km², 25 km² archive minimum.
  - Skip: UP42 (organizations only) and Planet's student program (non-commercial, up to 3 weeks).
  - Google Earth Pro historical imagery: free for non-commercial use with on-screen credit.
- **Permit sources:**
  - Ohio EPA eDocument Search. Lead: a 401 water-quality certification for Arsenal-1 on 2026-01-16 (from a third-party newsletter, so check it).
  - Pickaway County monthly permit PDFs. One entry: "Arsenal 1 phase 2 fire alarm", 2025-08-11 (unverified).
  - Chelan County SEPA 25-139 page; Washington Ecology SEPA Register.
  - Kentucky DEP Permit Search Online and eSearch; DOE EA-2327 and the Parcel A leasing package.
- **Recommended path:**
  - Headline: Arsenal-1, monthly frames from January 2024 to October 2026, opening on the 2023 NAIP aerial, with the filings laid over it.
  - Second: General Matter, with clearing visible ahead of the NRC licence.
  - Helion as the "harder case"; Saronic as "baseline captured, monitoring starts now".
  - Cost: $0 base, with an optional ~$150–1,000 for high-res start and end frames.

Sources: see the agent report in the session transcript. Key links:
- [NBC4: construction start](https://www.nbc4i.com/news/local-news/pickaway-county/anduril-quietly-starts-construction-on-ohio-arsenal-1-plant/)
- [JobsOhio: first Fury](https://www.jobsohio.com/newsroom/news-press/first-ohio-built-fury-rolls-off-andurils-arsenal-1-production-line)
- [Helion: starting to build](https://www.helionenergy.com/blog/starting-to-build-the-worlds-first-fusion-power-plant-in-malaga-wa)
- [Chelan County SEPA 25-139](https://co.chelan.wa.us/notifications/article/-fusion-energy-generation-project-studies)
- [World Nuclear News: General Matter at Paducah](https://www.world-nuclear-news.org/articles/general-matter-plans-new-enrichment-plant-in-paducah)
- [World Nuclear News: licence application](https://www.world-nuclear-news.org/articles/general-matter-submits-enrichment-plant-licence-application)
- [DOE finding, EA-2327](https://www.energy.gov/sites/default/files/2026-08/fonsi-ea-2327-gem-site-prep-licensing-parcel-a-2026-08.pdf)
- [Saronic Port Alpha groundbreaking](https://www.prnewswire.com/news-releases/saronic-breaks-ground-on-port-alpha-a-new-model-for-american-shipbuilding-302894975.html)
- [Ohio EPA eDocument Search](https://edocpub.epa.ohio.gov/publicportal/edochome.aspx)
- [SkyFi pricing](https://skyfi.com/en/pricing)
- [Earth Search STAC](https://earth-search.aws.element84.com/v1)

## 3. Import records and other signals

**Import records (US customs bills of lading):**
- **ImportYeti** has a free web search over US *sea* imports.
  - **Terms ban bots, data mining and commercial use**, and Cloudflare blocks scripts, so any work here is manual.
  - A 30-day Professional pass ($130) adds Power Query and CSV export. The API is Enterprise only, from $1,000/month.
  - Westmag list: **none of the named drone makers show Chinese motor imports.** Skydio's imports are mostly from Vietnam (packaging). Anduril has 25 sea shipments (batteries, antenna kits). BRINC and Shield AI aren't found.
  - Coverage is the core problem. Small motors arrive by air or courier, importers can hide their names, the importer on record is often a freight forwarder, and HS codes are noisy. NDAA-compliant defense makers avoid Chinese motors anyway.
- **ImportGenius:** ~$199/month. Fallback only.
- **Panjiva, Datamyne, Trademo:** quote-only, $10k+, with sales cycles longer than a week. Skip.
- **Decision:** build the Westmag prospect list from **defense procurement and hiring signals** (USAspending keyword search for sUAS, loitering munitions and UGVs; job boards; Federal Register), not from import records. If import records are used at all, they're a short, hand-checked side panel.

**Other free signals:**

| Signal | Status | Notes |
|---|---|---|
| SEC Form D (EDGAR) | Quarterly data sets 2008 Q1–2026 Q2 (latest updated 2026-07-09); full-text search from 2001 | The User-Agent must carry a name and contact email, so we need a dedicated project email (or Akash's OK). Limit 10 requests/second. Free funding ground truth. |
| Greenhouse / Lever / Ashby job boards | Verified, no key | Anduril 2,477 jobs (Greenhouse); Shield AI 594 (Lever, with pay bands); Skydio 153 and BRINC 34 (Ashby). |
| Wayback CDX | Works but flaky | 503s, and the availability API returned 429 after 2 calls. Keep to ~1 request/second with backoff. |
| Hacker News (Algolia) | Verified, no key | Weak for defense hardware. |
| GitHub API | 60 requests/hour without a key | A free token raises it to 5,000/hour. Limited value for hard tech. |
| PatentsView API | **Gone** (moved into USPTO's Open Data Portal on 2026-03-20; APIs "on hold") | Use the bulk tables or Google Patents on BigQuery. |
| Census trade API | Needs a free key | Market sizing only, no company names. |

**Commercial VC data, for evaluation only:**
- **Crunchbase Pro** is self-serve: ~$99 for a month, or $49/month on an annual plan. It exports 1,000–2,000 rows/month, and the trial allows no exports.
- PitchBook, Harmonic, Specter, Dealroom: sales-only and $12k+/year. Skip.

## Sign-ups only Akash can do

| Priority | What | Cost | Why |
|---|---|---|---|
| Now | NRC ADAMS developer key | $0 | Nuclear filings (General Matter, Radiant, Oklo) |
| Now | A project email, or OK to use the WashU one | $0 | Required by SEC EDGAR's User-Agent rule |
| Now | Crunchbase Pro, 1 month | ~$99 | Funding outcomes for the evaluation, and an "is it already funded?" check |
| Later | SkyFi high-res start and end frames | ~$150–1,000 | Only after the parcels are verified, and with publishing rights in writing |
| Optional | GitHub token, Census key | $0 | Higher limits |
| Skip | ImportYeti pass, Panjiva and other trade-data vendors, PitchBook | — | Terms of service, coverage, cost |
