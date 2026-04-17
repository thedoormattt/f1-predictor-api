from fastapi import APIRouter
from app.database import get_supabase
from app.models import Driver, Team

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/drivers", response_model=list[Driver])
async def list_drivers():
    sb = get_supabase()
    res = sb.table("drivers").select("*").eq("active", True).order("full_name").execute()
    return res.data


@router.get("/teams", response_model=list[Team])
async def list_teams():
    sb = get_supabase()
    res = sb.table("teams").select("*").eq("active", True).order("name").execute()
    return res.data
