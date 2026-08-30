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


def write_index(results, repo_url, base_url):
    """A landing page at the Pages root listing every published feed.

    Each row shows the complete URL, not a relative link, so a parent can read
    or copy it without having to assemble it from a prefix.
    """
    items = []
    for name, path, ev, mo in results:
        url = base_url.rstrip("/") + "/" + os.path.basename(path)
        items.append(f"""    <li>
      <div class="school">{name}</div>
      <div class="meta">{ev} school days &middot; {mo.replace('-1-', '/')}</div>
      <div class="row">
        <code>{url}</code>
        <button type="button" data-url="{url}">Copy</button>
      </div>
    </li>""")
    rows = chr(10).join(items)
    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>School Lunch Calendar Feeds</title>
<style>
  :root {{ color-scheme: light dark; --line: rgba(128,128,128,.28);
           --soft: rgba(128,128,128,.12); }}
  body {{ font: 16px/1.6 system-ui, -apple-system, sans-serif;
         max-width: 46rem; margin: 3rem auto; padding: 0 1.25rem; }}
  h1 {{ font-size: 1.5rem; margin-bottom: .25rem; }}
  h2 {{ font-size: 1.05rem; margin-top: 2.5rem; }}
  .lede {{ opacity: .8; margin-top: 0; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ border: 1px solid var(--line); border-radius: 8px;
        padding: .85rem 1rem; margin: .7rem 0; }}
  .school {{ font-weight: 600; }}
  .meta {{ opacity: .6; font-size: .85em; }}
  .row {{ display: flex; gap: .5rem; align-items: center;
          margin-top: .5rem; flex-wrap: wrap; }}
  code {{ background: var(--soft); padding: .3em .5em; border-radius: 4px;
          font-size: .8em; word-break: break-all; flex: 1 1 20rem; }}
  button {{ font: inherit; font-size: .85em; padding: .3em .9em;
            border: 1px solid var(--line); border-radius: 4px;
            background: var(--soft); cursor: pointer; }}
  button:hover {{ background: rgba(128,128,128,.22); }}
  ol {{ padding-left: 1.3rem; }}
  footer {{ margin-top: 2.5rem; font-size: .9em; opacity: .7;
            border-top: 1px solid var(--line); padding-top: 1rem; }}
</style>
<h1>School lunch calendar feeds</h1>
<p class="lede">Hamilton School District. Copy your school's link below, then
   add it to Skylight, Google Calendar, Apple Calendar, or Outlook.</p>
<ul>
{rows}
</ul>

<h2>Adding it to Skylight</h2>
<ol>
  <li>On a phone or computer (not the frame), sign in at
      <a href="https://app.ourskylight.com">app.ourskylight.com</a>.</li>
  <li>Pick your frame, then <strong>Calendar &rarr; Synced Calendars &rarr;
      Sync new calendar</strong>.</li>
  <li>Choose <strong>Calendar by URL</strong> &mdash; not the Google, Apple, or
      Outlook buttons.</li>
  <li>Paste the link, give it a name, and save.</li>
</ol>
<p>Skylight refetches on its own schedule, so new menus can take a few hours to
   appear on the frame.</p>

<footer>
  Built from the LinqConnect public menu API. Menus are updated manually about
  once a month, after the district posts them.
  <a href="{repo_url}">Source and setup instructions</a>.
</footer>
<script>
document.querySelectorAll('button[data-url]').forEach(function (b) {{
  b.addEventListener('click', function () {{
    navigator.clipboard.writeText(b.dataset.url).then(function () {{
      var t = b.textContent;
      b.textContent = 'Copied';
      setTimeout(function () {{ b.textContent = t; }}, 1400);
    }});
  }});
}});
</script>
</html>
"""
    # Written to the repo root: GitHub Pages serves this repo from "/", so an
    # index inside public/ would leave the bare URL showing the rendered README.
    with open("index.html", "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="month to fetch as M-1-YYYY (e.g. 10-1-2026)")
    ap.add_argument("--only", help="only feeds whose name contains this text")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--repo-url",
                    default="https://github.com/bziebart123/linq-lunch-feed")
    ap.add_argument("--base-url",
                    default="https://bziebart123.github.io/linq-lunch-feed/public",
                    help="public URL of the folder the feeds are served from")
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

    write_index(results, args.repo_url, args.base_url)
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
