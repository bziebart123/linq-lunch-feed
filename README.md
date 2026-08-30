# linq-lunch-feed

Lunch menus for **Hamilton School District** (Sussex, WI) as calendar feeds you
can subscribe to. The daily menu shows up as an all-day event on every school
day, in Skylight, Google Calendar, Apple Calendar, or Outlook.

---

# For parents

**Everything you need is on one page:
[the feed list](https://bziebart123.github.io/linq-lunch-feed/).**

Open it, find your school, tap **Copy**, and follow the steps on that page. You
can stop reading here — the rest of this file is for people who want to run or
change the code.

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
- **Menus are refreshed by hand, about once a month**, after the district posts
  the next month. If a new month looks missing, it hasn't been pulled in yet.
- **Weekends, holidays, and no-school days are simply absent** — that's
  expected, not a gap in the data.

---

# For developers

Everything below is about running, changing, or reusing the code.

## Updating the feeds

```bash
python refresh.py
```

Rebuilds every feed in `config.json` for the newest posted month (next month,
falling back to the current one), validates each, and pushes. Flags:

- `--month 10-1-2026` — a specific month
- `--only maple` — just the feeds whose name matches
- `--no-push` — rebuild locally without committing
- `--base-url` / `--repo-url` — if you host it somewhere else

Per-feed `detail` in `config.json` controls how much text lands on each day:
`full` (hot lunch, fruit, vegetable, extra, bistro box), `hot+bistro`, or `hot`.
Drop it down if a wall display looks crowded.

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
| `linq_parse.py` | Parses the JSON and XML forms of that response |
| `validate_ics.py` | Standalone iCalendar validator |
| `public/` | The published feeds and the index page |
