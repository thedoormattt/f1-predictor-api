from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header
from app.database import get_supabase
from app.models import Result, ResultCreate, Score, ScoreBreakdown
from app.services.scoring import calculate_score
from app.services.openf1 import fetch_race_result
from app.config import settings

router = APIRouter(prefix="/results", tags=["results"])


# ── Public ───────────────────────────────────────────────────

@router.get("/{race_id}", response_model=Result)
async def get_result(race_id: int):
    sb = get_supabase()
    res = sb.table("results").select("*").eq("race_id", race_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="No result yet for this race")
    return res.data


@router.get("/{race_id}/scores", response_model=list[Score])
async def get_race_scores(race_id: int):
    sb = get_supabase()
    res = sb.table("scores").select("*").eq("race_id", race_id).execute()
    return res.data


# ── Admin — protected by a simple secret header ──────────────
# In production you'd replace this with a proper admin role check

def _check_admin(secret: str):
    if secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Not authorised")


@router.post("/admin/{race_id}/fetch-openf1", response_model=Result)
async def fetch_and_save_result(
    race_id: int,
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
):
    """
    Fetches result from OpenF1 and saves to DB.
    Run this after each race. DotD must be added separately.
    """
    _check_admin(x_admin_secret)
    sb = get_supabase()

    race = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not race.data:
        raise HTTPException(status_code=404, detail="Race not found")

    r = race.data
    if not r.get("openf1_session_key"):
        raise HTTPException(status_code=400, detail="Race has no openf1_session_key set")

    result = await fetch_race_result(r["openf1_meeting_key"], r["openf1_session_key"])

    payload = {
        "race_id": race_id,
        **result.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    res = sb.table("results").upsert(payload, on_conflict="race_id").execute()
    return res.data[0]


@router.patch("/admin/{race_id}/dotd", response_model=Result)
async def set_dotd(
    race_id: int,
    dotd: str,
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
):
    """Manually set Driver of the Day (not available in OpenF1)."""
    _check_admin(x_admin_secret)
    sb = get_supabase()

    res = sb.table("results").update({
        "dotd": dotd,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("race_id", race_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="No result found — fetch OpenF1 data first")
    return res.data[0]


@router.post("/admin/{race_id}/score", response_model=list[Score])
async def score_race(
    race_id: int,
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
):
    """
    Runs scoring for all players for a given race.
    Safe to re-run — upserts scores so corrections are applied cleanly.
    """
    _check_admin(x_admin_secret)
    sb = get_supabase()

    result_res = sb.table("results").select("*").eq("race_id", race_id).single().execute()
    if not result_res.data:
        raise HTTPException(status_code=404, detail="No result found — fetch OpenF1 data first")

    from app.models import ResultBase
    result = ResultBase(**result_res.data)

    preds_res = sb.table("predictions").select("*").eq("race_id", race_id).execute()
    predictions = preds_res.data

    if not predictions:
        raise HTTPException(status_code=404, detail="No predictions found for this race")

    from app.models import PredictionBase
    scores_to_upsert = []
    for pred_data in predictions:
        pred = PredictionBase(**pred_data)
        breakdown = calculate_score(pred, result)
        scores_to_upsert.append({
            "player_id": pred_data["player_id"],
            "race_id":   race_id,
            **breakdown.model_dump(),
            "scored_at": datetime.now(timezone.utc).isoformat(),
        })

    res = sb.table("scores").upsert(
        scores_to_upsert,
        on_conflict="player_id,race_id"
    ).execute()

    return res.data

@router.post("/admin/score-all", response_model=dict)
async def score_all_races(
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
):
    """Rescores all races that have results. Safe to run any time."""
    _check_admin(x_admin_secret)
    sb = get_supabase()

    results = sb.table("results").select("race_id").execute()
    if not results.data:
        raise HTTPException(status_code=404, detail="No results found")

    from app.models import PredictionBase, ResultBase

    summary = {}
    for row in results.data:
        race_id = row["race_id"]

        result_res = sb.table("results").select("*").eq("race_id", race_id).single().execute()
        result = ResultBase(**result_res.data)

        preds_res = sb.table("predictions").select("*").eq("race_id", race_id).execute()
        if not preds_res.data:
            summary[race_id] = "no predictions"
            continue

        scores_to_upsert = []
        for pred_data in preds_res.data:
            pred = PredictionBase(**pred_data)
            breakdown = calculate_score(pred, result)
            scores_to_upsert.append({
                "player_id": pred_data["player_id"],
                "race_id":   race_id,
                **breakdown.model_dump(),
                "scored_at": datetime.now(timezone.utc).isoformat(),
            })

        sb.table("scores").upsert(
            scores_to_upsert,
            on_conflict="player_id,race_id"
        ).execute()

        summary[race_id] = f"{len(scores_to_upsert)} players scored"

    return {"scored": summary}
