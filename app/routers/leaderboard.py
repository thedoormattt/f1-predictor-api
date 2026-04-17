from fastapi import APIRouter
from app.database import get_supabase
from app.models import LeaderboardEntry, CumulativeEntry

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/", response_model=list[LeaderboardEntry])
async def get_leaderboard():
    """Current standings — reads from the leaderboard view."""
    sb = get_supabase()
    res = sb.table("leaderboard").select("*").order("position").execute()
    return res.data


@router.get("/cumulative", response_model=list[CumulativeEntry])
async def get_cumulative():
    """
    Cumulative scores per player per race — used for the chart.
    Returns all players x all scored races, ordered by round.
    """
    sb = get_supabase()
    res = sb.table("cumulative_scores").select("*").execute()
    return res.data
