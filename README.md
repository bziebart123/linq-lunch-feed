# linq-lunch-feed

Lunch menus for **Hamilton School District** (Sussex, WI) as calendar feeds you
can subscribe to. The daily menu shows up as an all-day event on every school
day, in Skylight, Google Calendar, Apple Calendar, or Outlook.

---

# For parents

**Everything is on one page: [the lunch menu
page](https://bziebart123.github.io/linq-lunch-feed/).** Find your school and
pick one of two things. You can stop reading here. The rest of this file is
for people who want to run or change the code.

| | What it is | Best for |
|---|---|---|
| **Subscribe** | A calendar link you add once. It updates on its own. | Skylight frames, phone calendars |
| **Print** | One landscape page per month. | Printing |

### Calendar links

These never change, so they are safe to bookmark or pass along:

| School | Calendar link |
|---|---|
| Maple Avenue Elementary | `https://bziebart123.github.io/linq-lunch-feed/public/maple_ave_lunch.ics` |
| Hamilton High School | `https://bziebart123.github.io/linq-lunch-feed/public/hamilton_high_school_lunch.ics` |
| Lannon Elementary School | `https://bziebart123.github.io/linq-lunch-feed/public/lannon_elementary_school_lunch.ics` |
| Marcy Elementary School | `https://bziebart123.github.io/linq-lunch-feed/public/marcy_elementary_school_lunch.ics` |
| Silver Spring Intermediate | `https://bziebart123.github.io/linq-lunch-feed/public/silver_spring_intermediate_lunch.ics` |
| Templeton Middle School | `https://bziebart123.github.io/linq-lunch-feed/public/templeton_middle_school_lunch.ics` |
| Woodside Elementary School | `https://bziebart123.github.io/linq-lunch-feed/public/woodside_elementary_school_lunch.ics` |

### Printable PDFs

Each school gets two printables per month: the standard menu, and a
"PDF with allergens" version. PDF links are not listed here on purpose. Each filename contains its
month (`maple_ave_lunch_September_2026.pdf`,
`maple_ave_lunch_September_2026_allergens.pdf`), so any list written here goes
stale as soon as a new month is posted. The [menu
page](https://bziebart123.github.io/linq-lunch-feed/) always has the current
ones.

The layout matches the calendar: hot lunch in bold, fruit in green, vegetable
in brown, extras in purple, and the alternative option in red. Print at 100%
scale (not "fit to page") on letter paper, landscape.

### Allergens and Halal

Every day lists the allergens the district records: Egg, Milk, Wheat, Soy,
Sesame Seeds, and Fish. Items the district marks Halal are labelled as such.

- **Calendar links** spell allergens out in full for each item, including the
  sides.
- **The PDF with allergens** lists them in full for every item. Use this one if
  you want them on paper.
- **The standard PDF** leaves allergens out so the menu stays easy to read.

This information comes from the district and can change. Confirm with the school
before relying on it.

Allergens are tracked per item, not pooled for the day, so the entree is never
credited with an allergen that was only in the cookie.

### The alternative lunch option

Every school offers a daily alternative you can pick *instead of* the hot
lunch, and it is listed on every day of both the calendar and the PDF. Each
level names it differently, so the label follows the school:

| School level | Shown as |
|---|---|
| Elementary and intermediate | **Bistro Box** |
| Templeton Middle School | **Grab & Go** |
| Hamilton High School | **The Grill**, **Build Your Own** |
| Any school, on days with a second entree | **Also Offered** |

### Adding it to Skylight

Do this from a phone or computer browser. The frame itself has no way to type
a URL.

1. Sign in at [app.ourskylight.com](https://app.ourskylight.com) and pick your
   frame.
2. **Calendar → Synced Calendars → Sync new calendar**.
3. Choose **Calendar by URL**. Do not use the Google, Apple, or Outlook
   buttons.
4. Paste your school's link, give it a name, and save.

Give it its own color so lunch doesn't blend into family events.

### Good to know

- **Updates are not instant.** Skylight refetches on its own schedule, usually
  within a few hours.
- **Menus refresh automatically once a week**, so a newly posted month shows up
  within a few days of the district publishing it.
- **The current month and next month are both included**, so the rest of this
  month never disappears when the next one is posted.
- **Weekends, holidays, and no-school days are absent.** That is expected and
  not a gap in the data.

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

- `--month 10-1-2026` fetches one specific month only
- `--only maple` limits the run to feeds whose name matches
- `--no-push` rebuilds locally without committing
- `--base-url` / `--repo-url` point at a different host

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

Nothing in the code is specific to Hamilton. District and school IDs live in
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
GET https://api.linqconnect.com/api/FamilyMenuFilter?districtId=<GUID>
GET https://api.linqconnect.com/api/FamilyMenuIdentifier?identifier=<code>
GET https://api.linqconnect.com/api/FamilyMenu
      ?buildingId=<GUID>&districtId=<GUID>&startDate=M-D-YYYY&endDate=M-D-YYYY
```

Three things that cost real debugging time:

- **A browser `User-Agent` is mandatory.** Plain clients get HTTP 403.
- **`endDate` is mandatory.** With `startDate` alone the API silently returns
  only the first *week* of the month. There is no error and nothing in the
  response marking the result partial.
- **Allergens arrive as bare GUIDs.** The menu response tags each recipe with
  allergen ids and nothing else. `FamilyMenuFilter?districtId=` is the map that
  turns them into "Milk" and "Halal". It also lists the district's serving
  sessions, which is how you can tell this district serves lunch only and there
  is no breakfast menu to publish.
- **Datacenter IPs are blocked.** The same request returns 200 from a home
  connection and 403 from GitHub Actions, Render, or a VPN. A scheduled
  workflow was built and tested against this and failed every run, which is why
  the refresh runs from a local Windows scheduled task rather than a cloud cron
  job. If `refresh.py` reports 403, check whether a VPN is on.

The district search and building list are undocumented endpoints found in the
LinqConnect web app's JS bundle. They need no authentication today, but nothing
guarantees they stay that way.

## Parsing notes

The alternative option is easy to get wrong, and three separate traps produce
plausible-looking but incorrect menus:

- **The middle school hides it inside `Hot Lunch`** as a second recipe named
  `Grab and Go-<item>`. Joined naively onto the entree it reads as one combined
  meal ("Chicken Sandwich Sliders w/ Grab and Go-Pizza Bagel Bites") rather
  than a choice between two.
- **A second `Hot Lunch` recipe is always another choice, never a component.**
  Real components arrive in the separate `With` / `Grain` / `And` categories.
  Without that split, "Domino's Pizza Slice" and "Papa Murphy's Cheese Pizza"
  merge into one impossible entree.
- **The high school uses its own category names**, `The Grill` and
  `Build Your Own`. Anything not in `ALT_CATS` is silently dropped, so an
  unknown name makes a school's alternatives vanish rather than error.

If another district shows no alternatives, dump its category names first:

```bash
python -c "import json,linq_api;d=json.loads(linq_api.fetch_menu(BID,DID,'9-1-2026')[0]);print({c['CategoryName'] for s in d['FamilyMenuSessions'] for p in s['MenuPlans'] for y in p['Days'] for m in y['MenuMeals'] for c in m['RecipeCategories']})"
```

then add them to `ALT_CATS` in `linq_parse.py`.

Allergen and Halal names come from `linq_api.district_lookups()`. If that call
fails the run continues without allergen data rather than dropping the feeds,
so a lookup outage degrades the output instead of breaking it.

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
events, and on any validation failure, so a bad fetch cannot destroy a good
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
