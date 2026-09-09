"""
Automatic post-race scoring.

Every race result now comes entirely from OpenF1 (Driver of the Day was the
last manually entered field and has been retired), so there is nothing left for
an admin to do between a session finishing and scores appearing. This module
does that work on its own.

How it runs
-----------
`start_autoscore(app)` launches a background loop that sweeps every
`AUTOSCORE_INTERVAL_MINUTES`, plus one sweep on startup. On a free Render
instance the service sleeps when idle, so the startup sweep is what matters:
whenever the API wakes up it immediately catches up on anything it missed.

What a sweep does
-----------------
For each race that (a) started at least `*_DELAY_MINUTES` ago, (b) started
within the last `AUTOSCORE_LOOKBACK_DAYS`, and (c) has an OpenF1 session key:

  1. fetch the result from OpenF1 if there isn't a usable one stored already
  2. run scoring for every player (rolling missing predictions forward)

Both steps are idempotent, and a race with a complete result and a full set of
scores is skipped without touching OpenF1 at all. If OpenF1 hasn't published
the data yet the race is simply left for the next sweep.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import get_supabase
from app.services.race_scoring import (
    fetch_and_store_result,
    get_result_row,
    score_race,
)

log = logging.getLogger("autoscore")

_sweep_lock = asyncio.Lock()
_task: asyncio.Task | None = None


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _delay_minutes(race_type: str) -> int:
    if (race_type or "").strip().lower() == "sprint":
        return settings.autoscore_sprint_delay_minutes
    return settings.autoscore_race_delay_minutes


def _result_is_usable(result: dict | None) -> bool:
    """A result is usable once OpenF1 has given us a full podium."""
    return bool(result and result.get("p1") and result.get("p2") and result.get("p3"))


def _due_races(sb, now: datetime) -> list[dict]:
    """Races that have finished recently enough to be worth checking."""
    lookback = (now - timedelta(days=settings.autoscore_lookback_days)).isoformat()

    races = (
        sb.table("races")
        .select("id, round, location, type, race_key, scheduled_at, openf1_meeting_key, openf1_session_key")
        .gte("scheduled_at", lookback)
        .lte("scheduled_at", now.isoformat())
        .order("scheduled_at")
        .execute()
        .data
    ) or []

    due = []
    for race in races:
        if not race.get("openf1_session_key"):
            continue
        finished_at = _parse(race["scheduled_at"]) + timedelta(
            minutes=_delay_minutes(race["type"])
        )
        if now >= finished_at:
            due.append(race)
    return due


def _player_count(sb) -> int:
    return len(sb.table("players").select("id").execute().data or [])


def _score_count(sb, race_id: int) -> int:
    return len(
        sb.table("scores").select("player_id").eq("race_id", race_id).execute().data or []
    )


async def sweep_once() -> dict[int, str]:
    """Run one pass. Returns {race_id: what happened} for anything acted on."""
    if _sweep_lock.locked():
        log.info("autoscore: sweep already running, skipping")
        return {}

    async with _sweep_lock:
        sb = get_supabase()
        now = datetime.now(timezone.utc)
        summary: dict[int, str] = {}

        try:
            races = _due_races(sb, now)
        except Exception:
            log.exception("autoscore: could not list races")
            return summary

        if not races:
            return summary

        try:
            expected_players = _player_count(sb)
        except Exception:
            log.exception("autoscore: could not count players")
            return summary

        for race in races:
            race_id = race["id"]
            label = f"R{race.get('round')} {race.get('location')} {race.get('type')}"
            try:
                result = get_result_row(sb, race_id)

                if not _result_is_usable(result):
                    log.info("autoscore: fetching OpenF1 result for %s", label)
                    result = await fetch_and_store_result(sb, race)
                    if not _result_is_usable(result):
                        summary[race_id] = "result incomplete, will retry"
                        continue
                    fetched = True
                else:
                    fetched = False

                # Already fully scored and nothing new to pick up.
                if not fetched and _score_count(sb, race_id) >= expected_players > 0:
                    continue

                scores = await score_race(sb, race_id, race)
                summary[race_id] = f"scored {len(scores)} players"
                log.info("autoscore: %s — scored %d players", label, len(scores))

            except Exception as exc:
                summary[race_id] = f"failed: {exc}"
                log.warning("autoscore: %s — %s", label, exc)

        return summary


async def _loop() -> None:
    interval = max(1, settings.autoscore_interval_minutes) * 60
    # Small delay so the first sweep doesn't compete with app startup.
    await asyncio.sleep(5)
    while True:
        try:
            await sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("autoscore: sweep crashed")
        await asyncio.sleep(interval)


def start_autoscore() -> None:
    global _task
    if not settings.autoscore_enabled:
        log.info("autoscore: disabled via AUTOSCORE_ENABLED")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    log.info(
        "autoscore: started (every %d min, race +%d min, sprint +%d min)",
        settings.autoscore_interval_minutes,
        settings.autoscore_race_delay_minutes,
        settings.autoscore_sprint_delay_minutes,
    )


async def stop_autoscore() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
