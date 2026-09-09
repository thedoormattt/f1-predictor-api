from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from app.database import get_supabase
from app.models import Result, Score, ResultBase
from app.dependencies import require_admin
from app.services.autoscore import sweep_once
from app.services.race_scoring import (
    fetch_and_store_result,
    preserve_fields,
    score_race,
)

router = APIRouter(prefix="/results", tags=["results"])


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


@router.post("/admin/{race_id}/fetch-openf1", response_model=Result)
async def fetch_and_save_result(
    race_id: int,
    _: None = Depends(require_admin),
):
    sb = get_supabase()
    race = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not race.data:
        raise HTTPException(status_code=404, detail="Race not found")

    try:
        return await fetch_and_store_result(sb, race.data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/admin/{race_id}/score", response_model=list[Score])
async def score_race_endpoint(
    race_id: int,
    _: None = Depends(require_admin),
):
    sb = get_supabase()
    try:
        return await score_race(sb, race_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/admin/score-all")
async def score_all_races(
    _: None = Depends(require_admin),
):
    sb = get_supabase()

    results = sb.table("results").select("race_id").execute()
    if not results.data:
        raise HTTPException(status_code=404, detail="No results found")

    summary = {}
    for row in results.data:
        race_id = row["race_id"]
        try:
            scores = await score_race(sb, race_id)
            summary[race_id] = f"{len(scores)} players scored"
        except ValueError as exc:
            summary[race_id] = str(exc)

    return {"scored": summary}


@router.post("/admin/autoscore")
async def run_autoscore_sweep(
    _: None = Depends(require_admin),
):
    """Run the automatic post-race sweep right now instead of waiting for the timer."""
    summary = await sweep_once()
    return {"swept": summary or "nothing due"}


@router.patch("/admin/{race_id}/override", response_model=Result)
async def override_result(
    race_id: int,
    body: ResultBase,
    _: None = Depends(require_admin),
):
    sb = get_supabase()
    payload = {
        **body.model_dump(exclude_none=False),
        "race_id":    race_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Driver of the Day is no longer settable — keep whatever is stored.
    payload = preserve_fields(sb, race_id, payload)

    res = sb.table("results").upsert(payload, on_conflict="race_id").execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="No result found for this race")
    return res.data[0]
