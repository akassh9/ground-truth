#!/usr/bin/env python3
"""Fetch Anti Fund's public portfolio from antifund.com into data/anti_portfolio.json.

Each company on the homepage is a <div data-company="..."> row with a link,
a one-line description, the year invested and one or more stage labels.
Rows sit under group labels (<p class="paper-label">) inside
<div data-portfolio-group="..."> blocks; the featured rows come first, before any group.
"""
import json
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

URL = "https://antifund.com/"
OUT = Path(__file__).resolve().parent.parent / "data" / "anti_portfolio.json"


class PortfolioParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.companies = []
        self.group_slug, self.group = "featured", "Featured"
        self.row = None
        self.depth = 0  # open <div>s inside the current row
        self.in_link = False
        self.field = None  # text field currently being read
        self.reading_label = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and "data-portfolio-group" in a:
            self.group_slug = a["data-portfolio-group"]
        elif tag == "p" and "paper-label" in (a.get("class") or ""):
            self.reading_label, self.group = True, ""
        elif tag == "div" and "data-company" in a:
            self.row = {
                "slug": a["data-company"], "name": "", "url": None, "description": "",
                "group": self.group if self.group_slug != "featured" else "Featured",
                "group_slug": self.group_slug, "invested": "", "stages": [], "personal": False,
            }
            self.depth = 1
        elif self.row is None:
            return
        elif tag == "div":
            self.depth += 1
        elif tag == "a" and self.row["url"] is None:
            self.row["url"], self.in_link = a.get("href"), True
        elif tag == "span" and a.get("aria-label") == "Personal investment":
            self.row["personal"] = True
        elif tag == "span" and "data-partnered" in a:
            self.field = "invested"
        elif tag == "span" and "data-stage-part" in a:
            self.field = "stage"
            self.row["stages"].append("")
        elif tag == "span" and self.in_link and not a:
            self.field = "name"
        elif tag == "p":
            self.field = "description"

    def handle_endtag(self, tag):
        if tag == "p" and self.reading_label:
            self.reading_label = False
            self.group = self.group.strip()
        if self.row is None:
            return
        if tag in ("span", "p"):
            self.field = None
        elif tag == "a":
            self.in_link = False
        elif tag == "div":
            self.depth -= 1
            if self.depth == 0:
                # the site writes several rounds in one label: "Seed* · Series B* · Series D"
                parts = (p.strip() for s in self.row["stages"] for p in s.split("·"))
                self.row["stages"] = [p for p in parts if p]
                for key in ("name", "description", "invested"):
                    self.row[key] = self.row[key].strip()
                self.companies.append(self.row)
                self.row = None

    def handle_data(self, data):
        if self.reading_label:
            self.group += data
        elif self.row is None or self.field is None:
            return
        elif self.field == "stage":
            self.row["stages"][-1] += data
        else:
            self.row[self.field] += data


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (ground-truth research)"})
    page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    parser = PortfolioParser()
    parser.feed(page)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": URL,
        "fetched": date.today().isoformat(),
        "note": "A trailing * on a stage, or personal=true, marks a partner's personal investment.",
        "companies": parser.companies,
    }, indent=2) + "\n")
    print(f"{len(parser.companies)} companies -> {OUT}")
    for c in parser.companies:
        print(f"  {c['group_slug'][:28]:28} {c['name'][:24]:24} {c['invested']:5} {', '.join(c['stages'])[:30]}")


if __name__ == "__main__":
    main()
