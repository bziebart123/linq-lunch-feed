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


_LOOKUPS = {}


def lookups_for(district_id):
    """Allergen/Halal name maps, fetched once per district per run.

    A failure here must not take down the feeds, so it degrades to no
    allergen data rather than raising.
    """
    if district_id not in _LOOKUPS:
        try:
            _LOOKUPS[district_id] = linq_api.district_lookups(district_id)
        except linq_api.LinqError as e:
            print(f"  (allergen names unavailable: {e})")
            _LOOKUPS[district_id] = {}
    return _LOOKUPS[district_id]


def build_one(feed, months):
    """Fetch, generate, validate. Returns (path, n_events, month) or None."""
    name = feed["name"]
    out = os.path.join(PUBLIC, feed["file"])
    print(f"\n{name}")

    parts, got, pdfs = [], [], []
    # The calendar name carries "Lunch"; the PDF header should not repeat it.
    school_label = name[:-6] if name.endswith(" Lunch") else name
    note = feed.get("note", DISTRICT_NOTE)
    lookups = lookups_for(feed["districtId"])
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
                               calendar_name=name, lookups=lookups)
        except Exception as e:
            print(f"  {month}: could not build calendar: {e}")
            os.remove(scratch)
            continue
        try:
            if build_pdf is None:
                raise RuntimeError(
                    f"PDF support unavailable ({_PDF_ERROR}); "
                    "install it with: pip install reportlab")
            MENU, meta = build_menu(scratch, session=feed.get("session", "Lunch"),
                                    lookups=lookups)
            base = os.path.splitext(feed["file"])[0]
            mname = MONTH_NAMES[meta["month"] - 1]
            stamp = f"{mname} {meta['year']}"
            os.makedirs(PUBLIC, exist_ok=True)

            # Two sheets: the normal menu, and one that puts allergens front
            # and centre for families who need to read them at a glance.
            variants = [("", feed.get("detail", "full"), "menu")]
            if any((v or {}).get("allergens") for v in MENU.values()):
                variants.append(("_allergens", "allergens", "allergens"))

            for suffix, mode, kind in variants:
                pdf_name = f"{base}_{mname}_{meta['year']}{suffix}.pdf"
                pdf_tmp = os.path.join(PUBLIC, pdf_name + ".tmp")
                made = build_pdf(MENU, meta["month"], meta["year"], school_label,
                                 pdf_tmp, note=note, detail=mode,
                                 no_school=meta.get("no_school"))
                if not made:
                    if os.path.exists(pdf_tmp):
                        os.remove(pdf_tmp)
                    continue
                pdf_out = os.path.join(PUBLIC, pdf_name)
                new = open(pdf_tmp, "rb").read()
                if os.path.exists(pdf_out) and open(pdf_out, "rb").read() == new:
                    os.remove(pdf_tmp)
                else:
                    os.replace(pdf_tmp, pdf_out)
                pdfs.append((stamp, pdf_out, kind))
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
        school = name[:-6] if name.endswith(" Lunch") else name
        url = base_url.rstrip("/") + "/" + os.path.basename(path)
        chips = chr(10).join(
            '          <a class="chip{}" href="{}">{}<span class="ext">{}</span></a>'
            .format("" if kind == "menu" else " alt",
                    base_url.rstrip("/") + "/" + os.path.basename(p),
                    label,
                    "PDF" if kind == "menu" else "ALLERGENS")
            for label, p, kind in pdfs)
        pdf_group = ("""
        <div class="opt">
          <div class="opt-label">Print</div>
""" + chips + """
        </div>""") if chips else ""
        items.append(f"""    <li>
      <div class="head">
        <h3>{school}</h3>
        <span class="meta">{ev} school days</span>
      </div>
      <div class="opt">
        <div class="opt-label">Subscribe</div>
        <div class="urlrow">
          <code>{url}</code>
          <button type="button" data-url="{url}"
                  aria-label="Copy the {school} calendar link">Copy</button>
        </div>
      </div>{pdf_group}
    </li>""")
    rows = chr(10).join(items)
    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>School Lunch Calendar Feeds</title>
