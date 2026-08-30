#!/usr/bin/env python3
"""
refresh.py - Rebuild every feed listed in config.json and publish them.

    python refresh.py                  # next month, falling back to this month
    python refresh.py --month 10-1-2026
    python refresh.py --only maple     # just feeds whose name matches
    python refresh.py --no-push        # rebuild locally, don't commit

Run this from your own machine: LinqConnect returns 403 to datacenter IPs, so
it cannot be automated on a server. A feed is only replaced if the new one is
non-empty and passes validation, so a bad fetch never destroys a good feed.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

import linq_api
from linq_ics import build_ics
from validate_ics import validate

CONFIG = "config.json"
PUBLIC = "public"


def candidate_months():
    today = datetime.date.today()
    first = today.replace(day=1)
    nxt = (first + datetime.timedelta(days=32)).replace(day=1)
    return [f"{nxt.month}-1-{nxt.year}", f"{first.month}-1-{first.year}"]


def load_config():
    if not os.path.exists(CONFIG):
        sys.exit(f"No {CONFIG}. Run: python discover.py --search \"<district>\"")
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    feeds = cfg.get("feeds") or []
    if not feeds:
        sys.exit(f"{CONFIG} has no feeds. "
                 "Add one with: python discover.py --district <CODE> --add \"<school>\"")
    return feeds


def build_one(feed, months):
    """Fetch, generate, validate. Returns (path, n_events, month) or None."""
    name = feed["name"]
    out = os.path.join(PUBLIC, feed["file"])
    print(f"\n{name}")

    raw = None
    used = None
    for month in months:
        try:
            raw, n_days = linq_api.fetch_menu(
                feed["buildingId"], feed["districtId"], month)
        except linq_api.LinqError as e:
            print(f"  {month}: {e}")
            return None
        if raw:
            print(f"  {month}: {n_days} school day(s)")
            used = month
            break
        print(f"  {month}: nothing posted")

    if not raw:
        print(f"  -> no menu available; leaving existing feed untouched")
        return None

    tmp = os.path.join(PUBLIC, feed["file"] + ".tmp")
    scratch = "_menu.json"
    with open(scratch, "wb") as f:
        f.write(raw)
    try:
        ics, meta = build_ics(scratch,
                              session=feed.get("session", "Lunch"),
                              detail=feed.get("detail", "full"),
                              calendar_name=name)
    except Exception as e:
        print(f"  -> could not build calendar: {e}")
        os.remove(scratch)
        return None
    os.remove(scratch)

    n_events = ics.count("BEGIN:VEVENT")
    if n_events < 1:
        print("  -> generated calendar has no events; refusing to publish")
        return None

    os.makedirs(PUBLIC, exist_ok=True)
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(ics)
    if validate(tmp):
        print("  -> failed validation; refusing to publish")
        os.remove(tmp)
        return None
    os.replace(tmp, out)
    print(f"  -> {out} ({n_events} events)")
    return out, n_events, used


def write_index(results, repo_url):
    """A landing page at the Pages root listing every published feed."""
    rows = "\n".join(
        f'      <li><a href="{os.path.basename(p)}">{n}</a> '
        f'<span class="meta">{ev} days &middot; {mo}</span></li>'
        for n, p, ev, mo in results)
    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>School Lunch Calendar Feeds</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 42rem;
         margin: 3rem auto; padding: 0 1.25rem; }}
  h1 {{ font-size: 1.4rem; }}
  ul {{ padding-left: 1.2rem; }}
  li {{ margin: .4rem 0; }}
  .meta {{ opacity: .6; font-size: .85em; }}
  code {{ background: rgba(128,128,128,.15); padding: .1em .35em;
          border-radius: 3px; word-break: break-all; }}
  footer {{ margin-top: 2.5rem; font-size: .9em; opacity: .75; }}
</style>
<h1>School lunch calendar feeds</h1>
<p>Subscribe to any of these by URL in Skylight, Google Calendar, Apple
   Calendar, or Outlook. Right-click a link to copy its address.</p>
<ul>
{rows}
</ul>
<p>In Skylight: <em>Calendar &rarr; Synced Calendars &rarr; Sync new calendar
   &rarr; Calendar by URL</em>.</p>
<footer>
  Generated from the LinqConnect public menu API.
  Source and setup instructions: <a href="{repo_url}">{repo_url}</a>
</footer>
</html>
"""
    with open(os.path.join(PUBLIC, "index.html"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="month to fetch as M-1-YYYY (e.g. 10-1-2026)")
    ap.add_argument("--only", help="only feeds whose name contains this text")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--repo-url",
                    default="https://github.com/bziebart123/linq-lunch-feed")
    args = ap.parse_args()

    feeds = load_config()
    if args.only:
        feeds = [f for f in feeds if args.only.lower() in f["name"].lower()]
        if not feeds:
            sys.exit(f"No feed name contains {args.only!r}.")

    months = [args.month] if args.month else candidate_months()
    print(f"Building {len(feeds)} feed(s); trying {' then '.join(months)}")

    built, results = [], []
    for feed in feeds:
        r = build_one(feed, months)
        if r:
            path, ev, mo = r
            built.append(path)
            results.append((feed["name"], path, ev, mo))

    if not built:
        print("\nNothing was rebuilt.")
        return 1

    write_index(results, args.repo_url)
    print(f"\nRebuilt {len(built)} of {len(feeds)} feed(s).")

    if args.no_push:
        print("--no-push set; not committing.")
        return 0

    subprocess.run(["git", "add", PUBLIC], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("No changes since last publish; nothing to push.")
        return 0
    subprocess.run(["git", "commit", "-m",
                    f"Update lunch menus ({months[0]})"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("\nPushed. GitHub Pages redeploys in about a minute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
