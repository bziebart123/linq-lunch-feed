#!/usr/bin/env python3
"""
linq_parse.py - Convert a LinqConnect FamilyMenu response into the MENU dict
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
# The entree comes from "Hot Lunch". "With"/"Grain"/"And" are sub-components of
# it (Pancakes + "And" Sausage Links). A *second* recipe inside "Hot Lunch" is
# never a component. It is another choice for that day, such as "Domino's Pizza
# Slice" or "Papa Murphy's Cheese Pizza". "Condiment" (Syrup, etc.) is minor,
# so it is folded into extra.
ENTREE_CAT      = "Hot Lunch"
COMPONENT_CATS  = ("With", "Grain", "And")
FRUIT_CATS = ("Fruit",)
VEG_CATS   = ("Vegetable",)
EXTRA_CATS = ("Extra Item", "Condiment", "Dessert")

# Alternative lunch options: a student picks ONE of these *instead of* the hot
# entree, so they must never be joined onto it. Each school level names them
# differently. Elementary and intermediate use "Bistro", the middle school
# "Grab n Go", the high school "The Grill" and "Build Your Own".
ALT_CATS = {
    "Bistro":         "Bistro Box",
    "Grab n Go":      "Grab & Go",
    "Grab and Go":    "Grab & Go",
    "The Grill":      "The Grill",
    "Build Your Own": "Build Your Own",
}
# The middle school hides its alternative inside the Hot Lunch category as a
# second recipe named "Grab and Go-<item>". Left alone, the entree and the
# alternative get merged into one nonsensical combined meal.
GRAB_RE = re.compile(r"^grab\s*(?:and|n)\s*go\s*[-:–]?\s*", re.IGNORECASE)


def _clean(name: str) -> str:
    """Tidy a raw recipe name for print."""
    if not name:
        return ""
    s = name.strip()
    s = re.sub(r"\s+", " ", s)          # collapse double spaces
    s = s.replace(" ^", "").replace("^", "")   # drop Halal marker glyph
    # Secondary-school recipes carry a school-code suffix ("Hamburger-HS",
    # "Cheese Pizza Slice- HS") that is pure noise on that school's own menu.
    s = re.sub(r"\s*-\s*(HS|MS|IS|SSIS|TMS)\s*$", "", s)
    return s.strip()


def _strip_bistro(name: str) -> str:
    """'Bistro Box (Cereal)' -> 'Cereal'; 'Bistro Variety (...)' -> '' (filler)."""
    s = _clean(name)
    if s.lower().startswith("bistro variety"):
        return ""  # "Weekly Extras Available" placeholder, not a real choice
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
                        # The XML form carries no allergen data; callers get
                        # empty lists rather than wrong ones.
                        recs = [
                            {"name": _xml_text(r, "RecipeName"),
                             "allergens": [], "religious": []}
                            for r in cat.find(NS + "Recipes")
                        ]
                        cats.append((cname, recs))
                days.append((date, cats))
        sessions.append((session_name, plan_name, days))
    return sessions, {}


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
                        recs = [{
                            "name": r.get("RecipeName"),
                            "allergens": r.get("Allergens") or [],
                            "religious": r.get("ReligiousRestrictions") or [],
                        } for r in cat.get("Recipes", [])]
                        cats.append((cname, recs))
                days.append((date, cats))
        sessions.append((session_name, plan_name, days))

    # Named no-school days ("9/7/2026" -> "Labor Day").
    academic = {}
    for ac in d.get("AcademicCalendars") or []:
        for day in ac.get("Days") or []:
            if day.get("Date") and day.get("Note"):
                academic[day["Date"]] = day["Note"].strip()
    return sessions, academic


# ─────────────────────────── public API ───────────────────────────

def _load(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    stripped = raw.lstrip()
    if stripped.startswith("<"):
        return _parse_xml(raw)
    return _parse_json(raw)


def build_menu(path, session="Lunch", lookups=None):
    """
    Returns (MENU, meta).
      MENU: {day_number: {"hot":..,"fruit":..,"veg":..,"extra":..,"bistro":..}}
      meta: {"month","year","plan_name","session","school_days"}
    Only day-of-month is used as the key, matching the template. All returned
    days fall in a single month (the modal month of the response); if a
    response ever straddles two months, pass a tighter date range to the API.
    """
    sessions, academic = _load(path)
    if not sessions:
        raise ValueError("No FamilyMenuSessions found in response.")

    lookups = lookups or {}
    allergen_names = lookups.get("allergens") or {}
    religious_names = lookups.get("religious") or {}

    def _labels(recs, key, names):
        """Decode the GUIDs on a set of recipes into sorted display names."""
        out = set()
        for r in recs:
            for guid in r.get(key) or []:
                label = names.get(guid)
                if label and label.lower() != "none":
                    out.add(label)
        return sorted(out)

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
        entrees, components, fruit, veg, extra = [], [], [], [], []
        alts = {}          # label -> [item, ...], insertion-ordered
        def _dedupe(seq):
            seen, out = set(), []
            for x in seq:
                if x not in seen:
                    seen.add(x); out.append(x)
            return out
        # Allergens are tracked per displayed item, not pooled for the whole
        # day. Pooling would imply the entree contains whatever was only ever
        # in the cookie.
        alt_allergens, alt_halal = {}, {}
        hot_recs, side_recs = [], []

        def _add_alt(label, items, recs=()):
            bucket = alts.setdefault(label, [])
            for it in items:
                if it and it not in bucket:
                    bucket.append(it)
            if recs:
                alt_allergens.setdefault(label, []).extend(recs)

        for cname, recs in cats:
            names = _dedupe([_clean(r["name"]) for r in recs if _clean(r["name"])])
            if cname == ENTREE_CAT:
                # Split off any "Grab and Go-<item>" hiding in here; it is a
                # choice instead of the entree, not part of it.
                grab_recs = [r for r in recs if GRAB_RE.match(_clean(r["name"]))]
                grabbed = [GRAB_RE.sub("", n) for n in names if GRAB_RE.match(n)]
                if grabbed:
                    _add_alt(ALT_CATS["Grab n Go"], grabbed, grab_recs)
                entrees += [n for n in names if not GRAB_RE.match(n)]
                hot_recs += [r for r in recs if not GRAB_RE.match(_clean(r["name"]))]
            elif cname in COMPONENT_CATS:
                components += names
                hot_recs += recs
            elif cname in FRUIT_CATS:
                fruit += names
                side_recs += recs
            elif cname in VEG_CATS:
                veg += names
                side_recs += recs
            elif cname in EXTRA_CATS:
                extra += names
                side_recs += recs
            elif cname in ALT_CATS:
                cleaned = [_strip_bistro(r["name"]) for r in recs]
                _add_alt(ALT_CATS[cname], [x for x in cleaned if x], recs)
        def _ddup(seq):
            seen, out = set(), []
            for x in seq:
                if x not in seen:
                    seen.add(x); out.append(x)
            return out
        entrees, components, fruit, veg, extra = map(
            _ddup, (entrees, components, fruit, veg, extra))
        cell = {}
        if entrees:
            # The first entree, plus its genuine sub-components joined by "w/".
            cell["hot"] = entrees[0] + (
                " w/ " + ", ".join(components) if components else "")
            # Any further "Hot Lunch" recipes are separate choices for the day.
            if len(entrees) > 1:
                extra_recs = [r for r in hot_recs
                              if _clean(r["name"]) in entrees[1:]]
                _add_alt("Also Offered", entrees[1:], extra_recs)
                hot_recs = [r for r in hot_recs
                            if _clean(r["name"]) not in entrees[1:]]
        else:
            cell["hot"] = ""
        if fruit:
            cell["fruit"] = ", ".join(fruit)
        if veg:
            cell["veg"] = ", ".join(veg)
        if extra:
            cell["extra"] = ", ".join(extra)

        cell["allergens"] = _labels(hot_recs, "allergens", allergen_names)
        cell["halal"] = bool(_labels(hot_recs, "religious", religious_names))
        cell["side_allergens"] = _labels(side_recs, "allergens", allergen_names)

        if alts:
            cell["alts"] = []
            for lbl, items in alts.items():
                if not items:
                    continue
                recs = alt_allergens.get(lbl, [])
                cell["alts"].append({
                    "label": lbl,
                    "items": ", ".join(items),
                    "allergens": _labels(recs, "allergens", allergen_names),
                    "halal": bool(_labels(recs, "religious", religious_names)),
                })
            # Legacy alias: the elementary Bistro Box, when there is one.
            for a in cell["alts"]:
                if a["label"] == "Bistro Box":
                    cell["bistro"] = a["items"]
                    break
        MENU[d] = cell

    # Named no-school days for this month ({7: "Labor Day"}).
    no_school = {}
    for date, note in (academic or {}).items():
        try:
            am, ad, ay = (int(x) for x in date.split("/"))
        except ValueError:
            continue
        if (am, ay) == (month, year):
            no_school[ad] = note

    meta = {
        "month": month,
        "year": year,
        "plan_name": plan_name,
        "session": session_name,
        "school_days": sorted(MENU.keys()),
        "no_school": no_school,
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
