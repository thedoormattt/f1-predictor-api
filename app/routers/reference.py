from fastapi import APIRouter
from app.database import get_supabase
from app.models import Driver, Team
from datetime import datetime, timedelta
import httpx

router = APIRouter(prefix="/reference", tags=["reference"])

# ── Cache ─────────────────────────────────────────────────────
_enriched_cache: list = []
_enriched_expiry: datetime | None = None


@router.get("/drivers", response_model=list[Driver])
async def list_drivers():
    sb = get_supabase()
    res = sb.table("drivers").select("*").eq("active", True).order("full_name").execute()
    return res.data


@router.get("/drivers/enriched")
async def list_drivers_enriched():
    global _enriched_cache, _enriched_expiry

    # Return cached if still valid
    if _enriched_expiry and datetime.now() < _enriched_expiry and _enriched_cache:
        return _enriched_cache

    sb = get_supabase()

    # Get latest completed race session key from DB
    races = sb.table("races").select("openf1_session_key, scheduled_at") \
        .not_.is_("openf1_session_key", "null") \
        .lt("scheduled_at", datetime.now().isoformat()) \
        .order("scheduled_at", desc=True) \
        .limit(1) \
        .execute()

    session_key = races.data[0]["openf1_session_key"] if races.data else None

    # Fetch from Supabase drivers table
    db_drivers = sb.table("drivers").select("*").eq("active", True).execute().data

    # Build acronym map from DB
    db_map = {d["acronym"]: d for d in db_drivers}

    # Fetch from OpenF1 if we have a session key
    openf1_map: dict = {}
    if session_key:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.openf1.org/v1/drivers",
                    params={"session_key": session_key},
                    timeout=10.0,
                )
                if r.status_code == 200:
                    for d in r.json():
                        openf1_map[d["name_acronym"]] = {
                            "headshot_url": d.get("headshot_url"),
                            "team_colour":  f"#{d['team_colour']}" if d.get("team_colour") else None,
                            "first_name":   d.get("first_name"),
                            "last_name":    d.get("last_name"),
                        }
        except Exception:
            pass  # fall back to DB data only

    # Merge
    result = []
    for d in db_drivers:
        openf1 = openf1_map.get(d["acronym"], {})
        result.append({
            "id":          d["id"],
            "acronym":     d["acronym"],
            "full_name":   d["full_name"],
            "number":      d["number"],
            "team":        d["team"],
            "active":      d["active"],
            "headshot_url": openf1.get("headshot_url"),
            "team_colour":  openf1.get("team_colour"),
        })

    # Sort by full name
    result.sort(key=lambda x: x["full_name"])

    # Cache for 1 hour
    _enriched_cache  = result
    _enriched_expiry = datetime.now() + timedelta(hours=1)

    return result


@router.get("/teams", response_model=list[Team])
async def list_teams():
    sb = get_supabase()
    res = sb.table("teams").select("*").eq("active", True).order("name").execute()
    return res.data