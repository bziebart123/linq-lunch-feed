# linq-lunch-feed

Subscribable lunch-menu calendars for **Hamilton School District** (Sussex, WI),
built from LinqConnect's public menu API. Point Skylight, Google Calendar,
Apple Calendar, or Outlook at a URL and the school lunch menu shows up as an
all-day event on every school day.

## Feeds

Browse them all at
**https://bziebart123.github.io/linq-lunch-feed/**

| School | Feed URL |
|---|---|
| Maple Avenue Elementary | `.../public/maple_ave_lunch.ics` |
| Hamilton High School | `.../public/hamilton_high_school_lunch.ics` |
| Lannon Elementary School | `.../public/lannon_elementary_school_lunch.ics` |
| Marcy Elementary School | `.../public/marcy_elementary_school_lunch.ics` |
| Silver Spring Intermediate | `.../public/silver_spring_intermediate_lunch.ics` |
| Templeton Middle School | `.../public/templeton_middle_school_lunch.ics` |
| Woodside Elementary School | `.../public/woodside_elementary_school_lunch.ics` |

Prefix each with `https://bziebart123.github.io/linq-lunch-feed`.

### Subscribing in Skylight

Do this from a phone or computer browser, not the frame itself:

1. Sign in at **app.ourskylight.com** and pick your frame.
2. **Calendar → Synced Calendars → Sync new calendar**.
3. Choose **Calendar by URL** — not the Google/Apple/Outlook buttons.
4. Paste your school's URL, name it, save.

Skylight refetches on its own schedule (a few hours, sometimes a day), so
updates are not instant.

## Updating

```bash
python refresh.py
```

Rebuilds every feed in `config.json` for the newest posted month (next month,
falling back to the current one), validates each, and pushes. Flags:

- `--month 10-1-2026` — a specific month
- `--only maple` — just the feeds whose name matches
- `--detail` is per-feed in `config.json`: `full`, `hot+bistro`, or `hot` if a
  wall display is too crowded
- `--no-push` — rebuild locally without committing

Run it once a month, after the district posts the next month's menus.

## Using this for a different district

Nothing about the code is specific to Hamilton — the district and school IDs
all live in `config.json`, and you can discover them:

```bash
python discover.py --search "Hamilton"                  # find your district
python discover.py --district ZHSWGT                    # list its schools
python discover.py --district ZHSWGT --add "Marcy Elementary School"
python refresh.py
```

`--add` appends a ready-made entry to `config.json`, so no GUID is ever copied
by hand. Fork the repo, clear the `feeds` list, and add your own schools.

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
  workflow was built and tested against this and fails every run, which is why
  refreshing is a manual command. If `refresh.py` reports 403, check your VPN.

## Safety

A feed is only replaced when the new one is real: `refresh.py` aborts on an
empty API response (summer months return nothing), on a calendar with zero
events, and on any validation failure. `validate_ics.py` enforces CRLF line
endings, balanced `BEGIN`/`END` blocks, all-day `DTSTART`/`DTEND` spans of
exactly one day, unique UIDs, and no line over 75 octets. `.gitattributes`
marks `*.ics` binary so git never rewrites the CRLF that RFC 5545 requires.

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
| `public/` | The published feeds and index page |
