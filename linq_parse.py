#!/usr/bin/env python3
"""
linq_parse.py — Convert a LinqConnect FamilyMenu response into the MENU dict
used by lunch_menu_template.py.

Handles BOTH formats the LinqConnect API can return:
  - XML  (DataContract serializer; namespace .../Titan.Model.Family.Menu)
  - JSON (same shape, PascalCase keys)

The API auto-negotiates on the Accept header. If you save the response from
DevTools you'll usually get JSON; a raw browser hit to the URL can yield XML.
This module sniffs the first non-space byte and parses accordingly, so you
don't have to care which one you saved.

Usage (standalone, to eyeball the result):
    python3 linq_parse.py FamilyMenu.xml --session Lunch

Usage (from the template):
    from linq_parse import build_menu
    MENU, meta = build_menu("FamilyMenu.xml", session="Lunch")
    # meta has: month, year, plan_name, session, school_days (sorted list)
"""

import json
import re
import sys
import xml.etree.ElementTree as ET

NS = "{http://schemas.datacontract.org/2004/07/Titan.Model.Family.Menu}"


# ── How LinqConnect recipe categories map onto the template's cell fields ──
# The template cell has: hot (bold), fruit (green), veg (brown),
# extra (purple), bistro (bold red).
#
# LinqConnect emits these category names (seen in Hamilton SD elementary lunch):
#   Hot Lunch, With, Grain, Fruit, Vegetable, Extra Item, Condiment, Bistro, And
#
# "With"/"Grain"/"And" are sub-components of the hot entree (e.g. Pancakes +
# "With" Sausage Links). "Condiment" (Syrup, etc.) is minor — folded into extra.
HOT_CATS   = ("Hot Lunch", "With", "Grain", "And")
FRUIT_CATS = ("Fruit",)
VEG_CATS   = ("Vegetable",)
EXTRA_CATS = ("Extra Item", "Condiment")
BISTRO_CATS = ("Bistro",)


def _clean(name: str) -> str:
    """Tidy a raw recipe name for print."""
    if not name:
        return ""
    s = name.strip()
    s = re.sub(r"\s+", " ", s)          # collapse double spaces
    s = s.replace(" ^", "").replace("^", "")   # drop Halal marker glyph
    return s.strip()


