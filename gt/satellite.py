"""Sentinel-2 monthly frames and a NAIP "before" frame for each watched site (data/sites.json).

Everything comes from Microsoft Planetary Computer (PC), no key or login. Learned by probing on
2026-10-08:
- STAC: POST https://planetarycomputer.microsoft.com/api/stac/v1/search. Sentinel-2 L2A items have
  proj:epsg, eo:cloud_cover and ids like S2C_MSIL2A_20260925T162021_R040_T17TLE_20260925T195353
  (tile, then processing time). One pass can give a tile two items, each covering only part of it,
  so we keep only items whose footprint contains the whole crop. PC lists scenes about a week after
  Earth Search does, so the current month may still be empty.
- Data API (TiTiler): GET /api/data/v1/item/bbox/{minx},{miny},{maxx},{maxy}/{w}x{h}.png with
  collection, item, assets, coord_crs and dst_crs renders a crop in any CRS. We use the site's UTM
  zone. Tile origins sit on a 20 m grid, so a crop snapped to 20 m at 10 m/px returns Sentinel-2's
  own pixels, unresampled. "visual" is the L2A true-colour image with fixed 8-bit scaling, so colours
  compare across dates and the 2022 reflectance offset doesn't apply.
- POST /api/data/v1/item/statistics?assets=SCL&categorical=true&c=0..11 with a GeoJSON Feature (in
  coord_crs) counts scene-classification pixels per class over the crop in under a second:
  properties.statistics.SCL_b1.histogram = [counts, classes]. Cloud here means classes 3 (shadow),
  8, 9 (cloud) and 10 (cirrus). SCL can miss small bright cumulus over pale winter fields (Arsenal-1,
  2024-02-03: a visible cloud, 0.19% flagged), so the estimate is a floor.
- A request that reads too many source pixels times out (504 at ~60 s). A 3420x2780 px NAIP crop at
  1 m (0.3 m source) failed, while 1000 px chunks take ~2.5 s. NAIP items are quarter-quads
  (~5.5 x 7 km, overlapping ~500 m) in NAD83 UTM, ~1 m from WGS 84 here. So NAIP is fetched in
  chunks per item and stitched with Pillow, the only non-stdlib dependency (installed in .venv).

Usage (after `source .venv/bin/activate`, or call .venv/bin/python):
  python3 -m gt.satellite frames arsenal-1               # Jan 2024 to now, plus NAIP
  python3 -m gt.satellite frames helion-orion --latest   # latest clear month, plus NAIP
  python3 -m gt.satellite preview arsenal-1              # preview.mp4 (ffmpeg) or preview.gif
Writes data/frames/<site>/<YYYY-MM>.png, naip-<year>.png and manifest.json. Raw responses are cached
in data/raw/satellite/. A scene search is cached per day; crops and statistics are cached for good.
"""
import hashlib
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from gt.env import DATA, ROOT

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
TILER = "https://planetarycomputer.microsoft.com/api/data/v1"
RAW = DATA / "raw" / "satellite"
FRAMES = DATA / "frames"
UA = {"User-Agent": "ground-truth-research/0.1"}
START = "2024-01"
S2_M = 10  # Sentinel-2 frame pixel, metres
GRID_M = 20  # crops snap outward to this grid (Sentinel-2 10 m and 20 m pixels)
NAIP_M = 1.0  # NAIP frame pixel (source 0.3-0.6 m); coarser if the crop is wider than NAIP_MAX_PX
NAIP_MAX_PX = 4000
CHUNK = 1000  # max pixels per side in one data API request
MAX_CLOUD = 5.0  # % of the crop; months whose clearest scene is cloudier get no frame
MAX_CHECKS = 8  # SCL checks per month, in order of scene-level cloud cover
MAX_SNOW = 25.0  # % of the crop; preview() skips snowier frames (they flash white), the manifest keeps them
CLOUD, SNOW = (3, 8, 9, 10), 11
PAUSE, TRIES, RETRY = 0.3, 5, (429, 500, 502, 503, 504)
PREVIEW_W = 960


