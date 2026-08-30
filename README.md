# linq-lunch-feed

Lunch menus for **Hamilton School District** (Sussex, WI) as calendar feeds you
can subscribe to. The daily menu shows up as an all-day event on every school
day, in Skylight, Google Calendar, Apple Calendar, or Outlook.

---

# For parents

**Everything you need is on one page:
[the feed list](https://bziebart123.github.io/linq-lunch-feed/).**

Find your school, then either:

- **Copy the calendar link** to subscribe in Skylight, Google, Apple, or
  Outlook — it updates itself, or
- **Open the printable PDF** — a one-page landscape month you can print for the
  fridge.

You can stop reading here — the rest of this file is for people who want to run
or change the code.

### Your school's link

| School | Feed URL |
|---|---|
| Maple Avenue Elementary | `https://bziebart123.github.io/linq-lunch-feed/public/maple_ave_lunch.ics` |
| Hamilton High School | `https://bziebart123.github.io/linq-lunch-feed/public/hamilton_high_school_lunch.ics` |
| Lannon Elementary School | `https://bziebart123.github.io/linq-lunch-feed/public/lannon_elementary_school_lunch.ics` |
| Marcy Elementary School | `https://bziebart123.github.io/linq-lunch-feed/public/marcy_elementary_school_lunch.ics` |
| Silver Spring Intermediate | `https://bziebart123.github.io/linq-lunch-feed/public/silver_spring_intermediate_lunch.ics` |
| Templeton Middle School | `https://bziebart123.github.io/linq-lunch-feed/public/templeton_middle_school_lunch.ics` |
| Woodside Elementary School | `https://bziebart123.github.io/linq-lunch-feed/public/woodside_elementary_school_lunch.ics` |

### Printable PDFs

Each school also gets a one-page landscape calendar per month, linked from the
feed list page. Same layout as the calendar link, just on paper — hot lunch in
bold, fruit in green, vegetable in brown, extras in purple, Bistro Box in red.
Print it at 100% scale (not "fit to page") on letter paper, landscape.

### Adding it to Skylight

Do this from a phone or computer browser — the frame itself has no way to type
a URL.

1. Sign in at [app.ourskylight.com](https://app.ourskylight.com) and pick your
   frame.
2. **Calendar → Synced Calendars → Sync new calendar**.
3. Choose **Calendar by URL** — not the Google, Apple, or Outlook buttons.
4. Paste your school's link, give it a name, and save.

Give it its own color so lunch doesn't blend into family events.

### Good to know

- **Updates are not instant.** Skylight refetches on its own schedule, usually
  within a few hours.
- **Menus refresh automatically once a week**, so a newly posted month shows up
  within a few days of the district publishing it.
- **The current month and next month are both included**, so the rest of this
  month never disappears when the next one is posted.
- **Weekends, holidays, and no-school days are simply absent** — that's
  expected, not a gap in the data.

---

# For developers

Everything below is about running, changing, or reusing the code.

## Updating the feeds

```bash
python refresh.py
```

Rebuilds every feed in `config.json`, publishing **this month and next month
together** as both an `.ics` feed and a one-page printable PDF per month,
validates each calendar, and pushes. Publishing only the newest available
month would erase the rest of the current month from subscribers' calendars the
moment the district posts the next one. Flags:

- `--month 10-1-2026` — one specific month only
- `--only maple` — just the feeds whose name matches
- `--no-push` — rebuild locally without committing
- `--base-url` / `--repo-url` — if you host it somewhere else

Per-feed `detail` in `config.json` controls how much text lands on each day:
`full` (hot lunch, fruit, vegetable, extra, bistro box), `hot+bistro`, or `hot`.
Drop it down if a wall display looks crowded.

## The weekly schedule

A Windows Scheduled Task runs `run_weekly.ps1` every Sunday at 9:00am. That
script pulls, runs `refresh.py`, and pushes only if a menu actually changed.
Output goes to `logs/refresh-YYYY-MM-DD.log` (last 12 kept); a failed run pops
a desktop notification rather than failing silently for weeks.

```powershell
powershell -ExecutionPolicy Bypass -File setup_schedule.ps1                          # register
powershell -ExecutionPolicy Bypass -File setup_schedule.ps1 -DayOfWeek Wed -At 7:30am
powershell -ExecutionPolicy Bypass -File setup_schedule.ps1 -Remove
Start-ScheduledTask -TaskName 'LinqLunchFeed Weekly Refresh'                          # run now
```

`StartWhenAvailable` is set, so a run missed because the machine was off or
asleep fires at the next opportunity instead of waiting a full week. The task
runs as the current user while logged on, so no password is stored and no admin
rights are needed. It needs a passphrase-free SSH key to push unattended.

This has to run on a home machine. LinqConnect blocks datacenter IPs, so no
cloud scheduler can do it.

## Using this for a different district

Nothing in the code is specific to Hamilton — district and school IDs live in
`config.json`, and you can discover them:

```bash
python discover.py --search "Hamilton"                  # find your district
python discover.py --district ZHSWGT                    # list its schools
python discover.py --district ZHSWGT --add "Marcy Elementary School"
python refresh.py
```

`--add` appends a ready-made entry to `config.json`, so no GUID is ever copied
by hand. Fork the repo, empty the `feeds` list, add your own schools, and point
`--base-url` at your own Pages site. The district search covers the whole
country, not just Wisconsin.

## API notes

```
GET https://api.linqconnect.com/api/FamilyDistrictSearch?searchText=<name>
GET https://api.linqconnect.com/api/FamilyMenuIdentifier?identifier=<code>
GET https://api.linqconnect.com/api/FamilyMenu
      ?buildingId=<GUID>&districtId=<GUID>&startDate=M-D-YYYY&endDate=M-D-YYYY
```

Three things that cost real debugging time:

- **A browser `User-Agent` is mandatory.** Plain clients get HTTP 403.
- **`endDate` is mandatory.** With `startDate` alone the API silently returns
  only the first *week* of the month — no error, nothing in the response
  marking the result partial.
- **Datacenter IPs are blocked.** The same request returns 200 from a home
  connection and 403 from GitHub Actions, Render, or a VPN. A scheduled
  workflow was built and tested against this and failed every run, which is why
  refreshing is a manual command rather than a cron job. If `refresh.py`
  reports 403, check whether a VPN is on.

The district search and building list are undocumented endpoints found in the
LinqConnect web app's JS bundle. They need no authentication today, but nothing
guarantees they stay that way.

## Determinism

Both outputs are built to be byte-stable so a weekly run with no menu change
produces no commit at all. The `.ics` comparison ignores `DTSTAMP` (the
generation time), and the PDF is written with reportlab's `invariant=1`, which
strips the creation timestamp and document id. Without both, every run would
commit, push, and redeploy Pages for nothing, burying real menu changes in
noise.

## Safety

A feed is only replaced when the new one is real. `refresh.py` aborts on an
empty API response (summer months return nothing), on a calendar with zero
events, and on any validation failure — so a bad fetch can't destroy a good
feed. `validate_ics.py` enforces CRLF line endings, balanced `BEGIN`/`END`
blocks, all-day `DTSTART`/`DTEND` spans of exactly one day, unique UIDs, and no
line over 75 octets. `.gitattributes` marks `*.ics` binary so git never
rewrites the CRLF that RFC 5545 requires.

```bash
python validate_ics.py public/maple_ave_lunch.ics
```

## Files

| File | Purpose |
|---|---|
| `config.json` | Which schools to build feeds for |
| `refresh.py` | Fetch → generate → validate → push, for every configured feed |
| `discover.py` | Find district and school IDs |
| `linq_api.py` | Client for the three public LinqConnect endpoints |
| `linq_ics.py` | Builds the `.ics` from a menu response |
| `linq_pdf.py` | Builds the one-page printable PDF calendar |
| `linq_parse.py` | Parses the JSON and XML forms of that response |
| `validate_ics.py` | Standalone iCalendar validator |
| `run_weekly.ps1` | What the scheduled task executes |
| `setup_schedule.ps1` | Registers, retimes, or removes that task |
| `public/` | The published feeds and the index page |