def _strip_bistro(name: str) -> str:
    """'Bistro Box (Cereal)' -> 'Cereal'; 'Bistro Variety (...)' -> '' (filler)."""
    s = _clean(name)
    if s.lower().startswith("bistro variety"):
        return ""  # "Weekly Extras Available" placeholder — not a real choice
    m = re.match(r"bistro box\s*\((.+)\)\s*$", s, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return s


# ─────────────────────────── XML path ───────────────────────────

def _xml_text(elem, tag):
    x = elem.find(NS + tag)
    return x.text if x is not None else None


def _parse_xml(raw: str):
    root = ET.fromstring(raw)
    sessions = []
    for s in root.find(NS + "FamilyMenuSessions"):
        session_name = _xml_text(s, "ServingSession")
        days = []
        for plan in s.find(NS + "MenuPlans"):
            plan_name = _xml_text(plan, "MenuPlanName")
            for day in plan.find(NS + "Days"):
                date = _xml_text(day, "Date")
                cats = []
                for meal in day.find(NS + "MenuMeals"):
                    rc = meal.find(NS + "RecipeCategories")
                    if rc is None:
                        continue
                    for cat in rc:
                        cname = _xml_text(cat, "CategoryName")
                        recs = [
                            _xml_text(r, "RecipeName")
                            for r in cat.find(NS + "Recipes")
                        ]
                        cats.append((cname, recs))
                days.append((date, cats))
        sessions.append((session_name, plan_name, days))
    return sessions


# ─────────────────────────── JSON path ───────────────────────────

def _parse_json(raw: str):
    d = json.loads(raw)
    sessions = []
    for s in d.get("FamilyMenuSessions", []):
        session_name = s.get("ServingSession")
        days = []
        for plan in s.get("MenuPlans", []):
            plan_name = plan.get("MenuPlanName")
            for day in plan.get("Days", []):
                date = day.get("Date")
                cats = []
                for meal in day.get("MenuMeals", []):
                    for cat in meal.get("RecipeCategories", []):
                        cname = cat.get("CategoryName")
                        recs = [r.get("RecipeName") for r in cat.get("Recipes", [])]
                        cats.append((cname, recs))
                days.append((date, cats))
        sessions.append((session_name, plan_name, days))
    return sessions


# ─────────────────────────── public API ───────────────────────────

def _load(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    stripped = raw.lstrip()
    if stripped.startswith("<"):
        return _parse_xml(raw)
    return _parse_json(raw)


def build_menu(path, session="Lunch"):
    """
    Returns (MENU, meta).
      MENU: {day_number: {"hot":..,"fruit":..,"veg":..,"extra":..,"bistro":..}}
      meta: {"month","year","plan_name","session","school_days"}
    Only day-of-month is used as the key, matching the template. All returned
    days fall in a single month (the modal month of the response); if a
    response ever straddles two months, pass a tighter date range to the API.
    """
    sessions = _load(path)
    if not sessions:
        raise ValueError("No FamilyMenuSessions found in response.")

    # pick requested session, else first
    chosen = None
    for name, plan_name, days in sessions:
        if name and session and name.lower() == session.lower():
            chosen = (name, plan_name, days)
            break
    if chosen is None:
        chosen = sessions[0]
    session_name, plan_name, days = chosen

    # figure out the modal (month, year) so a stray edge day can't skew it
    from collections import Counter
    mc = Counter()
    parsed_days = []
    for date, cats in days:
        m, d, y = (int(x) for x in date.split("/"))
        mc[(m, y)] += 1
        parsed_days.append((m, d, y, cats))
    (month, year), _ = mc.most_common(1)[0]

    MENU = {}
    for m, d, y, cats in parsed_days:
        if (m, y) != (month, year):
            continue
        hot, fruit, veg, extra, bistro = [], [], [], [], []
        def _dedupe(seq):
            seen, out = set(), []
            for x in seq:
                if x not in seen:
                    seen.add(x); out.append(x)
            return out
        for cname, recs in cats:
            names = _dedupe([_clean(n) for n in recs if _clean(n)])
            if cname in HOT_CATS:
                hot += names
            elif cname in FRUIT_CATS:
                fruit += names
            elif cname in VEG_CATS:
                veg += names
            elif cname in EXTRA_CATS:
                extra += names
            elif cname in BISTRO_CATS:
                b = [_strip_bistro(n) for n in recs]
                bistro += [x for x in b if x]
        def _ddup(seq):
            seen, out = set(), []
            for x in seq:
                if x not in seen:
                    seen.add(x); out.append(x)
            return out
        hot, fruit, veg, extra, bistro = map(_ddup, (hot, fruit, veg, extra, bistro))
        cell = {}
        if hot:
            # first is the entree; join sub-items with "w/"
            cell["hot"] = hot[0] + (" w/ " + ", ".join(hot[1:]) if len(hot) > 1 else "")
        else:
            cell["hot"] = ""
        if fruit:
            cell["fruit"] = ", ".join(fruit)
        if veg:
            cell["veg"] = ", ".join(veg)
        if extra:
            cell["extra"] = ", ".join(extra)
        if bistro:
            cell["bistro"] = bistro[0]  # primary box; extras dropped
        MENU[d] = cell

    meta = {
        "month": month,
        "year": year,
        "plan_name": plan_name,
        "session": session_name,
        "school_days": sorted(MENU.keys()),
    }
    return MENU, meta


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "FamilyMenu.xml"
    sess = "Lunch"
    if "--session" in sys.argv:
        sess = sys.argv[sys.argv.index("--session") + 1]
    MENU, meta = build_menu(path, session=sess)
    print(f"# session={meta['session']}  plan={meta['plan_name']}")
    print(f"# month={meta['month']}  year={meta['year']}  "
          f"school_days={meta['school_days']}")
    print("MENU = {")
    for day in sorted(MENU):
        print(f"    {day}: {MENU[day]!r},")
    print("}")