# --- WGS 84 / UTM, Krueger series (Karney 2011); matches pyproj to 0.1 mm at our sites ---
_F = 1 / 298.257223563
_N = _F / (2 - _F)
_R = 0.9996 * 6378137.0 / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64)
_ALPHA = (_N / 2 - 2 * _N**2 / 3 + 5 * _N**3 / 16, 13 * _N**2 / 48 - 3 * _N**3 / 5, 61 * _N**3 / 240)
_BETA = (_N / 2 - 2 * _N**2 / 3 + 37 * _N**3 / 96, _N**2 / 48 + _N**3 / 15, 17 * _N**3 / 480)
_DELTA = (2 * _N - 2 * _N**2 / 3 - 2 * _N**3, 7 * _N**2 / 3 - 8 * _N**3 / 5, 56 * _N**3 / 15)


def to_utm(lon, lat, epsg):
    """Easting, northing of a WGS 84 point in the UTM zone of `epsg` (326zz north, 327zz south)."""
    lam, phi = math.radians(lon - (epsg % 100 * 6 - 183)), math.radians(lat)
    c = 2 * math.sqrt(_N) / (1 + _N)
    t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
    xi, eta = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    e = eta + sum(a * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, a in enumerate(_ALPHA, 1))
    n = xi + sum(a * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, a in enumerate(_ALPHA, 1))
    return 500000 + _R * e, (1e7 if epsg >= 32700 else 0) + _R * n


def from_utm(x, y, epsg):
    """WGS 84 lon, lat of a UTM point."""
    xi, eta = (y - (1e7 if epsg >= 32700 else 0)) / _R, (x - 500000) / _R
    xi2 = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta2 = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    chi = math.asin(math.sin(xi2) / math.cosh(eta2))
    lat = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(_DELTA, 1))
    return epsg % 100 * 6 - 183 + math.degrees(math.atan2(math.sinh(eta2), math.cos(xi2))), math.degrees(lat)


# --- sites and crop geometry ---
def load_site(slug):
    sites = json.loads((DATA / "sites.json").read_text())["sites"]
    site = next((s for s in sites if s["slug"] == slug), None)
    if site is None:
        sys.exit(f"unknown site {slug!r}; known: {', '.join(s['slug'] for s in sites)}")
    return site


def extent(site):
    """UTM bounds [minx, miny, maxx, maxy] covering the site's lon/lat bbox, snapped out to GRID_M."""
    w, s, e, n = site["bbox"]
    pts = [to_utm(lon, lat, site["epsg"]) for lon in (w, (w + e) / 2, e) for lat in (s, (s + n) / 2, n)]
    lo = lambda v: math.floor(v / GRID_M) * GRID_M
    hi = lambda v: math.ceil(v / GRID_M) * GRID_M
    return [lo(min(p[0] for p in pts)), lo(min(p[1] for p in pts)), hi(max(p[0] for p in pts)), hi(max(p[1] for p in pts))]


def lonlat_ring(ext, epsg, per_side=4):
    """Closed lon/lat ring along the crop's edges, for STAC searches and footprint checks."""
    x0, y0, x1, y1 = ext
    steps = [i / per_side for i in range(per_side)]
    xy = ([(x0 + (x1 - x0) * t, y0) for t in steps] + [(x1, y0 + (y1 - y0) * t) for t in steps]
          + [(x1 - (x1 - x0) * t, y1) for t in steps] + [(x0, y1 - (y1 - y0) * t) for t in steps])
    ring = [list(from_utm(x, y, epsg)) for x, y in xy]
    return ring + [ring[0]]


def _inside(x, y, ring):
    inside = False
    for a, b in zip(ring, ring[1:]):
        if (a[1] > y) != (b[1] > y) and x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
            inside = not inside
    return inside


def covers(geometry, ring):
    """True if every point of `ring` lies inside the (Multi)Polygon footprint."""
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return all(any(_inside(x, y, p[0]) for p in polys) for x, y in ring[:-1])


