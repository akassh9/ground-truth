import json, sys, urllib.request, urllib.parse, collections
UA = {"User-Agent": "groundtruth-feasibility-check/0.1"}
def _open(req, timeout=90):
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)
def post(url, body):
    return _open(urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={**UA, "Content-Type": "application/json"}))
def get(url):
    return _open(urllib.request.Request(url, headers=UA))
def stac_search(endpoint, body, max_pages=40):
    feats, resp, page = [], post(endpoint + "/search", body), 0
    while True:
        feats += resp.get("features", []); page += 1
        nxt = [l for l in resp.get("links", []) if l.get("rel") == "next"]
        if not nxt or page >= max_pages: break
        l = nxt[0]
        if l.get("method", "GET").upper() == "POST":
            b = l.get("body") or {}
            b = {**body, **b} if (l.get("merge") or not b) else b
            resp = post(l["href"], b)
        else:
            resp = get(l["href"])
    return feats

# --- Overpass name lookup (light, single query) ---
oq = """[out:json][timeout:60];
(
 nwr["name"~"Anduril|Arsenal",i](39.70,-83.05,39.90,-82.80);
 nwr["operator"~"Anduril",i](39.70,-83.05,39.90,-82.80);
 nwr["name"~"Helion|Nixon Rapids|Rock Island Dam",i](47.25,-120.30,47.45,-120.00);
 nwr["name"~"General Matter|Gaseous Diffusion",i](37.0,-88.95,37.2,-88.65);
 nwr["name"~"Saronic|Port Alpha",i](25.80,-97.60,26.15,-97.10);
);
out center tags;"""
try:
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": oq}).encode(), headers=UA)
    od = _open(req)
    print("== OSM matches ==")
    for e in od["elements"]:
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        t = e.get("tags", {})
        keep = {k: t[k] for k in ("landuse","building","operator","construction","highway","man_made","power","industrial","start_date") if k in t}
        print(f"{e['type'][0]}{e['id']}  {t.get('name')!r}  {c.get('lat'):.5f},{c.get('lon'):.5f}  {keep}")
except Exception as ex:
    print("overpass error:", ex)

# --- STAC counts ---
sites = json.loads(sys.argv[1])
ES = "https://earth-search.aws.element84.com/v1"
PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
out = {}
for name, (lat, lon) in sites.items():
    pt = {"type": "Point", "coordinates": [lon, lat]}
    out[name] = {}
    print(f"\n== {name} ({lat},{lon}) ==")
    for label, ep, coll in [("ES s2-l2a", ES, "sentinel-2-l2a"), ("ES s2-c1-l2a", ES, "sentinel-2-c1-l2a"), ("PC s2-l2a", PC, "sentinel-2-l2a")]:
        body = {"collections": [coll], "intersects": pt, "datetime": "2024-01-01T00:00:00Z/2026-10-08T23:59:59Z",
                "query": {"eo:cloud_cover": {"lt": 20}}, "limit": 200,
                "fields": {"include": ["id", "properties.datetime", "properties.eo:cloud_cover", "properties.s2:mgrs_tile", "properties.grid:code"], "exclude": ["assets", "links", "geometry"]}}
        try:
            f = stac_search(ep, body)
        except Exception as ex:
            print(f"  {label}: ERROR {ex}"); continue
        dates = sorted({x["properties"]["datetime"][:10] for x in f})
        tiles = collections.Counter((x["properties"].get("s2:mgrs_tile") or x["properties"].get("grid:code") or x["id"].split("_")[1]) for x in f)
        byyear = collections.Counter(d[:4] for d in dates)
        bymonth = collections.Counter(d[:7] for d in dates)
        latest = sorted(f, key=lambda x: x["properties"]["datetime"])[-3:]
        print(f"  {label}: items={len(f)} unique_dates={len(dates)} by_year={dict(sorted(byyear.items()))} tiles={dict(tiles)}")
        print(f"    months_with_clear_scene={len(bymonth)} of 34; months: " + " ".join(f"{k[2:]}:{v}" for k, v in sorted(bymonth.items())))
        print("    latest: " + "; ".join(f"{x['id']} cc={x['properties']['eo:cloud_cover']:.1f}" for x in latest))
        out[name][label] = [{"id": x["id"], "dt": x["properties"]["datetime"], "cc": x["properties"]["eo:cloud_cover"]} for x in f]
    try:
        f = stac_search(PC, {"collections": ["naip"], "intersects": pt, "limit": 100,
                             "fields": {"include": ["id", "properties.datetime", "properties.gsd", "properties.naip:year"], "exclude": ["assets", "links", "geometry"]}})
        print("  PC naip: " + ", ".join(sorted(f"{x['properties']['datetime'][:10]}@{x['properties'].get('gsd')}m" for x in f)))
    except Exception as ex:
        print("  PC naip ERROR", ex)
json.dump(out, open(sys.argv[2], "w"))
