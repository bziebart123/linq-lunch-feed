#!/usr/bin/env python3
"""
linq_pdf.py - One-page printable lunch calendar for a school month.

A data-driven port of the original hand-edited lunch_menu_template.py: same
landscape-letter layout, teal header, weekday grid, and colour coding, but the
menu comes from the LinqConnect API instead of a dict edited by hand, and the
per-child checkbox row is gone so the sheet suits any family.

Output is deterministic - the same menu always produces byte-identical PDF
bytes - so a weekly rebuild that finds no menu change produces no commit.
"""

import calendar
import datetime

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(letter)
MARGIN = 0.35 * inch

TEAL = HexColor("#00838f")
GRAY_LINE = HexColor("#cccccc")
GRAY_TEXT = HexColor("#888888")
GRAY_BG = HexColor("#f5f5f3")
NO_SCHOOL_BG = HexColor("#fff3e0")
NO_SCHOOL_FG = HexColor("#e65100")
PENDING_BG = HexColor("#fafafa")
HOT_FG = HexColor("#1a1a1a")
FRUIT_FG = HexColor("#2e7d32")
VEG_FG = HexColor("#5d4037")
EXTRA_FG = HexColor("#6a1b9a")
BISTRO_RED = HexColor("#c62828")

ALLERGEN_FG = HexColor("#6b6b6b")

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# Short codes keep allergens to one quiet line on the standard sheet. The
# allergen sheet spells them out instead.
ALLERGEN_CODES = {
    "Egg": "E", "Milk": "M", "Wheat": "W", "Soy": "S",
    "Sesame Seeds": "Se", "Sesame": "Se", "Fish": "F",
    "Shellfish": "SF", "Peanut": "P", "Peanuts": "P",
    "Tree Nuts": "TN", "Tree Nut": "TN",
}


def allergen_code(name):
    return ALLERGEN_CODES.get(name) or name[:2].title()


def legend_for(names):
    """'E=Egg, M=Milk, ...' for whatever allergens appear this month."""
    seen = {}
    for n in names:
        seen.setdefault(allergen_code(n), n)
    return ", ".join(f"{c}={seen[c]}" for c in sorted(seen))


def school_year(month, year):
    """A month maps to the school year it falls in (Aug-Dec -> Y/Y+1)."""
    return f"{year}–{year + 1}" if month >= 7 else f"{year - 1}–{year}"


