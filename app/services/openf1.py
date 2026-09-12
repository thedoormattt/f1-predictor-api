"""
OpenF1 API integration.
Docs: https://openf1.org

Fetches race results and maps them to our ResultBase schema.

Driver of the Day is not published by OpenF1 and has been retired — nothing here
ever sets it.

Two things worth knowing about the data:

  * The starting grid is NOT the qualifying order. Penalties, pit-lane starts and
    post-qualifying exclusions move drivers. At Monza 2026 the grid differed from
    qualifying for 15 of 22 drivers — Antonelli qualified P7 and started P19 — so
    positions gained must be measured from `/starting_grid`, never from
    qualifying positions.
  * `/starting_grid` is queried by `meeting_key` (a `session_key` query 404s) and
    its rows are tagged with the QUALIFYING session_key, not the race's. On a
    sprint weekend a meeting has two of them, so we filter by the qualifying
    session that actually set the grid for the session being scored.

Final classifications come from `/session_result`, which gives official positions
plus dnf/dns/dsq flags. Where that isn't available we fall back to the `/position`
live feed, taking each driver's last entry.
"""

import asyncio
import logging

import httpx

from app.models import ResultBase

log = logging.getLogger(__name__)

OPENF1_BASE = "https://api.openf1.org/v1"
RETRY_DELAY = 5      # seconds to wait on 429
MAX_RETRIES = 3

SPRINT_QUALI_NAMES = ("sprint qualifying", "sprint shootout")


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


