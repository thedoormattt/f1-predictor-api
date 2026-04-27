import random
import string
from fastapi import APIRouter, HTTPException, Depends
from app.database import get_supabase
from app.dependencies import verify_token
from pydantic import BaseModel

router = APIRouter(prefix="/leagues", tags=["leagues"])


class LeagueCreate(BaseModel):
    name: str


def generate_code(length=6) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


@router.get("/")
async def list_my_leagues(user_id: str = Depends(verify_token)):
    sb = get_supabase()
    res = sb.table("league_members").select(
        "league_id, leagues(id, name, invite_code, created_by)"
    ).eq("player_id", user_id).execute()
    return [r["leagues"] for r in res.data]


@router.post("/")
async def create_league(
    body: LeagueCreate,
    user_id: str = Depends(verify_token),
):
    sb = get_supabase()
    code = generate_code()
    league = sb.table("leagues").insert({
        "name":        body.name,
        "invite_code": code,
        "created_by":  user_id,
    }).execute().data[0]

    sb.table("league_members").insert({
        "league_id": league["id"],
        "player_id": user_id,
    }).execute()
    return league


@router.post("/join")
async def join_league(
    invite_code: str,
    user_id: str = Depends(verify_token),
):
    sb = get_supabase()
    league = sb.table("leagues").select("*").eq(
        "invite_code", invite_code.upper()
    ).single().execute()

    if not league.data:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    sb.table("league_members").upsert({
        "league_id": league.data["id"],
        "player_id": user_id,
    }, on_conflict="league_id,player_id").execute()
    return league.data


@router.get("/{league_id}/leaderboard")
async def get_league_leaderboard(league_id: int):
    sb = get_supabase()
    res = sb.table("league_leaderboard").select("*").eq(
        "league_id", league_id
    ).order("position").execute()
    return res.data


@router.get("/{league_id}/cumulative")
async def get_league_cumulative(league_id: int):
    sb = get_supabase()
    res = sb.table("league_cumulative").select("*").eq(
        "league_id", league_id
    ).execute()
    return res.data