def months_between(first, last):
    """['2024-01', ..., last] as YYYY-MM strings."""
    y, m = map(int, first.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# --- HTTP with cache and backoff ---
def _fetch(url, body=None, kind="misc", name=""):
    """Bytes of GET `url` (POST if `body`), cached in data/raw/satellite/<kind>/; retries on 429/5xx."""
    key = hashlib.sha1(f"{url} {json.dumps(body, sort_keys=True)}".encode()).hexdigest()[:12]
    suffix = "png" if ".png?" in url else "json"
    path = RAW / kind / (f"{name}-{key}.{suffix}" if name else f"{key}.{suffix}")
    if path.exists():
        return path.read_bytes()
    data = json.dumps(body).encode() if body is not None else None
    headers = {**UA, "Content-Type": "application/json"} if body is not None else UA
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=120) as resp:
                content = resp.read()
            break
        except urllib.error.HTTPError as err:
            if err.code not in RETRY or attempt == TRIES - 1:
                raise
            retry_after = err.headers.get("Retry-After", "")
            wait = float(retry_after) if retry_after.isdigit() else 3 * 2**attempt
        except (urllib.error.URLError, TimeoutError):
            if attempt == TRIES - 1:
                raise
            wait = 3 * 2**attempt
        time.sleep(wait)
    time.sleep(PAUSE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def stac_search(body, name):
    """All features of a STAC search, following "next" links (PC pages by POST with a token)."""
    feats, page = [], json.loads(_fetch(STAC + "/search", body, "stac", name))
    while True:
        feats += page["features"]
        link = next((l for l in page.get("links", []) if l.get("rel") == "next"), None)
        if link is None:
            return feats
        if link.get("method", "GET").upper() == "POST":
            nxt = link.get("body") or {}
            page = json.loads(_fetch(link["href"], {**body, **nxt} if link.get("merge") or not nxt else nxt, "stac", name))
        else:
            page = json.loads(_fetch(link["href"], None, "stac", name))


# --- scenes and cloud over the crop ---
def s2_scenes(ext, epsg, start, end):
    """Sentinel-2 L2A scenes in the site's UTM zone whose footprint covers the whole crop, oldest first."""
    ring = lonlat_ring(ext, epsg)
    body = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Polygon", "coordinates": [ring]},
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "query": {"proj:epsg": {"eq": epsg}, "eo:cloud_cover": {"lt": 95}},
        "limit": 500,
        "fields": {"include": ["id", "geometry", "properties.datetime", "properties.eo:cloud_cover",
                               "properties.s2:mean_solar_zenith"], "exclude": ["assets", "links"]},
    }
    scenes = {}
    for f in stac_search(body, f"s2-{epsg}-{end}"):
        if not covers(f["geometry"], ring):
            continue
        p, parts = f["properties"], f["id"].split("_")
        key = (p["datetime"][:16], parts[4])  # one pass over one tile; keep the latest processing
        if key not in scenes or scenes[key]["id"] < f["id"]:
            scenes[key] = {"id": f["id"], "acquired": p["datetime"], "scene_cloud": round(p["eo:cloud_cover"], 2),
                           "sun_elevation": round(90 - p.get("s2:mean_solar_zenith", 90), 1)}
    return sorted(scenes.values(), key=lambda s: s["acquired"])