async def _get_json(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    """GET a list endpoint, returning [] instead of raising on a 4xx."""
    try:
        r = await _get(client, f"{OPENF1_BASE}/{path}", params)
    except httpx.HTTPStatusError as exc:
        log.warning("openf1: %s %s -> %s", path, params, exc)
        return []
    return r.json() or []


# ── main entry point ─────────────────────────────────────────

async def fetch_race_result(meeting_key: int, session_key: int) -> ResultBase:
    async with httpx.AsyncClient(timeout=30.0) as client:
        sessions    = await _get_json(client, "sessions", {"meeting_key": meeting_key})
        quali_key   = _resolve_qualifying_session(sessions, session_key)

        driver_map  = await _build_driver_map(client, session_key)
        finish      = await _final_positions(client, session_key)
        pole        = await _get_pole_position(client, quali_key, driver_map)
        fastest_lap = await _get_fastest_lap(client, session_key, driver_map)
        fastest_pit = await _get_fastest_pitstop(client, session_key)
        safety_car  = await _safety_car_deployed(client, session_key)
        pos_gained  = await _get_most_positions_gained(
            client, meeting_key, quali_key, finish, driver_map
        )

    if not finish:
        raise ValueError(f"No position data for session {session_key}")

    order = sorted(finish.items(), key=lambda kv: kv[1])

    def acronym(driver_number: int) -> str | None:
        return driver_map.get(driver_number)

    return ResultBase(
        pole              = pole,
        p1                = acronym(order[0][0]) if len(order) > 0 else None,
        p2                = acronym(order[1][0]) if len(order) > 1 else None,
        p3                = acronym(order[2][0]) if len(order) > 2 else None,
        last_place        = acronym(order[-1][0]) if order else None,
        fastest_lap       = fastest_lap,
        fastest_pitstop   = fastest_pit,
        safety_car        = safety_car,
        pos_gained_winner = pos_gained,
        dotd              = None,
    )


# ── sessions ─────────────────────────────────────────────────

def _resolve_qualifying_session(sessions: list[dict], race_session_key: int) -> int | None:
    """
    The qualifying session that set the grid for `race_session_key`.

    A sprint weekend has both "Qualifying" and "Sprint Qualifying", so picking
    sessions[0] of session_type "Qualifying" can silently select the wrong one.
    """
    if not sessions:
        return None

    target = next((s for s in sessions if s.get("session_key") == race_session_key), None)
    target_name = (target or {}).get("session_name", "") or ""
    is_sprint = "sprint" in target_name.lower()

    def named(candidates: tuple[str, ...]) -> int | None:
        for s in sessions:
            name = (s.get("session_name") or "").lower()
            if name in candidates and not s.get("is_cancelled"):
                return s.get("session_key")
        return None

    if is_sprint:
        return named(SPRINT_QUALI_NAMES) or named(("qualifying",))
    return named(("qualifying",)) or named(SPRINT_QUALI_NAMES)


# ── classifications ──────────────────────────────────────────

def _classified(rows: list[dict]) -> dict[int, int]:
    """{driver_number: position} for drivers with an official finishing position."""
    out = {}
    for r in rows:
        pos = r.get("position")
        if pos is None or r.get("dns") or r.get("dsq"):
            continue
        out[r["driver_number"]] = pos
    return out


async def _final_positions(client: httpx.AsyncClient, session_key: int) -> dict[int, int]:
    """
    Official classification for a session, falling back to the live position feed.
    """
    classified = _classified(
        await _get_json(client, "session_result", {"session_key": session_key})
    )
    if classified:
        return classified

    log.info("openf1: no session_result for %s, using position feed", session_key)
    return await _feed_positions(client, session_key)


async def _feed_positions(client: httpx.AsyncClient, session_key: int) -> dict[int, int]:
    """Last position entry per driver from the live feed. Fallback only."""
    data = await _get_json(client, "position", {"session_key": session_key})

    latest: dict[int, dict] = {}
    for entry in data:
        dn = entry["driver_number"]
        if dn not in latest or entry["date"] > latest[dn]["date"]:
            latest[dn] = entry
    return {dn: e["position"] for dn, e in latest.items()}


# ── grid and positions gained ────────────────────────────────

async def _get_starting_grid(
    client: httpx.AsyncClient, meeting_key: int, quali_session_key: int | None
) -> dict[int, int]:
    """
    {driver_number: grid_position} for the race that `quali_session_key` set.

    Queried by meeting_key — a session_key query 404s — and the rows carry the
    qualifying session_key, so a sprint weekend returns two grids.
    """
    rows = await _get_json(client, "starting_grid", {"meeting_key": meeting_key})
    if not rows:
        return {}

    if quali_session_key is not None:
        for_session = [r for r in rows if r.get("session_key") == quali_session_key]
        if for_session:
            rows = for_session

    return {r["driver_number"]: r["position"] for r in rows if r.get("position") is not None}


async def _get_most_positions_gained(
    client: httpx.AsyncClient,
    meeting_key: int,
    quali_session_key: int | None,
    finish: dict[int, int],
    driver_map: dict[int, str],
) -> str | None:
    """
    Driver who gained the most places, measured from the actual starting grid.

    Measuring from qualifying instead is wrong whenever anyone takes a grid
    penalty, and gets the winner wrong outright when the penalised driver
    recovers (Monza 2026: Antonelli, P19 on the grid to P1, +18).
    """
    grid = await _get_starting_grid(client, meeting_key, quali_session_key)

    if not grid:
        if quali_session_key is None:
            log.warning("openf1: no qualifying session for meeting %s", meeting_key)
            return None
        log.warning(
            "openf1: no starting grid for meeting %s, falling back to qualifying order",
            meeting_key,
        )
        grid = await _final_positions(client, quali_session_key)

    if not grid or not finish:
        return None

    best_driver, best_gain = None, 0
    for driver_number, finish_pos in finish.items():
        start_pos = grid.get(driver_number)
        if start_pos is None:
            continue
        gain = start_pos - finish_pos
        if gain > best_gain:
            best_driver, best_gain = driver_number, gain

    return driver_map.get(best_driver) if best_driver is not None else None


# ── pole ─────────────────────────────────────────────────────

async def _get_pole_position(
    client: httpx.AsyncClient,
    quali_session_key: int | None,
    driver_map: dict[int, str],
) -> str | None:
    """P1 in qualifying. Deliberately the qualifying result, not the grid —
    a driver keeps pole even if a penalty drops them down the grid."""
    if quali_session_key is None:
        return None

    positions = await _final_positions(client, quali_session_key)
    if not positions:
        return None

    pole_driver = min(positions, key=lambda dn: positions[dn])
    return driver_map.get(pole_driver)


# ── drivers, laps, pitstops, safety car ──────────────────────

async def _build_driver_map(client: httpx.AsyncClient, session_key: int) -> dict[int, str]:
    """Returns {driver_number: acronym} for a session."""
    rows = await _get_json(client, "drivers", {"session_key": session_key})
    return {d["driver_number"]: d["name_acronym"] for d in rows}


async def _get_fastest_lap(
    client: httpx.AsyncClient,
    session_key: int,
    driver_map: dict[int, str],
) -> str | None:
    laps = await _get_json(client, "laps", {
        "session_key":    session_key,
        "is_pit_out_lap": False,
    })
    valid = [l for l in laps if l.get("lap_duration") is not None]
    if not valid:
        return None

    fastest = min(valid, key=lambda l: l["lap_duration"])
    return driver_map.get(fastest["driver_number"])


async def _get_fastest_pitstop(client: httpx.AsyncClient, session_key: int) -> str | None:
    pits = await _get_json(client, "pit", {"session_key": session_key})
    valid = [p for p in pits if p.get("pit_duration") is not None]
    if not valid:
        return None

    fastest = min(valid, key=lambda p: p["pit_duration"])

    drivers = await _get_json(client, "drivers", {
        "session_key":   session_key,
        "driver_number": fastest["driver_number"],
    })
    if not drivers:
        return None

    return _team_name_to_acronym(drivers[0].get("team_name", ""))


async def _safety_car_deployed(client: httpx.AsyncClient, session_key: int) -> bool:
    data = await _get_json(client, "race_control", {"session_key": session_key})
    if not data:
        raise ValueError(
            f"No race control data found for session {session_key} — check session key is correct"
        )

    return any(e.get("category") == "SafetyCar" for e in data)


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