def _wrap(c, text, font, size, max_w, max_lines):
    """Greedy word wrap, ellipsising only if the text overruns max_lines."""
    words = text.split()
    lines = []
    cur = ""
    truncated = False
    for i, w in enumerate(words):
        trial = (cur + " " + w).strip()
        if c.stringWidth(trial, font, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                truncated = True
                cur = ""
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if truncated and lines:
        last = lines[-1]
        while (c.stringWidth(last + "…", font, size) > max_w
               and len(last) > 3):
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def build_pdf(MENU, month, year, school_name, out_path,
              note="", last_posted_day=None, detail="full", no_school=None):
    """Render one month for one school onto a single landscape page.

    MENU maps day-of-month -> cell dict (falsy for a no-school day). Weekdays
    missing from MENU are treated as no-school, except those after
    `last_posted_day`, which are drawn as not-yet-posted rather than falsely
    claiming there is no school that day.

    Returns out_path, or None if the month has no menu data at all.
    """
    total_days = calendar.monthrange(year, month)[1]
    no_school = no_school or {}
    allergen_sheet = detail == "allergens"
    if last_posted_day is None:
        served = [d for d, v in MENU.items() if v]
        last_posted_day = max(served) if served else 0

    # Only the allergens actually used this month go in the footer legend.
    used_allergens = set()
    for v in MENU.values():
        if not v:
            continue
        used_allergens.update(v.get("allergens") or [])
        for a in v.get("alts") or []:
            used_allergens.update(a.get("allergens") or [])
        if allergen_sheet:
            used_allergens.update(v.get("side_allergens") or [])

    # Build the Mon-Fri grid, dropping any week with no menu at all (spring
    # break, winter break) so the calendar stays on a single sheet.
    weeks = []
    for d in range(1, total_days + 1):
        dow = datetime.date(year, month, d).weekday()
        if dow >= 5:
            continue
        if dow == 0 or not weeks:
            weeks.append([None] * 5)
        weeks[-1][dow] = d
    weeks = [w for w in weeks if any(d and MENU.get(d) for d in w)]
    if not weeks:
        return None

    rows = len(weeks)
    cols = 5
    ux = MARGIN
    uw = PAGE_W - 2 * MARGIN
    header_h = 0.42 * inch
    # The allergen legend needs a second footer line.
    footer_h = (0.34 if used_allergens else 0.2) * inch
    day_header_h = 0.2 * inch
    grid_top = PAGE_H - MARGIN - header_h
    grid_bottom = MARGIN + footer_h
    cell_w = uw / cols
    cell_h = (grid_top - grid_bottom - day_header_h) / rows

    # invariant=1 strips the creation timestamp and document id, so identical
    # input yields identical bytes and no spurious weekly commit.
    c = canvas.Canvas(out_path, pagesize=landscape(letter), invariant=1)
    c.setTitle("{} Lunch, {} {}".format(
        school_name, MONTH_NAMES[month - 1], year))
    c.setAuthor("Hamilton School District lunch feeds")
    c.setSubject("Printable monthly lunch menu")

    # Header
    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(TEAL)
    c.drawString(ux, PAGE_H - MARGIN - 16, school_name)
    c.setFont("Helvetica", 10)
    c.setFillColor(BISTRO_RED if allergen_sheet else black)
    c.drawString(ux, PAGE_H - MARGIN - 29,
                 "Lunch Menu: Allergens" if allergen_sheet else "Lunch Menu")

    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(TEAL)
    c.drawRightString(ux + uw, PAGE_H - MARGIN - 16,
                      "{} {}".format(MONTH_NAMES[month - 1], year))
    c.setFont("Helvetica", 8)
    c.setFillColor(GRAY_TEXT)
    c.drawRightString(ux + uw, PAGE_H - MARGIN - 29,
                      "{} School Year".format(school_year(month, year)))

    # Day-of-week header band
    hdr_y = grid_top - day_header_h
    c.setFillColor(TEAL)
    c.rect(ux, hdr_y, uw, day_header_h, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8.5)
    for col, name in enumerate(DAY_NAMES):
        c.drawCentredString(ux + col * cell_w + cell_w / 2, hdr_y + 5.5, name)

    for row_i, week in enumerate(weeks):
        for col_i, day_num in enumerate(week):
            x = ux + col_i * cell_w
            y = hdr_y - (row_i + 1) * cell_h
            cell = MENU.get(day_num) if day_num else None
            pending = bool(day_num) and not cell and day_num > last_posted_day

            if day_num is None:
                bg = GRAY_BG
            elif pending:
                bg = PENDING_BG
            elif not cell:
                bg = NO_SCHOOL_BG
            else:
                bg = white
            c.setFillColor(bg)
            c.rect(x, y, cell_w, cell_h, fill=1, stroke=0)
            c.setStrokeColor(GRAY_LINE)
            c.setLineWidth(0.5)
            c.rect(x, y, cell_w, cell_h, fill=0, stroke=1)

            if day_num is None:
                continue

            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(TEAL)
            c.drawString(x + 4, y + cell_h - 12, str(day_num))

            if not cell:
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(GRAY_TEXT if pending else NO_SCHOOL_FG)
                label = "NOT YET POSTED" if pending else "NO SCHOOL"
                reason = None if pending else no_school.get(day_num)
                c.drawCentredString(x + cell_w / 2,
                                    y + cell_h / 2 + (2 if reason else -2), label)
                if reason:
                    # The district names its closures, so say why.
                    c.setFont("Helvetica", 7)
                    c.setFillColor(GRAY_TEXT)
                    c.drawCentredString(x + cell_w / 2, y + cell_h / 2 - 8,
                                        reason)
                continue

            pad_x = x + 4
            max_w = cell_w - 8
            top = y + cell_h - 24
            floor = y + 3

            # Collect what this cell has to say, then size it to fit. A high
            # school day carries an entree plus two or three alternatives, and
            # at a fixed font that overruns the cell and clips a line
            # mid-phrase ("Build Your Own: BYO Mac and").
            def halal_tag(item):
                return " (Halal)" if item.get("halal") else ""

            blocks = [(cell.get("hot", "") + halal_tag(cell),
                       8.5, HOT_FG, True, 3)]
            if allergen_sheet:
                # This sheet exists to make allergens readable, so they are
                # spelled out and the fruit/vegetable detail is dropped.
                if cell.get("allergens"):
                    blocks.append(("Contains: " + ", ".join(cell["allergens"]),
                                   7.5, BISTRO_RED, True, 3))
                for alt in cell.get("alts") or []:
                    blocks.append((alt["label"] + ": " + alt["items"]
                                   + halal_tag(alt), 7.6, HOT_FG, True, 2))
                    if alt.get("allergens"):
                        blocks.append(("Contains: " + ", ".join(alt["allergens"]),
                                       7, BISTRO_RED, False, 3))
                if cell.get("side_allergens"):
                    blocks.append(("Sides: " + ", ".join(cell["side_allergens"]),
                                   6.8, ALLERGEN_FG, False, 3))
            else:
                if detail == "full":
                    blocks.append((cell.get("fruit", ""), 7.2, FRUIT_FG, False, 2))
                    blocks.append((cell.get("veg", ""), 7.2, VEG_FG, False, 2))
                    blocks.append((cell.get("extra", ""), 7.2, EXTRA_FG, False, 2))
                for alt in cell.get("alts") or []:
                    blocks.append((alt["label"] + ": " + alt["items"]
                                   + halal_tag(alt), 8, BISTRO_RED, True, 2))
                # Allergens stay secondary here: one small grey line of codes,
                # with the legend in the footer.
                if cell.get("allergens"):
                    codes = ", ".join(allergen_code(a) for a in cell["allergens"])
                    blocks.append(("Contains " + codes, 6.4, ALLERGEN_FG, False, 2))
            blocks = [b for b in blocks if b[0]]

            def layout(scale):
                """Wrap every block at `scale`; return (lines, total height)."""
                out = []
                height = 0.0
                for text, size, color, bold, max_lines in blocks:
                    sz = size * scale
                    font = "Helvetica-Bold" if bold else "Helvetica"
                    wrapped = _wrap(c, text, font, sz, max_w, max_lines)
                    out.append((wrapped, sz, color, font))
                    height += len(wrapped) * (sz + 1.6 * scale) + 1.5 * scale
                return out, height

            avail = top - floor
            chosen, _h = layout(1.0)
            if _h > avail:
                for step in range(1, 13):          # down to 70% before clipping
                    scale = 1.0 - step * 0.025
                    chosen, _h = layout(scale)
                    if _h <= avail:
                        break

            ty = top
            for wrapped, sz, color, font in chosen:
                c.setFont(font, sz)
                c.setFillColor(color)
                for ln in wrapped:
                    if ty < floor:
                        break
                    c.drawString(pad_x, ty, ln)
                    ty -= sz + 1.6
                ty -= 1.5

    # Footer
    c.setFont("Helvetica", 6)
    c.setFillColor(GRAY_TEXT)
    base_y = MARGIN + 2

    if used_allergens:
        legend_y = base_y + 8
        if allergen_sheet:
            legend = ("Allergen and Halal information comes from the district "
                      "and can change. Confirm with the school before relying "
                      "on it.")
        else:
            legend = (legend_for(used_allergens)
                      + ". Codes cover the hot lunch; see the allergen sheet "
                        "for every item. Confirm with the school.")
        while c.stringWidth(legend, "Helvetica", 6) > uw and len(legend) > 10:
            legend = legend[:-2]
        c.setFillColor(ALLERGEN_FG)
        c.drawString(ux, legend_y, legend)
        c.setFillColor(GRAY_TEXT)

    if note:
        flat = " • ".join(x.strip() for x in note.splitlines() if x.strip())
        while c.stringWidth(flat, "Helvetica", 6) > uw * 0.72 and len(flat) > 10:
            flat = flat[:-2]
        c.drawString(ux, base_y, flat)
    c.drawRightString(ux + uw, base_y,
                      "Hamilton School District • LinqConnect")

    c.save()
    return out_path
