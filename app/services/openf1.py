"""
OpenF1 API integration.
Docs: https://openf1.org

Fetches race results and maps them to our ResultBase schema.
Driver of the Day is NOT available in OpenF1 — entered manually via admin endpoint.
"""

import httpx
from app.models import ResultBase

OPENF1_BASE = "https://api.openf1.org/v1"


async def fetch_race_result(meeting_key: int, session_key: int) -> ResultBase:
    async with httpx.AsyncClient() as client:
        positions   = await _get_positions(client, session_key)
        fastest_lap = await _get_fastest_lap(client, session_key)
        fastest_pit = await _get_fastest_pitstop(client, session_key)
        sc_laps     = await _get_safety_car_laps(client, session_key)
        pos_gained  = await _get_most_positions_gained(client, session_key)

    if not positions:
        raise ValueError(f"No position data for session {session_key}")

    sorted_pos = sorted(positions, key=lambda x: x["position"])
    acronyms   = [p["driver_number"] for p in sorted_pos]  # mapped below

    driver_map = await _build_driver_map(session_key)

    def acronym(driver_number: int) -> str | None:
        return driver_map.get(driver_number)

    return ResultBase(
        pole            = acronym(sorted_pos[0]["driver_number"]) if sorted_pos else None,
        p1              = acronym(sorted_pos[0]["driver_number"]) if len(sorted_pos) > 0 else None,
        p2              = acronym(sorted_pos[1]["driver_number"]) if len(sorted_pos) > 1 else None,
        p3              = acronym(sorted_pos[2]["driver_number"]) if len(sorted_pos) > 2 else None,
        last_place      = acronym(sorted_pos[-1]["driver_number"]) if sorted_pos else None,
        fastest_lap     = fastest_lap,
        fastest_pitstop = fastest_pit,
        safety_car      = bool(sc_laps),
        pos_gained_winner = pos_gained,
        dotd            = None,  # manual entry only
    )


async def _build_driver_map(session_key: int) -> dict[int, str]:
    """Returns {driver_number: acronym} for a session."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{OPENF1_BASE}/drivers", params={"session_key": session_key})
        r.raise_for_status()
        return {d["driver_number"]: d["name_acronym"] for d in r.json()}


async def _get_positions(client: httpx.AsyncClient, session_key: int) -> list[dict]:
    """Final race positions — uses the last position entry per driver."""
    r = await client.get(f"{OPENF1_BASE}/position", params={"session_key": session_key})
    r.raise_for_status()
    data = r.json()

    # Keep only the final position entry per driver
    final: dict[int, dict] = {}
    for entry in data:
        dn = entry["driver_number"]
        if dn not in final or entry["date"] > final[dn]["date"]:
            final[dn] = entry

    return list(final.values())


async def _get_fastest_lap(client: httpx.AsyncClient, session_key: int) -> str | None:
    r = await client.get(f"{OPENF1_BASE}/laps", params={"session_key": session_key, "is_pit_out_lap": False})
    r.raise_for_status()
    laps = r.json()
    if not laps:
        return None

    valid = [l for l in laps if l.get("lap_duration") is not None]
    if not valid:
        return None

    fastest = min(valid, key=lambda l: l["lap_duration"])
    driver_map = await _build_driver_map(session_key)
    return driver_map.get(fastest["driver_number"])


async def _get_fastest_pitstop(client: httpx.AsyncClient, session_key: int) -> str | None:
    """Returns team acronym of fastest pitstop — OpenF1 gives pit duration per stop."""
    r = await client.get(f"{OPENF1_BASE}/pit", params={"session_key": session_key})
    r.raise_for_status()
    pits = r.json()
    if not pits:
        return None

    valid = [p for p in pits if p.get("pit_duration") is not None]
    if not valid:
        return None

    fastest = min(valid, key=lambda p: p["pit_duration"])

    # Get team for this driver
    drivers_r = await client.get(f"{OPENF1_BASE}/drivers", params={
        "session_key": session_key,
        "driver_number": fastest["driver_number"]
    })
    drivers_r.raise_for_status()
    drivers = drivers_r.json()
    if not drivers:
        return None

    # Map full team name to acronym used in predictions
    team_name = drivers[0].get("team_name", "")
    return _team_name_to_acronym(team_name)


async def _get_safety_car_laps(client: httpx.AsyncClient, session_key: int) -> list[dict]:
    r = await client.get(f"{OPENF1_BASE}/race_control", params={
        "session_key": session_key,
        "category": "SafetyCar",
    })
    r.raise_for_status()
    return [e for e in r.json() if "SAFETY CAR" in e.get("message", "").upper()]


async def _get_most_positions_gained(client: httpx.AsyncClient, session_key: int) -> str | None:
    """
    Compares grid position to race finish position.
    Returns acronym of driver who gained the most places.
    """
    # Get starting grid from qualifying session — would need meeting_key lookup
    # For now returns None; can be enhanced with qualifying session data
    return None


def _team_name_to_acronym(team_name: str) -> str | None:
    mapping = {
        "McLaren":        "MCL",
        "Mercedes":       "MER",
        "Ferrari":        "FER",
        "Red Bull":       "RBR",
        "Aston Martin":   "AMR",
        "Alpine":         "ALP",
        "Sauber":         "SAU",
        "Haas":           "HAS",
        "Racing Bulls":   "RBU",
        "Williams":       "WIL",
    }
    for key, acronym in mapping.items():
        if key.lower() in team_name.lower():
            return acronym
    return None
