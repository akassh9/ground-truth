import json, urllib.request, urllib.parse, time
UA = {"User-Agent": "groundtruth-feasibility-check/0.1 (light research use)"}
def get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)
# 1) Wikipedia coordinates
titles = ["Arsenal-1","Anduril Industries","Helion Energy","General Matter","Saronic Technologies","Paducah Gaseous Diffusion Plant","Rock Island Dam","Rickenbacker International Airport","Port of Brownsville"]
try:
    d = get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action":"query","prop":"coordinates","titles":"|".join(titles),"format":"json","redirects":1,"coprimary":"all"}))
    for p in d["query"]["pages"].values():
        print("WP", p.get("title"), [(c["lat"], c["lon"], c.get("primary","")) for c in p.get("coordinates", [])] or "no coords" if "missing" not in p else "MISSING")
    s = get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action":"query","list":"search","srsearch":"Arsenal-1 Anduril Pickaway","srlimit":3,"format":"json"}))
    print("WP search:", [x["title"] for x in s["query"]["search"]])
except Exception as ex: print("wikipedia error", ex)
# 2) Census geocoder for Helion address
try:
    g = get("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + urllib.parse.urlencode({"address":"1476 Nixon Rapids Lane, Malaga, WA 98828","benchmark":"Public_AR_Current","format":"json"}))
    print("Census:", [(m["matchedAddress"], m["coordinates"]) for m in g["result"]["addressMatches"]] or "no match")
except Exception as ex: print("census error", ex)
# 3) Nominatim (1 req/s)
for q in ["Nixon Rapids Lane, Malaga, Washington", "Anduril Arsenal-1, Ohio", "Rickenbacker Parkway, Pickaway County, Ohio"]:
    try:
        n = get("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 3}))
        print("Nominatim", repr(q), [(x["display_name"][:90], x["lat"], x["lon"], x.get("type")) for x in n] or "none")
    except Exception as ex: print("nominatim error", q, ex)
    time.sleep(1.2)
# 4) Overpass retry (alternate instance)
oq = """[out:json][timeout:40];
( nwr["name"~"Anduril|Arsenal-1",i](39.70,-83.05,39.90,-82.80);
  nwr["operator"~"Anduril",i](39.70,-83.05,39.90,-82.80);
  nwr["name"~"Helion|Nixon Rapids",i](47.25,-120.30,47.45,-120.00);
  nwr["name"~"General Matter",i](37.0,-88.95,37.2,-88.65);
  nwr["name"~"Saronic|Port Alpha",i](25.80,-97.60,26.15,-97.10); );
out center tags;"""
for ep in ["https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]:
    try:
        req = urllib.request.Request(ep, data=urllib.parse.urlencode({"data": oq}).encode(), headers=UA)
        with urllib.request.urlopen(req, timeout=45) as r: od = json.load(r)
        print("Overpass", ep)
        for e in od["elements"]:
            c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}; t = e.get("tags", {})
            print("  ", e["type"], e["id"], repr(t.get("name")), round(c["lat"],5), round(c["lon"],5), {k: t[k] for k in ("landuse","building","operator","highway","construction") if k in t})
        break
    except Exception as ex: print("overpass error", ep, ex)
