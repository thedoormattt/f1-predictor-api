from fastapi import APIRouter, HTTPException
from app.database import get_supabase
from app.models import Race

router = APIRouter(prefix="/races", tags=["races"])


@router.get("/", response_model=list[Race])
async def list_races():
    sb = get_supabase()
    res = sb.table("races").select("*").order("round").order("type").execute()
    return res.data


@router.get("/{race_id}", response_model=Race)
async def get_race(race_id: int):
    sb = get_supabase()
    res = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Race not found")
    return res.data