<style>
  :root {{ color-scheme: light dark;
           --line: rgba(128,128,128,.26);
           --soft: rgba(128,128,128,.11);
           --accent: #00838f; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --accent: #4dd0e1; }} }}
  * {{ box-sizing: border-box; }}
  body {{ font: 16px/1.6 system-ui, -apple-system, sans-serif;
         max-width: 44rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 .3rem; color: var(--accent); }}
  h2 {{ font-size: 1.05rem; margin: 2.75rem 0 .6rem; }}
  h3 {{ font-size: 1.02rem; margin: 0; }}
  .lede {{ opacity: .85; margin-top: 0; }}

  .legend {{ display: grid; gap: .5rem; margin: 1.5rem 0 2rem; padding: .9rem 1rem;
             border: 1px solid var(--line); border-radius: 10px;
             background: var(--soft); font-size: .92em; }}
  .legend div {{ display: grid; grid-template-columns: 5rem 1fr; gap: .55rem; }}
  .legend b {{ color: var(--accent); }}
  @media (max-width: 30rem) {{
    .legend div {{ grid-template-columns: 1fr; gap: .1rem; }}
  }}

  ul.schools {{ list-style: none; padding: 0; margin: 0; }}
  ul.schools > li {{ border: 1px solid var(--line); border-radius: 10px;
        padding: 1rem 1.1rem; margin: .8rem 0; }}
  .head {{ display: flex; justify-content: space-between; align-items: baseline;
           gap: .75rem; flex-wrap: wrap; margin-bottom: .8rem; }}
  .meta {{ opacity: .55; font-size: .82em; white-space: nowrap; }}

  .opt + .opt {{ margin-top: .85rem; padding-top: .85rem;
                 border-top: 1px dashed var(--line); }}
  .opt-label {{ font-size: .72em; letter-spacing: .09em; text-transform: uppercase;
                opacity: .75; font-weight: 600; margin-bottom: .4rem; }}
  .hint {{ text-transform: none; letter-spacing: 0; font-weight: 400;
           opacity: .75; }}

  .urlrow {{ display: flex; gap: .5rem; align-items: stretch; flex-wrap: wrap;
             min-width: 0; }}
  /* min-width:0 matters: a flex child defaults to min-width:auto, which stops
     the long URL shrinking and pushes the whole page wider than the phone. */
  code {{ background: var(--soft); padding: .45em .6em; border-radius: 6px;
          font-size: .78em; overflow-wrap: anywhere; word-break: break-word;
          flex: 1 1 12rem; min-width: 0; border: 1px solid var(--line); }}
  button {{ font: inherit; font-size: .85em; padding: .4em 1.1em;
            border: 1px solid var(--accent); border-radius: 6px; color: var(--accent);
            background: transparent; cursor: pointer; font-weight: 600;
            white-space: nowrap; flex: 0 0 auto; }}
  button:hover {{ background: var(--soft); }}
  button.done {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

  a.chip {{ display: inline-flex; align-items: center; gap: .5rem;
            font-size: .88em; text-decoration: none; color: inherit;
            border: 1px solid var(--line); border-radius: 6px;
            padding: .4em .5em .4em .8em; margin: 0 .4rem .4rem 0; }}
  a.chip:hover {{ background: var(--soft); border-color: var(--accent); }}
  .ext {{ font-size: .72em; font-weight: 700; letter-spacing: .05em;
          background: var(--soft); border-radius: 4px; padding: .15em .45em;
          opacity: .8; }}
  a.chip.alt .ext {{ background: rgba(198,40,40,.14); color: #c62828; }}
  @media (prefers-color-scheme: dark) {{
    a.chip.alt .ext {{ background: rgba(255,138,128,.18); color: #ff8a80; }}
  }}

  ol {{ padding-left: 1.3rem; }}
  ol li {{ margin: .3rem 0; }}
  footer {{ margin-top: 3rem; font-size: .88em; opacity: .7;
            border-top: 1px solid var(--line); padding-top: 1rem; }}
</style>
<h1>School lunch menus</h1>
<p class="lede">Hamilton School District. All seven schools.</p>

<div class="legend">
  <div><b>Subscribe</b><span>Add the menu to Skylight, Google, Apple, or
       Outlook. You set it up once and it updates on its own.</span></div>
  <div><b>Print</b><span>A printable page for each month.</span></div>
</div>

<ul class="schools">
{rows}
</ul>

<h2>Adding it to Skylight</h2>
<ol>
  <li>On a phone or computer (not the frame), sign in at
      <a href="https://app.ourskylight.com">app.ourskylight.com</a>.</li>
  <li>Pick your frame, then <strong>Calendar &rarr; Synced Calendars &rarr;
      Sync new calendar</strong>.</li>
  <li>Choose <strong>Calendar by URL</strong>. Do not use the Google, Apple, or
      Outlook buttons.</li>
  <li>Paste the link, give it a name, and save.</li>
</ol>
<p>Skylight checks for updates on its own schedule. A new menu can take a few
   hours to show up on the frame.</p>

<h2>What you will see each day</h2>
<p>The hot lunch, the fruit, the vegetable, and any extra. Each day also lists
   the alternative your child can choose instead of the hot lunch. It is called
   <strong>Bistro Box</strong> at the elementary and intermediate schools,
   <strong>Grab &amp; Go</strong> at Templeton, and <strong>The Grill</strong>
   or <strong>Build Your Own</strong> at the high school.</p>

<h2>Allergens</h2>
<p>Each day lists the allergens the district records for the hot lunch, and the
   calendar spells them out for every item. The standard printable keeps them
   short as letter codes with a key at the bottom. If you need them at a
   glance, use the <strong>Allergens</strong> printable instead, which lists
   them in full for each item.</p>
<p>This information comes from the district and can change. Confirm with the
   school before relying on it.</p>

<footer>
  Menus come from the LinqConnect public API and are refreshed weekly.
  <a href="{repo_url}">Source and setup instructions</a>.
</footer>
<script>
document.querySelectorAll('button[data-url]').forEach(function (b) {{
  b.addEventListener('click', function () {{
    var done = function () {{
      b.textContent = 'Copied';
      b.classList.add('done');
      setTimeout(function () {{
        b.textContent = 'Copy';
        b.classList.remove('done');
      }}, 1600);
    }};
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(b.dataset.url).then(done, fallback);
    }} else {{
      fallback();
    }}
    // Older mobile browsers and any non-secure context land here.
    function fallback() {{
      var ta = document.createElement('textarea');
      ta.value = b.dataset.url;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {{ document.execCommand('copy'); done(); }} catch (e) {{
        var c = b.previousElementSibling;
        if (c) {{
          var r = document.createRange();
          r.selectNodeContents(c);
          var s = window.getSelection();
          s.removeAllRanges();
          s.addRange(r);
        }}
      }}
      document.body.removeChild(ta);
    }}
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
