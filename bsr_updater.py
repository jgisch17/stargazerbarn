#!/usr/bin/env python3
"""
BSR Updater — updates the Stargazer dashboard with today's Amazon BSR ranks.

Usage:
    python3 bsr_updater.py '<json>'

    where <json> is a dict of {product_name: rank_int} produced by scrape_bsr.py.

New products in the JSON that don't yet exist in bsr_data are auto-added with
null historical ranks so they appear on the dashboard from their first sighting.
"""

import sys
import json
import re
from datetime import date

DASHBOARD_DATA = "/Volumes/GISCH SSD/CLAUDE/Stargazer/dashboard_data.js"
TODAY = str(date.today())


def get_brand(name):
    if name.startswith("Stargazer"):
        return "Stargazer"
    if " - " in name:
        return name.split(" - ")[0].strip()
    if "-" in name:
        return name.split("-")[0].strip()
    return name.split()[0]


def extract_bsr_json(text):
    match = re.search(r'bsr_data:', text)
    if not match:
        raise ValueError("bsr_data key not found in dashboard_data.js")
    start = match.end()
    depth = 0
    in_string = False
    escape = False
    i = start
    while i < len(text):
        c = text[i]
        if escape:
            escape = False
        elif c == '\\' and in_string:
            escape = True
        elif c == '"':
            in_string = not in_string
        elif not in_string:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return match.start(), i + 1, text[start:i + 1]
        i += 1
    raise ValueError("Could not find closing brace for bsr_data")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 bsr_updater.py '<json_ranks>'", file=sys.stderr)
        sys.exit(1)

    try:
        input_ranks = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Error parsing rank JSON: {e}", file=sys.stderr)
        sys.exit(1)

    with open(DASHBOARD_DATA, "r", encoding="utf-8") as f:
        content = f.read()

    key_start, key_end, bsr_json_str = extract_bsr_json(content)
    bsr = json.loads(bsr_json_str)

    if TODAY in bsr["dates"]:
        print(f"Already tracked: {TODAY} is already in bsr_data.dates — no changes made.")
        _report(bsr, TODAY)
        sys.exit(0)

    num_dates = len(bsr["dates"])  # current length before appending today

    # Auto-add any product in today's scrape that isn't yet in rankings
    existing_names = {p["product"] for p in bsr["rankings"]}
    for name in input_ranks:
        if name not in existing_names:
            bsr["rankings"].append({
                "product": name,
                "brand": get_brand(name),
                "ranks": [None] * num_dates,
                "latest": None,
                "best": None,
            })
            existing_names.add(name)
            print(f"  Auto-added new product: {name}")

    bsr["dates"].append(TODAY)

    for product in bsr["rankings"]:
        name = product["product"]
        rank = input_ranks.get(name, None)
        product["ranks"].append(rank)
        non_null = [r for r in product["ranks"] if r is not None]
        product["latest"] = rank
        product["best"] = min(non_null) if non_null else None

    new_bsr_str = json.dumps(bsr, separators=(",", ":"))
    new_content = content[:key_start] + "bsr_data:" + new_bsr_str + content[key_end:]

    with open(DASHBOARD_DATA, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ BSR updated for {TODAY} ({len(bsr['dates'])} days tracked)")
    _report(bsr, TODAY)


def _report(bsr, today):
    idx = bsr["dates"].index(today)
    sg_products = [p for p in bsr["rankings"] if p["brand"] == "Stargazer"]
    print(f"\nStargazer rankings for {today}:")
    print(f"{'Product':<45} {'Today':>6} {'Best':>6}")
    print("-" * 60)
    for p in sg_products:
        rank = p["ranks"][idx]
        best = p["best"]
        rank_str = f"#{rank}" if rank else "—"
        best_str = f"#{best}" if best else "—"
        print(f"{p['product']:<45} {rank_str:>6} {best_str:>6}")


if __name__ == "__main__":
    main()
