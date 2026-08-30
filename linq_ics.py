#!/usr/bin/env python3
"""
linq_ics.py - Turn a LinqConnect FamilyMenu response into an .ics calendar feed.

Reuses linq_parse.build_menu() (same parser as the PDF generator), then writes a
standards-compliant iCalendar file with one all-day event per school day.

Skylight (and Google/iCloud/Outlook) can subscribe to the resulting .ics by URL.
Host the file somewhere public, such as GitHub Pages, then paste that URL
into Skylight: My Skylight Menu -> Synced Calendars ->
Sync new calendar -> Calendar URL.

Usage:
    python3 linq_ics.py FamilyMenu.xml -o maple_ave_lunch.ics
    python3 linq_ics.py FamilyMenu.xml --session Lunch --detail full

--detail:
    full   (default) : hot / fruit / veg / extra / bistro
    hot+bistro       : entree + bistro box
    hot              : entree only
"""

import argparse
import datetime
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from linq_parse import build_menu

# A stable namespace so re-generated feeds keep the same UIDs (no duplicates on
# re-sync). Tie UIDs to building + date so multiple schools never collide.
UID_DOMAIN = "linqconnect-menu.local"

# Emoji prefix makes the entree pop on a wall display. Set to "" to disable.
TITLE_PREFIX = "\U0001F374 "  # fork and knife


def _fold(line: str) -> str:
    """RFC 5545 line folding: lines >75 octets are folded with CRLF + space."""
    out = []
    raw = line.encode("utf-8")
    while len(raw) > 73:  # 75 minus room; fold on a safe boundary
        # find a UTF-8 char boundary at/under 73 bytes
        cut = 73
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


def _esc(text: str) -> str:
    """Escape text per RFC 5545 (commas, semicolons, backslashes, newlines)."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fmt_date(y, m, d):
    return f"{y:04d}{m:02d}{d:02d}"


def build_ics(menu_file, session="Lunch", detail="full",
              calendar_name="School Lunch"):
    MENU, meta = build_menu(menu_file, session=session)
    year, month = meta["year"], meta["month"]

    now = datetime.datetime.now(datetime.timezone.utc)
    dtstamp = now.strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//linqconnect-menu//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(calendar_name)}",
        "X-WR-TIMEZONE:America/Chicago",
    ]

    for day in sorted(MENU):
        cell = MENU[day]
        if cell is None:
            continue  # NO SCHOOL day; skip (nothing to show)

        hot = cell.get("hot", "").strip()
        if not hot:
            continue

        # Title
        title = TITLE_PREFIX + hot

        # Description body scales with --detail
        desc_parts = []
        if detail in ("full", "hot+bistro", "hot"):
            desc_parts.append(f"Hot Lunch: {hot}")
        if detail == "full":
            if cell.get("fruit"):
                desc_parts.append(f"Fruit: {cell['fruit']}")
            if cell.get("veg"):
                desc_parts.append(f"Vegetable: {cell['veg']}")
            if cell.get("extra"):
                desc_parts.append(f"Extra: {cell['extra']}")
        # Alternative options (Bistro Box / Grab & Go / The Grill / Build Your
        # Own / a second entree). These are picked *instead of* the hot lunch,
        # so they are always listed alongside it.
        if detail in ("full", "hot+bistro"):
            for alt in cell.get("alts") or []:
                desc_parts.append(f"{alt['label']}: {alt['items']}")
        description = "\n".join(desc_parts)

        start = _fmt_date(year, month, day)
        # All-day event: DTEND is the next day (exclusive) per RFC 5545.
        end_dt = datetime.date(year, month, day) + datetime.timedelta(days=1)
        end = _fmt_date(end_dt.year, end_dt.month, end_dt.day)

        # Stable UID: same input date -> same UID across regenerations.
        uid_seed = f"{session}-{year}-{month:02d}-{day:02d}"
        uid_hash = hashlib.sha1(uid_seed.encode()).hexdigest()[:16]
        uid = f"{uid_hash}@{UID_DOMAIN}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{start}",
            f"DTEND;VALUE=DATE:{end}",
            _fold(f"SUMMARY:{_esc(title)}"),
        ]
        if description:
            lines.append(_fold(f"DESCRIPTION:{_esc(description)}"))
        lines += [
            "TRANSP:TRANSPARENT",  # doesn't block time; it's informational
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n", meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("menu_file")
    ap.add_argument("-o", "--output", default="lunch.ics")
    ap.add_argument("--session", default="Lunch")
    ap.add_argument("--detail", default="full",
                    choices=["full", "hot+bistro", "hot"])
    ap.add_argument("--name", default="Maple Ave Lunch")
    args = ap.parse_args()

    ics, meta = build_ics(args.menu_file, session=args.session,
                          detail=args.detail, calendar_name=args.name)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        f.write(ics)

    n_events = ics.count("BEGIN:VEVENT")
    print(f"Wrote {args.output}")
    print(f"  session={meta['session']}  {meta['month']}/{meta['year']}  "
          f"events={n_events}  detail={args.detail}")


if __name__ == "__main__":
    main()
