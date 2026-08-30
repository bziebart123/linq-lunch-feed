#!/usr/bin/env python3
"""
refresh.py - Fetch the latest Maple Ave lunch menu and republish the feed.

Run this from your own machine: LinqConnect returns 403 to datacenter IPs
(GitHub Actions, most cloud hosts), so this cannot be automated server-side.

    python refresh.py              # next month, falling back to this month
    python refresh.py --month 10-1-2026
    python refresh.py --no-push    # regenerate locally, don't commit

It fetches, regenerates public/maple_ave_lunch.ics, validates it, and pushes.
It refuses to publish an empty or invalid calendar over a good one.
"""

import argparse
import calendar
import datetime
import json
import subprocess
import sys
import urllib.error
import urllib.request

BUILDING_ID = "a513a71a-22d7-ee11-a71c-a811a99a3020"   # Maple Avenue Elementary
DISTRICT_ID = "37aa0b35-eba0-ee11-839d-b338dc280a64"   # Hamilton SD, WI
API = "https://api.linqconnect.com/api/FamilyMenu"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

OUT = "public/maple_ave_lunch.ics"
RAW = "FamilyMenu.json"


def month_str(d):
    return f"{d.month}-1-{d.year}"


def month_end(start):
    """Last day of the month named by a 'M-1-YYYY' start string.

    The API returns only the first WEEK unless an explicit endDate is sent,
    so every request must carry one.
    """
    m, _, y = (int(x) for x in start.split("-"))
    return f"{m}-{calendar.monthrange(y, m)[1]}-{y}"


def candidates():
    today = datetime.date.today()
    first = today.replace(day=1)
    nxt = (first + datetime.timedelta(days=32)).replace(day=1)
    return [month_str(nxt), month_str(first)]


def fetch(start):
    end = month_end(start)
    url = (f"{API}?buildingId={BUILDING_ID}&districtId={DISTRICT_ID}"
           f"&startDate={start}&endDate={end}")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://linqconnect.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for startDate={start}")
        if e.code == 403:
            print("  (403 usually means you are on a blocked network - "
                  "LinqConnect rejects datacenter/VPN IPs. Try your home wifi.)")
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"  Response was not JSON for startDate={start}")
        return None
    n = len(data.get("FamilyMenuSessions") or [])
    n_days = sum(len(pl.get("Days") or [])
                 for se in (data.get("FamilyMenuSessions") or [])
                 for pl in (se.get("MenuPlans") or []))
    print(f"  {start}..{end}: {n} session(s), {n_days} day(s)")
    return body if n > 0 else None


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="month to fetch as M-1-YYYY (e.g. 10-1-2026)")
    ap.add_argument("--detail", default="full",
                    choices=["full", "hot+bistro", "hot"])
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    tries = [args.month] if args.month else candidates()
    body = None
    used = None
    print("Fetching menu...")
    for start in tries:
        body = fetch(start)
        if body:
            used = start
            break
    if not body:
        print(f"\nNo menu posted for {' or '.join(tries)}. "
              "Existing feed left untouched.")
        return 1

    with open(RAW, "wb") as f:
        f.write(body)

    print(f"\nGenerating feed from {used}...")
    run([sys.executable, "linq_ics.py", RAW, "-o", "candidate.ics",
         "--detail", args.detail, "--name", "Maple Ave Lunch"])

    if subprocess.run([sys.executable, "validate_ics.py", "candidate.ics"]).returncode:
        print("\nCandidate feed is invalid - refusing to publish.")
        return 1

    import os
    os.replace("candidate.ics", OUT)
    os.remove(RAW)
    print(f"\nWrote {OUT}")

    if args.no_push:
        print("--no-push set; not committing.")
        return 0

    if not subprocess.run(["git", "diff", "--quiet", "--", OUT]).returncode:
        print("No change since last publish; nothing to push.")
        return 0

    run(["git", "add", OUT])
    run(["git", "commit", "-m", f"Update lunch menu ({used})"])
    run(["git", "push"])
    print("\nPushed. GitHub Pages redeploys in about a minute:")
    print("  https://bziebart123.github.io/linq-lunch-feed/public/maple_ave_lunch.ics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
