import json, sys, urllib.request, urllib.parse, zlib, struct
UA = {"User-Agent": "groundtruth-feasibility-check/0.1"}
items = json.load(open(sys.argv[1])); outdir = sys.argv[2]
boxes = {"anduril_arsenal1": (-82.99, 39.760, -82.89, 39.815), "helion_orion": (-120.14, 47.32, -120.07, 47.37),
         "general_matter": (-88.845, 37.08, -88.775, 37.135), "saronic_port_alpha": (-97.42, 25.93, -97.30, 25.99)}
def png_decode(data):
    pos, idat = 8, b""
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos+4])[0]; typ = data[pos+4:pos+8]; ch_ = data[pos+8:pos+8+ln]; pos += 12 + ln
        if typ == b"IHDR": w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", ch_)
        elif typ == b"IDAT": idat += ch_
        elif typ == b"IEND": break
    assert bd == 8 and il == 0 and ct in (0, 2, 4, 6), (bd, ct, il)
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[ct]; stride = w * ch; raw = zlib.decompress(idat)
    out = bytearray(h * stride); prev = bytearray(stride); i = 0
    for y in range(h):
        ft = raw[i]; i += 1; line = bytearray(raw[i:i+stride]); i += stride
        if ft == 1:
            for x in range(ch, stride): line[x] = (line[x] + line[x-ch]) & 255
        elif ft == 2:
            for x in range(stride): line[x] = (line[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride): line[x] = (line[x] + (((line[x-ch] if x >= ch else 0) + prev[x]) >> 1)) & 255
        elif ft == 4:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0; b = prev[x]; c = prev[x-ch] if x >= ch else 0
                p = a + b - c; pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        out[y*stride:(y+1)*stride] = line; prev = line
    rgb = bytearray(w * h * 3)
    if ch >= 3:
        for k in range(3): rgb[k::3] = out[k::ch]
    else:
        for k in range(3): rgb[k::3] = out[0::ch]
    return w, h, rgb
def png_encode(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb[y*w*3:(y+1)*w*3]) for y in range(h))
    ck = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ck(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ck(b"IDAT", zlib.compress(raw, 9)) + ck(b"IEND", b"")
tiles = []
for name, bb in boxes.items():
    cands = [x for x in items[name]["PC s2-l2a"] if x["dt"] >= "2026-07-25"]
    it = sorted(cands, key=lambda x: (round(x["cc"]), -int(x["dt"][:10].replace("-", ""))))[0]
    q = urllib.parse.urlencode({"collection": "sentinel-2-l2a", "item": it["id"], "assets": "visual", "asset_bidx": "visual|1,2,3", "nodata": 0, "max_size": 800})
    bbs = ",".join(str(v) for v in bb); data = None
    for path in ("bbox", "crop"):
        url = f"https://planetarycomputer.microsoft.com/api/data/v1/item/{path}/{bbs}.png?{q}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r: data = r.read(); break
        except Exception as ex: print(f"  {name} {path}: {ex}")
    if not data: continue
    open(f"{outdir}/{name}.png", "wb").write(data)
    w, h, rgb = png_decode(data)
    print(f"{name}: item={it['id']} date={it['dt'][:10]} scene_cc={it['cc']:.1f} png={len(data)//1024}KB {w}x{h}px (~{(bb[2]-bb[0])*111.32*__import__('math').cos(__import__('math').radians(bb[1]))*1000/w:.1f} m/px)")
    tiles.append((w, h, rgb))
# 2x2 composite: TL anduril, TR helion, BL general_matter, BR saronic
if len(tiles) == 4:
    pad = 8; cw = [max(tiles[0][0], tiles[2][0]), max(tiles[1][0], tiles[3][0])]; rh = [max(tiles[0][1], tiles[1][1]), max(tiles[2][1], tiles[3][1])]
    W, H = cw[0] + cw[1] + pad, rh[0] + rh[1] + pad; canvas = bytearray(b"\xff" * (W * H * 3))
    for idx, (w, h, rgb) in enumerate(tiles):
        ox = 0 if idx % 2 == 0 else cw[0] + pad; oy = 0 if idx < 2 else rh[0] + pad
        for y in range(h): canvas[((oy+y)*W+ox)*3:((oy+y)*W+ox+w)*3] = rgb[y*w*3:(y+1)*w*3]
    open(f"{outdir}/composite.png", "wb").write(png_encode(W, H, canvas)); print("composite", W, H)
