from fastapi import APIRouter, HTTPException, Depends
from app.database import get_supabase
from app.dependencies import verify_token
from pydantic import BaseModel

router = APIRouter(prefix="/players", tags=["players"])


class PlayerCreate(BaseModel):
    username: str
    full_name: str | None = None


@router.post("/")
async def create_player(
    body: PlayerCreate,
    user_id: str = Depends(verify_token),
):
    sb = get_supabase()
    existing = sb.table("players").select("id").eq("id", user_id).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Player already exists")

    res = sb.table("players").insert({
        "id":        user_id,
        "username":  body.username,
        "full_name": body.full_name,
    }).execute()
    return res.data[0]


@router.get("/me")
async def get_me(user_id: str = Depends(verify_token)):
    sb = get_supabase()
    res = sb.table("players").select("*").eq("id", user_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Player not found")
    return res.data


@router.get("/{player_id}/scores")
async def get_player_scores(
    player_id: str,
    _: str = Depends(verify_token),
):
    sb = get_supabase()
    res = sb.table("scores").select("*").eq("player_id", player_id).execute()
    return res.data


@router.get("/")
async def list_players():
    sb = get_supabase()
    res = sb.table("players").select("id, username").order("username").execute()
    return res.data