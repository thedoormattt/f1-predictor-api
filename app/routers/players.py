from fastapi import APIRouter, Header, HTTPException
from app.database import get_supabase
from pydantic import BaseModel

router = APIRouter(prefix="/players", tags=["players"])


class PlayerCreate(BaseModel):
    name: str


@router.post("/")
async def create_player(
    body: PlayerCreate,
    x_player_id: str = Header(..., alias="X-Player-Id"),
):
    sb = get_supabase()

    existing = sb.table("players").select("id").eq("id", x_player_id).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Player already exists")

    res = sb.table("players").insert({
        "id":   x_player_id,
        "name": body.name,
    }).execute()

    return res.data[0]


@router.get("/me")
async def get_me(x_player_id: str = Header(..., alias="X-Player-Id")):
    sb = get_supabase()
    res = sb.table("players").select("*").eq("id", x_player_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Player not found")
    return res.data


@router.get("/")
async def list_players():
    sb = get_supabase()
    res = sb.table("players").select("id, name").order("name").execute()
    return res.data