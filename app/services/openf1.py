"""
OpenF1 API integration.
Docs: https://openf1.org

Fetches race results and maps them to our ResultBase schema.
Driver of the Day is NOT available in OpenF1 — entered manually via admin endpoint.
"""

import asyncio
import httpx
from app.models import ResultBase

OPENF1_BASE = "https://api.openf1.org/v1"
RETRY_DELAY = 5      # seconds to wait on 429
MAX_RETRIES = 3


async def _get(client: httpx.AsyncClient, url: str, params: dict = {}) -> httpx.Response:
    """GET with automatic retry on 429."""
    for attempt in range(MAX_RETRIES):
        await asyncio.sleep(0.5)  # always wait between calls
        r = await client.get(url, params=params)
        if r.status_code == 429:
            wait = RETRY_DELAY * (attempt + 1)
            await asyncio.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise httpx.HTTPStatusError(
        f"Too many retries for {url}",
        request=r.request,
        response=r,
    )


async def fetch_race_result(meeting_key: int, session_key: int) -> ResultBase:
    async with httpx.AsyncClient(timeout=30.0) as client:
        driver_map  = await _build_driver_map(client, session_key)
        positions   = await _get_positions(client, session_key)
        fastest_lap = await _get_fastest_lap(client, session_key, driver_map)
        fastest_pit = await _get_fastest_pitstop(client, session_key)
        sc_laps     = await _get_safety_car_laps(client, session_key)
        pos_gained  = await _get_most_positions_gained(client, session_key)

    if not positions:
        raise ValueError(f"No position data for session {session_key}")

    sorted_pos = sorted(positions, key=lambda x: x["position"])

    def acronym(driver_number: int) -> str | None:
        return driver_map.get(driver_number)

    return ResultBase(
        pole              = acronym(sorted_pos[0]["driver_number"]) if sorted_pos else None,
        p1                = acronym(sorted_pos[0]["driver_number"]) if len(sorted_pos) > 0 else None,
        p2                = acronym(sorted_pos[1]["driver_number"]) if len(sorted_pos) > 1 else None,
        p3                = acronym(sorted_pos[2]["driver_number"]) if len(sorted_pos) > 2 else None,
        last_place        = acronym(sorted_pos[-1]["driver_number"]) if sorted_pos else None,
        fastest_lap       = fastest_lap,
        fastest_pitstop   = fastest_pit,
        safety_car        = bool(sc_laps),
        pos_gained_winner = pos_gained,
        dotd              = None,
    )


async def _build_driver_map(client: httpx.AsyncClient, session_key: int) -> dict[int, str]:
    """Returns {driver_number: acronym} for a session."""
    r = await _get(client, f"{OPENF1_BASE}/drivers", {"session_key": session_key})
    return {d["driver_number"]: d["name_acronym"] for d in r.json()}


async def _get_positions(client: httpx.AsyncClient, session_key: int) -> list[dict]:
    """Final race positions — uses the last position entry per driver."""
    r = await _get(client, f"{OPENF1_BASE}/position", {"session_key": session_key})
    data = r.json()

    final: dict[int, dict] = {}
    for entry in data:
        dn = entry["driver_number"]
        if dn not in final or entry["date"] > final[dn]["date"]:
            final[dn] = entry

    return list(final.values())


async def _get_fastest_lap(
    client: httpx.AsyncClient,
    session_key: int,
    driver_map: dict[int, str],
) -> str | None:
    r = await _get(client, f"{OPENF1_BASE}/laps", {
        "session_key":    session_key,
        "is_pit_out_lap": False,
    })
    laps = r.json()
    if not laps:
        return None

    valid = [l for l in laps if l.get("lap_duration") is not None]
    if not valid:
        return None

    fastest = min(valid, key=lambda l: l["lap_duration"])
    return driver_map.get(fastest["driver_number"])


async def _get_fastest_pitstop(client: httpx.AsyncClient, session_key: int) -> str | None:
    r = await _get(client, f"{OPENF1_BASE}/pit", {"session_key": session_key})
    pits = r.json()
    if not pits:
        return None

    valid = [p for p in pits if p.get("pit_duration") is not None]
    if not valid:
        return None

    fastest = min(valid, key=lambda p: p["pit_duration"])

    drivers_r = await _get(client, f"{OPENF1_BASE}/drivers", {
        "session_key":   session_key,
        "driver_number": fastest["driver_number"],
    })
    drivers = drivers_r.json()
    if not drivers:
        return None

    team_name = drivers[0].get("team_name", "")
    return _team_name_to_acronym(team_name)


async def _get_safety_car_laps(client: httpx.AsyncClient, session_key: int) -> list[dict]:
    r = await _get(client, f"{OPENF1_BASE}/race_control", {
        "session_key": session_key,
        "category":    "SafetyCar",
    })
    return [e for e in r.json() if "SAFETY CAR" in e.get("message", "").upper()]


async def _get_most_positions_gained(client: httpx.AsyncClient, session_key: int) -> str | None:
    return None


def _team_name_to_acronym(team_name: str) -> str | None:
    mapping = {
        "McLaren":        "MCL",
        "Mercedes":       "MER",
        "Ferrari":        "FER",
        "Red Bull":       "RBR",
        "Aston Martin":   "AMR",
        "Alpine":         "ALP",
        "Haas":           "HAS",
        "Racing Bulls":   "RBU",
        "Williams":       "WIL",
        "Audi":           "AUD",
        "Cadillac":       "CAD",
    }
    for key, acronym in mapping.items():
        if key.lower() in team_name.lower():
            return acronym
    return None