def crop_cloud(item_id, ext, epsg):
    """Cloud, snow and no-data shares (%) of the crop, from the scene classification (SCL) band."""
    x0, y0, x1, y1 = ext
    feature = {"type": "Feature", "properties": {},
               "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}}
    query = [("collection", "sentinel-2-l2a"), ("item", item_id), ("assets", "SCL"), ("coord_crs", f"epsg:{epsg}"),
             ("dst_crs", f"epsg:{epsg}"), ("categorical", "true")] + [("c", c) for c in range(12)]
    stats = json.loads(_fetch(f"{TILER}/item/statistics?{urllib.parse.urlencode(query)}", feature, "scl", item_id))
    band = stats["properties"]["statistics"]["SCL_b1"]
    counts = dict(zip(band["histogram"][1], band["histogram"][0]))
    total = band["valid_pixels"] + band["masked_pixels"]
    share = lambda n: round(100 * n / total, 2)
    return share(sum(counts.get(c, 0) for c in CLOUD)), share(counts.get(SNOW, 0)), share(band["masked_pixels"] + counts.get(0, 0))


def pick(scenes, ext, epsg, months, latest=False):
    """Clearest scene per month over the crop -> (picks, missing reasons). `latest`: stop at the first pick."""
    by_month = {}
    for s in scenes:
        by_month.setdefault(s["acquired"][:7], []).append(s)
    picks, missing = {}, {}
    for month in months:
        candidates = sorted(by_month.get(month, []), key=lambda s: s["scene_cloud"])
        checked = []
        for s in candidates[:MAX_CHECKS]:
            s["cloud"], s["snow"], nodata = crop_cloud(s["id"], ext, epsg)
            if nodata == 0:
                checked.append(s)
                if s["cloud"] + s["snow"] <= 0.5:
                    break
        clear = [s for s in checked if s["cloud"] <= MAX_CLOUD]
        if clear:
            picks[month] = min(clear, key=lambda s: (s["cloud"] + s["snow"], s["scene_cloud"]))
            if latest:
                break
        elif checked:
            best = min(checked, key=lambda s: s["cloud"])
            missing[month] = (f"cloudy: {len(candidates)} scenes, clearest of {len(checked)} checked has "
                              f"{best['cloud']}% cloud over the crop ({best['id']}, {best['acquired'][:10]})")
        elif candidates:
            missing[month] = "no scene with full coverage of the crop"
        else:
            missing[month] = "no scene on Planetary Computer" + (
                " yet (PC lists scenes about a week after acquisition)" if month == date.today().isoformat()[:7] else "")
    return picks, missing


# --- rendering ---
def _pil():
    """Pillow's Image, ImageDraw and ImageFont, or a clear exit if it isn't installed."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        sys.exit("Pillow is needed to stitch NAIP chunks and draw previews: "
                 "python3 -m venv .venv && .venv/bin/pip install pillow, then source .venv/bin/activate")
    return Image, ImageDraw, ImageFont


def _bbox_png(item_id, bounds, w, h, query):
    coords = ",".join(f"{v:.2f}" for v in bounds)
    url = f"{TILER}/item/bbox/{coords}/{w}x{h}.png?" + urllib.parse.urlencode(query + [("item", item_id)])
    return _fetch(url, None, "png", item_id)


def render(collection, items, ext, epsg, size, assets, bidx=None):
    """PNG bytes of the crop at `size` (w, h). `items` is [(id, utm_bounds or None)]. One small item is a
    single request; larger crops or several items are fetched in chunks and stitched with Pillow."""
    w, h = size
    query = [("collection", collection), ("assets", assets), ("coord_crs", f"epsg:{epsg}"), ("dst_crs", f"epsg:{epsg}")]
    query += [("asset_bidx", bidx)] if bidx else []
    if len(items) == 1 and max(w, h) <= CHUNK:
        return _bbox_png(items[0][0], ext, w, h, query + [("return_mask", "false")])
    Image = _pil()[0]
    canvas = Image.new("RGBA", (w, h))
    sx, sy = (ext[2] - ext[0]) / w, (ext[3] - ext[1]) / h
    for top in range(0, h, CHUNK):
        for left in range(0, w, CHUNK):
            cw, ch = min(CHUNK, w - left), min(CHUNK, h - top)
            sub = (ext[0] + left * sx, ext[3] - (top + ch) * sy, ext[0] + (left + cw) * sx, ext[3] - top * sy)
            for item_id, b in items:
                if b and (b[0] >= sub[2] or b[2] <= sub[0] or b[1] >= sub[3] or b[3] <= sub[1]):
                    continue
                try:
                    piece = _bbox_png(item_id, sub, cw, ch, query)
                except urllib.error.HTTPError as err:
                    if err.code == 404:  # chunk outside this item
                        continue
                    raise
                canvas.alpha_composite(Image.open(io.BytesIO(piece)).convert("RGBA"), (left, top))
    if canvas.getextrema()[3][0] == 255:
        canvas = canvas.convert("RGB")
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return buf.getvalue()


def naip_items(ext, epsg):
    """(year, [(id, utm_bounds, date)]) for the latest NAIP year overlapping the crop."""
    ring = lonlat_ring(ext, epsg)
    feats = stac_search({"collections": ["naip"], "intersects": {"type": "Polygon", "coordinates": [ring]}, "limit": 500,
                         "fields": {"include": ["id", "bbox", "properties.datetime"], "exclude": ["assets", "links"]}},
                        f"naip-{epsg}")
    year = max(f["properties"]["datetime"][:4] for f in feats)
    items = []
    for f in sorted(feats, key=lambda f: f["id"]):
        if f["properties"]["datetime"][:4] == year:
            w, s, e, n = f["bbox"]
            pts = [to_utm(lon, lat, epsg) for lon in (w, e) for lat in (s, n)]
            b = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            items.append((f["id"], b, f["properties"]["datetime"][:10]))
    return year, items


# --- commands ---
def frames(slug, latest=False):
    """Write the site's Sentinel-2 frames, the NAIP frame and manifest.json."""
    site = load_site(slug)
    if not site["verified"]:
        print(f"warning: {slug} is unverified ({site['bbox_kind']}); frames are context, not the site", file=sys.stderr)
    epsg, ext = site["epsg"], extent(site)
    out = FRAMES / slug
    out.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    months = months_between(START, today[:7])
    if latest:
        months = months[::-1][:4]
    scenes = s2_scenes(ext, epsg, min(months) + "-01", today)
    picks, missing = pick(scenes, ext, epsg, months, latest)

    size = (round((ext[2] - ext[0]) / S2_M), round((ext[3] - ext[1]) / S2_M))
    entries = []
    for month, s in sorted(picks.items()):
        (out / f"{month}.png").write_bytes(render("sentinel-2-l2a", [(s["id"], None)], ext, epsg, size, "visual"))
        entries.append({"file": f"{month}.png", "month": month, "acquired": s["acquired"], "scene_id": s["id"],
                        "collection": "sentinel-2-l2a", "cloud_pct": s["cloud"], "snow_pct": s["snow"],
                        "scene_cloud_pct": s["scene_cloud"], "sun_elevation_deg": s["sun_elevation"],
                        "credit": f"Contains modified Copernicus Sentinel data {month[:4]}"})
        print(f"{month}  {s['acquired'][:10]}  cloud {s['cloud']:>5}%  {s['id']}")
    for month, why in sorted(missing.items()):
        print(f"{month}  missing: {why}")

    year, items = naip_items(ext, epsg)
    used = [i for i in items if not (i[1][0] >= ext[2] or i[1][2] <= ext[0] or i[1][1] >= ext[3] or i[1][3] <= ext[1])]
    px = max(NAIP_M, math.ceil(max(ext[2] - ext[0], ext[3] - ext[1]) / NAIP_MAX_PX * 2) / 2)
    naip_size = (round((ext[2] - ext[0]) / px), round((ext[3] - ext[1]) / px))
    (out / f"naip-{year}.png").write_bytes(render("naip", [(i, b) for i, b, _ in used], ext, epsg, naip_size, "image", "image|1,2,3"))
    dates = sorted({d for _, _, d in used})
    entries.insert(0, {"file": f"naip-{year}.png", "month": dates[0][:7], "acquired": dates[0] if len(dates) == 1 else f"{dates[0]}/{dates[-1]}",
                       "scene_id": "+".join(i for i, _, _ in used), "collection": "naip", "cloud_pct": None, "pixel_m": px,
                       "credit": f"NAIP {year}: USDA Farm Production and Conservation Business Center (public domain)"})
    print(f"naip-{year}.png  {naip_size[0]}x{naip_size[1]} px at {px} m from {len(used)} item(s)")

    path = out / "manifest.json"
    if latest and path.exists():  # keep earlier frames of a full run
        old = json.loads(path.read_text())
        files = {e["file"] for e in entries}
        entries += [e for e in old["frames"] if e["file"] not in files]
        missing = {**{m["month"]: m["reason"] for m in old.get("missing", [])}, **missing}
    have = {e["month"] for e in entries if e["collection"] == "sentinel-2-l2a"}
    x0, y0, x1, y1 = ext
    manifest = {
        "site": slug, "label": site["label"], "company": site["company"], "verified": site["verified"],
        "bbox_kind": site["bbox_kind"], "generated": today, "crs": f"EPSG:{epsg}", "bounds": ext,
        "corners_lonlat": [[round(v, 6) for v in from_utm(x, y, epsg)] for x, y in ((x0, y1), (x1, y1), (x1, y0), (x0, y0))],
        "sentinel2_size": list(size), "sentinel2_pixel_m": S2_M, "max_cloud_pct": MAX_CLOUD,
        "frames": sorted(entries, key=lambda e: (e["collection"] != "naip", e["month"])),
        "missing": [{"month": m, "reason": r} for m, r in sorted(missing.items()) if m not in have],
    }
    path.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{len(have)} Sentinel-2 frames + NAIP {year} -> {path.relative_to(ROOT)}")


def preview(slug, fps=3):
    """Animate NAIP then the monthly frames (minus snow-covered ones), labelled, into preview.mp4 (ffmpeg)
    or preview.gif (Pillow)."""
    Image, ImageDraw, ImageFont = _pil()
    out = FRAMES / slug
    man = json.loads((out / "manifest.json").read_text())
    seq = [f for f in man["frames"] if f["collection"] == "naip"] + [
        f for f in man["frames"] if f["collection"] != "naip" and (f.get("snow_pct") or 0) <= MAX_SNOW]
    w, h = man["sentinel2_size"]
    k = max(1, round(PREVIEW_W / w))
    size = (w * k // 2 * 2, h * k // 2 * 2)  # even sides for yuv420p
    big, small = ImageFont.load_default(size=max(14, size[0] // 42)), ImageFont.load_default(size=max(11, size[0] // 64))
    shots = []
    for i, f in enumerate(seq):
        img = Image.open(out / f["file"]).convert("RGB").resize(size, Image.LANCZOS)
        draw = ImageDraw.Draw(img)
        source = "NAIP aerial" if f["collection"] == "naip" else "Sentinel-2"
        draw.text((10, 8), f"{man['label']}   {f['acquired'][:10]}   {source}", font=big, fill="white", stroke_width=2, stroke_fill="black")
        draw.text((10, size[1] - small.size - 12), f["credit"], font=small, fill="white", stroke_width=2, stroke_fill="black")
        shots += [img] * (fps if i in (0, len(seq) - 1) else 1)  # hold the first and last frames
    if shutil.which("ffmpeg"):
        with tempfile.TemporaryDirectory() as tmp:
            for i, img in enumerate(shots):
                img.save(f"{tmp}/{i:04d}.png")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{tmp}/%04d.png",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-r", "30", str(out / "preview.mp4")], check=True)
        return out / "preview.mp4"
    shots[0].save(out / "preview.gif", save_all=True, append_images=shots[1:], duration=1000 // fps, loop=0)
    return out / "preview.gif"


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ("frames", "preview"):
        sys.exit("usage: python3 -m gt.satellite frames <site-slug> [--latest] | preview <site-slug>")
    if args[0] == "frames":
        frames(args[1], latest="--latest" in args)
    else:
        print(f"preview -> {preview(args[1]).relative_to(ROOT)}")
