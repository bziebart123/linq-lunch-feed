#!/usr/bin/env python3
"""Validate that a file is well-formed iCalendar per the guarantees we care
about: CRLF line endings, balanced BEGIN/END, all-day spans of exactly one
day, unique UIDs, and no line over 75 octets."""
import datetime
import re
import sys


def validate(path):
    raw = open(path, "rb").read()
    txt = raw.decode("utf-8")
    errs = []

    if raw.count(b"\n") != raw.count(b"\r\n"):
        errs.append("line endings are not all CRLF")
    if not raw.endswith(b"\r\n"):
        errs.append("file does not end with CRLF")
    if txt.count("BEGIN:VCALENDAR") != 1 or txt.count("END:VCALENDAR") != 1:
        errs.append("unbalanced VCALENDAR")

    n_events = txt.count("BEGIN:VEVENT")
    if n_events != txt.count("END:VEVENT"):
        errs.append("unbalanced BEGIN/END:VEVENT")
    if n_events < 1:
        errs.append("no events")

    ds = re.findall(r"DTSTART;VALUE=DATE:(\d{8})", txt)
    de = re.findall(r"DTEND;VALUE=DATE:(\d{8})", txt)
    if not (len(ds) == len(de) == n_events):
        errs.append(f"DTSTART/DTEND count mismatch ({len(ds)}/{len(de)}/{n_events})")
    for a, b in zip(ds, de):
        delta = (datetime.datetime.strptime(b, "%Y%m%d")
                 - datetime.datetime.strptime(a, "%Y%m%d"))
        if delta != datetime.timedelta(days=1):
            errs.append(f"event {a} spans {delta.days} days, expected 1")

    uids = re.findall(r"^UID:(.+)$", txt, re.M)
    if len(uids) != n_events:
        errs.append(f"UID count {len(uids)} != event count {n_events}")
    if len(uids) != len(set(uids)):
        errs.append("duplicate UIDs")

    for line in txt.split("\r\n"):
        if len(line.encode("utf-8")) > 75:
            errs.append(f"line exceeds 75 octets: {line[:40]}...")

    if errs:
        print("INVALID iCalendar:")
        for e in errs:
            print("  -", e)
        return 1
    print(f"Valid iCalendar: {n_events} events, {len(raw)} bytes, "
          f"{ds[0]}..{ds[-1]}, CRLF OK")
    return 0


if __name__ == "__main__":
    sys.exit(validate(sys.argv[1] if len(sys.argv) > 1 else "lunch.ics"))
