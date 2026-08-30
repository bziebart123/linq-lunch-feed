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
from linq_parse import build_menu

try:
    from linq_pdf import MONTH_NAMES, build_pdf
except ImportError as _e:  # reportlab missing or broken
    build_pdf = None
    MONTH_NAMES = None
    _PDF_ERROR = _e

from validate_ics import validate

CONFIG = "config.json"
DISTRICT_NOTE = ""
CRLF = chr(13) + chr(10)
PUBLIC = "public"


def candidate_months():
    """This month and next, in order.

    Both are published together. Taking only the newest available month would
    erase the rest of the current month from every subscriber's calendar the
    moment the district posts the next one.
    """
    today = datetime.date.today()
    first = today.replace(day=1)
    nxt = (first + datetime.timedelta(days=32)).replace(day=1)
    return [f"{first.month}-1-{first.year}", f"{nxt.month}-1-{nxt.year}"]


def _content_key(text):
    """A calendar's meaning, ignoring DTSTAMP.

    DTSTAMP is the generation time, so it changes on every run. Comparing on it
    would make each weekly refresh look like a change and produce a pointless
    commit, push, and Pages redeploy.
    """
    return [ln for ln in text.split(CRLF) if not ln.startswith("DTSTAMP:")]


def merge_calendars(parts):
    """Splice several one-month calendars into a single VCALENDAR.

    Keeps the first calendar's header, concatenates every VEVENT, and drops
    duplicate UIDs so an overlapping response cannot double-book a day.
    """
    if len(parts) == 1:
        return parts[0]
    header, events, seen = [], [], set()
    for part in parts:
        lines = part.split(CRLF)
        if "BEGIN:VEVENT" not in lines:
            continue
        first = lines.index("BEGIN:VEVENT")
        last = len(lines) - 1 - lines[::-1].index("END:VEVENT")
        if not header:
            header = lines[:first]
        block = []
        for line in lines[first:last + 1]:
            block.append(line)
            if line == "END:VEVENT":
                uid = next((x[4:] for x in block if x.startswith("UID:")), None)
                if uid and uid not in seen:
                    seen.add(uid)
                    events.extend(block)
                block = []
    return CRLF.join(header + events + ["END:VCALENDAR"]) + CRLF


def load_config():
    if not os.path.exists(CONFIG):
        sys.exit(f"No {CONFIG}. Run: python discover.py --search \"<district>\"")
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    global DISTRICT_NOTE
    DISTRICT_NOTE = (cfg.get("district") or {}).get("note", "")
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

    parts, got, pdfs = [], [], []
    # The calendar name carries "Lunch"; the PDF header should not repeat it.
    school_label = name[:-6] if name.endswith(" Lunch") else name
    note = feed.get("note", DISTRICT_NOTE)
    scratch = "_menu.json"
    for month in months:
        try:
            raw, n_days = linq_api.fetch_menu(
                feed["buildingId"], feed["districtId"], month)
        except linq_api.LinqError as e:
            print(f"  {month}: {e}")
            return None
        if not raw:
            print(f"  {month}: nothing posted")
            continue
        with open(scratch, "wb") as f:
            f.write(raw)
        try:
            ics, _ = build_ics(scratch,
                               session=feed.get("session", "Lunch"),
                               detail=feed.get("detail", "full"),
                               calendar_name=name)
        except Exception as e:
            print(f"  {month}: could not build calendar: {e}")
            os.remove(scratch)
            continue
        try:
            if build_pdf is None:
                raise RuntimeError(
                    f"PDF support unavailable ({_PDF_ERROR}); "
                    "install it with: pip install reportlab")
            MENU, meta = build_menu(scratch, session=feed.get("session", "Lunch"))
            base = os.path.splitext(feed["file"])[0]
            mname = MONTH_NAMES[meta["month"] - 1]
            pdf_name = f"{base}_{mname}_{meta['year']}.pdf"
            pdf_tmp = os.path.join(PUBLIC, pdf_name + ".tmp")
            os.makedirs(PUBLIC, exist_ok=True)
            if build_pdf(MENU, meta["month"], meta["year"], school_label,
                         pdf_tmp, note=note,
                         detail=feed.get("detail", "full")):
                pdf_out = os.path.join(PUBLIC, pdf_name)
                new = open(pdf_tmp, "rb").read()
                if os.path.exists(pdf_out) and open(pdf_out, "rb").read() == new:
                    os.remove(pdf_tmp)
                else:
                    os.replace(pdf_tmp, pdf_out)
                pdfs.append((f"{mname} {meta['year']}", pdf_out))
            elif os.path.exists(pdf_tmp):
                os.remove(pdf_tmp)
        except Exception as e:
            print(f"  {month}: could not build PDF: {e}")

        os.remove(scratch)
        print(f"  {month}: {n_days} school day(s)")
        parts.append(ics)
        got.append(month)

    if not parts:
        print("  -> no menu available; leaving existing feed untouched")
        return None

    ics = merge_calendars(parts)
    used = " + ".join(got)
    tmp = os.path.join(PUBLIC, feed["file"] + ".tmp")

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

    if os.path.exists(out):
        existing = open(out, encoding="utf-8", newline="").read()
        if _content_key(existing) == _content_key(ics):
            os.remove(tmp)
            print(f"  -> unchanged ({n_events} events, {len(pdfs)} PDF)")
            return out, n_events, used, pdfs

    os.replace(tmp, out)
    print(f"  -> {out} ({n_events} events updated, {len(pdfs)} PDF)")
    return out, n_events, used, pdfs


def write_index(results, repo_url, base_url):
    """A landing page at the Pages root listing every published feed.

    Each row shows the complete URL, not a relative link, so a parent can read
    or copy it without having to assemble it from a prefix.
    """
    items = []
    for name, path, ev, mo, pdfs in results:
        url = base_url.rstrip("/") + "/" + os.path.basename(path)
        links = " ".join(
            '<a class="pdf" href="{}">{}</a>'.format(
                base_url.rstrip("/") + "/" + os.path.basename(p), label)
            for label, p in pdfs)
        pdf_row = ('      <div class="row pdfs"><span class="lbl">Printable:</span> '
                   + links + "</div>") if links else ""
        items.append(f"""    <li>
      <div class="school">{name}</div>
      <div class="meta">{ev} school days &middot; {mo.replace('-1-', '/')}</div>
      <div class="row">
        <code>{url}</code>
        <button type="button" data-url="{url}">Copy</button>
      </div>
{pdf_row}
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
  .pdfs {{ margin-top: .35rem; }}
  .lbl {{ font-size: .85em; opacity: .65; }}
  a.pdf {{ font-size: .85em; text-decoration: none; border: 1px solid var(--line);
           border-radius: 4px; padding: .22em .6em; }}
  a.pdf:hover {{ background: var(--soft); }}
  ol {{ padding-left: 1.3rem; }}
  footer {{ margin-top: 2.5rem; font-size: .9em; opacity: .7;
            border-top: 1px solid var(--line); padding-top: 1rem; }}
</style>
<h1>School lunch calendar feeds</h1>
<p class="lede">Hamilton School District. Copy your school's link below to add
   the menu to Skylight, Google Calendar, Apple Calendar, or Outlook &mdash; or
   grab the one-page <strong>printable PDF</strong> for the fridge.</p>
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
            path, ev, mo, pdfs = r
            built.append(path)
            results.append((feed["name"], path, ev, mo, pdfs))

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
    stamp = datetime.date.today().isoformat()
    subprocess.run(["git", "commit", "-m",
                    f"Update lunch menus ({stamp})"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("\nPushed. GitHub Pages redeploys in about a minute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
