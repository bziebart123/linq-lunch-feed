#!/usr/bin/env python3
"""Thin client for LinqConnect's public (unauthenticated) endpoints.

Three endpoints are reachable without a login:

  FamilyDistrictSearch?searchText=   -> districts matching a name
  FamilyMenuIdentifier?identifier=   -> a district's buildings, by district code
  FamilyMenu?buildingId=&districtId=&startDate=&endDate=  -> the menu itself

Two quirks are load-bearing and easy to miss:

  * A browser User-Agent is mandatory. Plain clients get HTTP 403.
  * FamilyMenu needs an explicit endDate. With startDate alone it silently
    returns only the first WEEK of the month, with no error and nothing in the
    response indicating the result is partial.
"""

import calendar
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.linqconnect.com/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class LinqError(RuntimeError):
    pass


def _get(endpoint, **params):
    url = f"{BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://linqconnect.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise LinqError(
                "HTTP 403 from LinqConnect. It blocks datacenter and VPN IPs - "
                "run this from a home connection with any VPN turned off."
            ) from e
        raise LinqError(f"HTTP {e.code} from {endpoint}") from e
    except urllib.error.URLError as e:
        raise LinqError(f"Could not reach LinqConnect: {e.reason}") from e
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise LinqError(f"{endpoint} returned non-JSON data") from e


def search_districts(text):
    """[{DistrictId, Identifier, Name, City, State}, ...] matching `text`."""
    return _get("FamilyDistrictSearch", searchText=text).get("Data") or []


def district_lookups(district_id):
    """GUID -> name maps for allergens and religious restrictions.

    The menu response tags each recipe with allergen GUIDs and nothing else.
    This endpoint is what turns them into "Milk", "Wheat", "Halal".
    """
    d = _get("FamilyMenuFilter", districtId=district_id)
    return {
        "allergens": d.get("Allergies") or {},
        "religious": d.get("ReligiousRestrictions") or {},
        "sessions": d.get("ServingSessions") or {},
    }


def district_buildings(identifier):
    """District code (e.g. 'ZHSWGT') -> {DistrictId, DistrictName, Buildings}."""
    d = _get("FamilyMenuIdentifier", identifier=identifier)
    if not d.get("DistrictId"):
        raise LinqError(f"No district found for identifier {identifier!r}")
    return d


def month_range(month):
    """'M-1-YYYY' -> (startDate, endDate) covering that whole month."""
    m, _, y = (int(x) for x in month.split("-"))
    return f"{m}-1-{y}", f"{m}-{calendar.monthrange(y, m)[1]}-{y}"


def fetch_menu(building_id, district_id, month):
    """Return the raw FamilyMenu JSON bytes, or None if nothing is posted."""
    start, end = month_range(month)
    data = _get("FamilyMenu", buildingId=building_id, districtId=district_id,
                startDate=start, endDate=end)
    sessions = data.get("FamilyMenuSessions") or []
    n_days = sum(len(p.get("Days") or [])
                 for s in sessions for p in (s.get("MenuPlans") or []))
    if not sessions or not n_days:
        return None, 0
    return json.dumps(data).encode("utf-8"), n_days
