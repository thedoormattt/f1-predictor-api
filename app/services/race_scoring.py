"""
Shared race result + scoring routines.

Used by both the admin endpoints in `routers/results.py` and the automatic
post-race scoring sweep in `services/autoscore.py`.

Note on Driver of the Day: it is not available from OpenF1 and is no longer
entered manually, so `dotd` is never written by anything in here. The column,
the model field and the scoring rule all remain, so historical scores are
preserved and stay reproducible on a rescore.
"""

import logging
from datetime import datetime, timezone

from app.models import PredictionBase, ResultBase
from app.services.openf1 import fetch_race_result
from app.services.scoring import calculate_score

log = logging.getLogger(__name__)

# Fields that must never be overwritten by an OpenF1 fetch or an admin override.
PRESERVED_RESULT_FIELDS = ("dotd",)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_result_row(sb, race_id: int) -> dict | None:
    res = sb.table("results").select("*").eq("race_id", race_id).limit(1).execute()
    return res.data[0] if res.data else None


def preserve_fields(sb, race_id: int, payload: dict) -> dict:
    """Carry stored values of read-only fields (e.g. dotd) into a new payload."""
    existing = get_result_row(sb, race_id)
    if not existing:
        payload.pop("dotd", None)
        return payload
    for field in PRESERVED_RESULT_FIELDS:
        payload[field] = existing.get(field)
    return payload


async def fetch_and_store_result(sb, race: dict) -> dict:
    """Pull a race result from OpenF1 and upsert it. Returns the stored row."""
    if not race.get("openf1_session_key"):
        raise ValueError(f"Race {race['id']} has no openf1_session_key set")

    result = await fetch_race_result(
        race["openf1_meeting_key"], race["openf1_session_key"]
    )

    payload = {
        "race_id": race["id"],
        **result.model_dump(),
        "updated_at": _now(),
    }
    payload = preserve_fields(sb, race["id"], payload)

    res = sb.table("results").upsert(payload, on_conflict="race_id").execute()
    return res.data[0]


async def rollover_predictions(
    sb, race_id: int, race_type: str, scheduled_at: str
) -> int:
    """Copy each player's most recent same-type prediction forward if they didn't submit."""
    players = sb.table("players").select("id").execute().data

    existing = (
        sb.table("predictions").select("player_id").eq("race_id", race_id).execute().data
    )
    existing_ids = {p["player_id"] for p in existing}

    missing = [p["id"] for p in players if p["id"] not in existing_ids]
    if not missing:
        return 0

    rolled_count = 0
    for player_id in missing:
        prev = (
            sb.table("predictions")
            .select("*, races!inner(scheduled_at, type)")
            .eq("player_id", player_id)
            .eq("races.type", race_type)
            .lt("races.scheduled_at", scheduled_at)
            .execute()
            .data
        )

        if not prev:
            continue

        prev.sort(key=lambda p: p["races"]["scheduled_at"], reverse=True)
        most_recent = prev[0]

        rolled = {
            k: v
            for k, v in most_recent.items()
            if k not in ("id", "race_id", "created_at", "updated_at", "races")
        }
        rolled["race_id"] = race_id
        rolled["player_id"] = player_id
        rolled["is_rollover"] = True
        rolled["updated_at"] = _now()

        sb.table("predictions").insert(rolled).execute()
        rolled_count += 1

    return rolled_count


async def score_race(sb, race_id: int, race: dict | None = None) -> list[dict]:
    """Score every player's prediction for a race. Idempotent."""
    result_row = get_result_row(sb, race_id)
    if not result_row:
        raise ValueError(f"No result stored for race {race_id}")

    if race is None:
        race = (
            sb.table("races")
            .select("id, type, scheduled_at")
            .eq("id", race_id)
            .single()
            .execute()
            .data
        )
    if race:
        await rollover_predictions(sb, race_id, race["type"], race["scheduled_at"])

    result = ResultBase(**result_row)

    preds = sb.table("predictions").select("*").eq("race_id", race_id).execute().data
    if not preds:
        raise ValueError(f"No predictions found for race {race_id}")

    scores_to_upsert = []
    for pred_data in preds:
        breakdown = calculate_score(PredictionBase(**pred_data), result)
        scores_to_upsert.append(
            {
                "player_id": pred_data["player_id"],
                "race_id": race_id,
                **breakdown.model_dump(),
                "scored_at": _now(),
            }
        )

    res = (
        sb.table("scores")
        .upsert(scores_to_upsert, on_conflict="player_id,race_id")
        .execute()
    )
    return res.data
