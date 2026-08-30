# linq-lunch-feed

Turns Maple Avenue Elementary's (Hamilton SD, WI) LinqConnect lunch menu into a
subscribable iCalendar feed for Skylight / Google / iCloud / Outlook.

**Feed URL:** https://bziebart123.github.io/linq-lunch-feed/public/maple_ave_lunch.ics

## How it works

`.github/workflows/update-menu.yml` runs on the 25th of each month (and on
demand from the Actions tab). It fetches the current menu from the LinqConnect
public API, regenerates `public/maple_ave_lunch.ics`, and commits the result.

## Manual regeneration

```bash
curl -sS "https://api.linqconnect.com/api/FamilyMenu?buildingId=a513a71a-22d7-ee11-a71c-a811a99a3020&districtId=37aa0b35-eba0-ee11-839d-b338dc280a64&startDate=4-1-2026" -o FamilyMenu.json
python3 linq_ics.py FamilyMenu.json -o public/maple_ave_lunch.ics --detail full --name "Maple Ave Lunch"
```

`--detail` controls how much text lands on each day: `full` (default),
`hot+bistro`, or `hot` if the wall display is too busy.
