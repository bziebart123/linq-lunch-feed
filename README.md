# linq-lunch-feed

Turns Maple Avenue Elementary's (Hamilton SD, WI) LinqConnect lunch menu into a
subscribable iCalendar feed for Skylight / Google / iCloud / Outlook.

**Feed URL — paste this into Skylight:**

```
https://bziebart123.github.io/linq-lunch-feed/public/maple_ave_lunch.ics
```

Skylight: *My Skylight Menu → Synced Calendars → Sync new calendar → Calendar URL*.

## Updating the feed

```bash
python refresh.py
```

That fetches the newest posted menu (next month, falling back to the current
month), regenerates `public/maple_ave_lunch.ics`, validates it, and pushes.
GitHub Pages redeploys about a minute later. Useful flags:

- `--month 10-1-2026` — fetch a specific month
- `--detail hot+bistro` or `--detail hot` — less text per day if the wall
  display is too busy (default is `full`)
- `--no-push` — regenerate locally without committing

Run it whenever the menu looks stale — typically once a month, after the school
posts the next month's menu.

### Why this isn't automated

LinqConnect's API returns **403 to datacenter IPs**. A GitHub Actions workflow
was built and tested, and it fails on every run regardless of request headers —
the same request returns 200 from a home connection and 403 from a runner. Any
cloud-hosted scheduler (Actions, Render, Fly, Lambda) will hit the same wall, so
the fetch has to originate from a residential network. If `refresh.py` ever
reports 403 from your own machine, check whether a VPN is on.

## Safety guarantees

`refresh.py` will not publish over a good feed unless the new one is real. It
aborts if the API returns no sessions (summer months return an empty list), if
the generated calendar has zero events, or if `validate_ics.py` fails. That
validator enforces CRLF line endings, balanced `BEGIN`/`END` blocks, all-day
`DTSTART`/`DTEND` spans of exactly one day, unique UIDs, and no line over 75
octets. `.gitattributes` marks `*.ics` binary so git never rewrites the CRLF
that RFC 5545 requires.

Validate any feed by hand with:

```bash
python validate_ics.py public/maple_ave_lunch.ics
```

## Files

| File | Purpose |
|---|---|
| `refresh.py` | Fetch → generate → validate → push. The only command you need. |
| `linq_ics.py` | Builds the `.ics` from a LinqConnect response |
| `linq_parse.py` | Parses both the JSON and XML forms of that response |
| `validate_ics.py` | Standalone iCalendar validator |
| `public/maple_ave_lunch.ics` | The published feed |

## Source data

```
GET https://api.linqconnect.com/api/FamilyMenu
      ?buildingId=a513a71a-22d7-ee11-a71c-a811a99a3020   # Maple Avenue Elementary
      &districtId=37aa0b35-eba0-ee11-839d-b338dc280a64   # Hamilton School District
      &startDate=M-D-YYYY
```

Requires a browser `User-Agent`; plain `curl` gets a 403.
