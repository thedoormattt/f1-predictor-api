from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header
from app.database import get_supabase
from app.models import Prediction, PredictionCreate

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/race/{race_id}", response_model=list[Prediction])
async def get_race_predictions(race_id: int):
    """All players' predictions for a race. Visible to everyone once race has started."""
    sb = get_supabase()

    race = sb.table("races").select("scheduled_at").eq("id", race_id).single().execute()
    if not race.data:
        raise HTTPException(status_code=404, detail="Race not found")

    scheduled_at = datetime.fromisoformat(race.data["scheduled_at"])
    if datetime.now(timezone.utc) < scheduled_at:
        raise HTTPException(status_code=403, detail="Predictions are locked until race starts")

    res = sb.table("predictions").select("*").eq("race_id", race_id).execute()
    return res.data


@router.get("/player/{player_id}", response_model=list[Prediction])
async def get_player_predictions(player_id: str):
    """All predictions for a given player."""
    sb = get_supabase()
    res = sb.table("predictions").select("*").eq("player_id", player_id).execute()
    return res.data


@router.post("/", response_model=Prediction)
async def submit_prediction(
    body: PredictionCreate,
    x_player_id: str = Header(..., alias="X-Player-Id"),
):
    """
    Submit or update a prediction. Locked once race has started.
    Expects X-Player-Id header (set by frontend after Supabase auth).
    """
    sb = get_supabase()

    # Check race exists and hasn't started
    race = sb.table("races").select("scheduled_at").eq("id", body.race_id).single().execute()
    if not race.data:
        raise HTTPException(status_code=404, detail="Race not found")

    scheduled_at = datetime.fromisoformat(race.data["scheduled_at"])
    if datetime.now(timezone.utc) >= scheduled_at:
        raise HTTPException(status_code=403, detail="Predictions are locked — race has started")

    payload = {
        **body.model_dump(),
        "player_id": x_player_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Upsert — insert or update if already submitted
    res = sb.table("predictions").upsert(
        payload,
        on_conflict="player_id,race_id"
    ).execute()

    return res.data[0]
