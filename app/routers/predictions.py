from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from app.database import get_supabase
from app.models import Prediction, PredictionCreate
from app.dependencies import verify_token

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/race/{race_id}", response_model=list[Prediction])
async def get_race_predictions(
    race_id: int,
    _: str = Depends(verify_token),
):
    sb = get_supabase()
    race = sb.table("races").select("locks_at, scheduled_at").eq("id", race_id).single().execute()
    if not race.data:
        raise HTTPException(status_code=404, detail="Race not found")

    locks_at = datetime.fromisoformat(race.data.get("locks_at") or race.data["scheduled_at"])
    if datetime.now(timezone.utc) < locks_at:
        raise HTTPException(status_code=403, detail="Predictions hidden until race weekend starts")

    res = sb.table("predictions").select("*").eq("race_id", race_id).execute()
    return res.data


@router.get("/player/{player_id}", response_model=list[Prediction])
async def get_player_predictions(
    player_id: str,
    user_id: str = Depends(verify_token),
):
    if player_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another player's predictions")
    sb = get_supabase()
    res = sb.table("predictions").select("*").eq("player_id", player_id).execute()
    return res.data


@router.post("/", response_model=Prediction)
async def submit_prediction(
    body: PredictionCreate,
    user_id: str = Depends(verify_token),
):
    sb = get_supabase()
    race = sb.table("races").select("locks_at, scheduled_at").eq("id", body.race_id).single().execute()
    if not race.data:
        raise HTTPException(status_code=404, detail="Race not found")

    locks_at = datetime.fromisoformat(race.data.get("locks_at") or race.data["scheduled_at"])
    if datetime.now(timezone.utc) >= locks_at:
        raise HTTPException(status_code=403, detail="Predictions are locked — race weekend has started")

    payload = {
        **body.model_dump(),
        "player_id": user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    res = sb.table("predictions").upsert(
        payload, on_conflict="player_id,race_id"
    ).execute()
    return res.data[0]