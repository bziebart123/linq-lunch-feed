#!/usr/bin/env python3
"""
discover.py - Find the district and building IDs for your own school.

    python discover.py --search "Hamilton"     # find your district
    python discover.py --district ZHSWGT       # list its schools
    python discover.py --district ZHSWGT --add "Maple Avenue Elementary"

The last form appends a ready-to-use feed entry to config.json, so you never
have to copy a GUID by hand.
"""

import argparse
import json
import os
import re
import sys

import linq_api

CONFIG = "config.json"


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return re.sub(r"_+", "_", s)


def cmd_search(text):
    rows = linq_api.search_districts(text)
    if not rows:
        print(f"No districts matched {text!r}.")
        return 1
    print(f"{len(rows)} district(s) matching {text!r}:\n")
    print(f"  {'CODE':<8} {'DISTRICT':<40} LOCATION")
    for d in rows:
        loc = ", ".join(x for x in (d.get("City"), d.get("State")) if x)
        print(f"  {d.get('Identifier',''):<8} {d.get('Name','')[:40]:<40} {loc}")
    print("\nNext: python discover.py --district <CODE>")
    return 0


def cmd_district(identifier, add=None):
    d = linq_api.district_buildings(identifier)
    buildings = d.get("Buildings") or []
    print(f"{d['DistrictName']}  (code {d['Identifier']})")
    print(f"district id: {d['DistrictId']}\n")
    for i, b in enumerate(buildings, 1):
        print(f"  {i}. {b['Name']}")
    if d.get("MenuNotification"):
        print(f"\nDistrict note: {d['MenuNotification'].strip()}")

    if not add:
        print("\nAdd one to config.json with:")
        print(f'  python discover.py --district {identifier} --add "<school name>"')
        return 0

    match = [b for b in buildings if b["Name"].lower() == add.lower()]
    if not match:
        match = [b for b in buildings if add.lower() in b["Name"].lower()]
    if len(match) != 1:
        print(f"\n{add!r} matched {len(match)} schools; be more specific.")
        return 1
    b = match[0]

    cfg = {"feeds": []}
    if os.path.exists(CONFIG):
        cfg = json.load(open(CONFIG, encoding="utf-8"))
    cfg.setdefault("feeds", [])

    if any(f.get("buildingId") == b["BuildingId"] and
           f.get("session", "Lunch") == "Lunch" for f in cfg["feeds"]):
        print(f"\n{b['Name']} is already in {CONFIG}.")
        return 0

    entry = {
        "name": f"{b['Name']} Lunch",
        "file": f"{slugify(b['Name'])}_lunch.ics",
        "districtId": d["DistrictId"],
        "buildingId": b["BuildingId"],
        "session": "Lunch",
        "detail": "full",
    }
    cfg["feeds"].append(entry)
    with open(CONFIG, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print(f"\nAdded to {CONFIG}:")
    print(json.dumps(entry, indent=2))
    print("\nNow run: python refresh.py")
    return 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--search", metavar="NAME", help="find a district by name")
    g.add_argument("--district", metavar="CODE", help="list a district's schools")
    ap.add_argument("--add", metavar="SCHOOL",
                    help="append this school to config.json")
    args = ap.parse_args()
    try:
        if args.search:
            return cmd_search(args.search)
        return cmd_district(args.district, args.add)
    except linq_api.LinqError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
