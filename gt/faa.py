"""FAA aircraft registry: the daily ReleasableAircraft.zip (~73 MB, no key), unzipped into data/raw/faa/.

Files used:
- MASTER.txt: registered aircraft; owner in NAME, registration date in CERT ISSUE DATE.
- RESERVED.txt: reserved N-numbers ("tail numbers"); a burst of reservations usually comes
  before a batch of new aircraft.
- ACFTREF.txt: model codes; MFR names the maker, so it shows which companies build aircraft.
Owner names are matched as whole words on the legal name minus corporate suffixes, because
substrings collide ("HELION" sits inside "ANTHELION"). Individuals own aircraft too; only the
company names we ask for are ever extracted.
Evidence links: registry.faa.gov/AircraftInquiry/Search/NameResult?Nametxt=<name>
"""
import csv
import json
import re
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date

from gt.env import DATA

ZIP_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
RAW = DATA / "raw" / "faa"
SUFFIXES = {"INC", "LLC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "THE", "PBC"}


def download():
    """Fetch and unzip the registry unless today's copy is already here."""
    zpath = RAW / "ReleasableAircraft.zip"
    if zpath.exists() and date.fromtimestamp(zpath.stat().st_mtime) == date.today():
        return
    RAW.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "ground-truth-research/0.1"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        zpath.write_bytes(resp.read())
    with zipfile.ZipFile(zpath) as z:
        z.extractall(RAW, members=["MASTER.txt", "RESERVED.txt", "ACFTREF.txt"])


def normalize(name):
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split())


def core_name(legal_name):
    """'ANDURIL INDUSTRIES, INC.' -> 'ANDURIL INDUSTRIES'"""
    words = normalize(legal_name).split()
    while words and words[-1] in SUFFIXES:
        words.pop()
    while words and words[0] == "THE":
        words.pop(0)
    return " ".join(words)


def _rows(filename):
    with open(RAW / filename, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        for row in reader:
            yield dict(zip(header, (cell.strip() for cell in row)))


def _iso(yyyymmdd):
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}" if len(yyyymmdd) == 8 else None


def extract(cores):
    """One pass over the registry for a set of core names. Returns {core: {owned, reserved, models}}."""
    download()
    pattern = re.compile(r"\b(" + "|".join(re.escape(c) for c in sorted(cores, key=len, reverse=True)) + r")\b")
    found = {c: {"owned": [], "reserved": [], "models": []} for c in cores}

    def match(name):
        m = pattern.search(normalize(name))
        return m.group(1) if m else None

    models = {}
    for r in _rows("ACFTREF.txt"):
        models[r["CODE"]] = (r["MFR"], r["MODEL"])
        if (c := match(r["MFR"])):
            found[c]["models"].append(r["MODEL"])
    for r in _rows("MASTER.txt"):
        if (c := match(r["NAME"])):
            maker, model = models.get(r["MFR MDL CODE"], ("unknown", "unknown"))
            found[c]["owned"].append({"n_number": "N" + r["N-NUMBER"], "maker": maker, "model": model,
                                      "registered": _iso(r["CERT ISSUE DATE"]), "certification": r["CERTIFICATION"]})
    for r in _rows("RESERVED.txt"):
        if (c := match(r["REGISTRANT"])):
            found[c]["reserved"].append({"n_number": "N" + r["N-NUMBER"], "reserved": _iso(r["RSV DATE"])})
    return found


def name_search_url(core):
    return ("https://registry.faa.gov/AircraftInquiry/Search/NameResult?"
            + urllib.parse.urlencode({"Nametxt": core, "sort_option": 1, "PageNo": 1}))


def by_month(dates):
    months = defaultdict(list)
    for d in dates:
        if d:
            months[d[:7]].append(d)
    return dict(sorted(months.items()))


if __name__ == "__main__":
    import sys
    result = extract({core_name(n) for n in sys.argv[1:]})
    print(json.dumps({c: {k: len(v) for k, v in found.items()} for c, found in result.items()}, indent=1))
