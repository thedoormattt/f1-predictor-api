import httpx
from fastapi import Header, HTTPException, Depends
from app.config import settings


async def verify_token(authorization: str = Header(...)) -> str:
    """Verify Supabase JWT and return the user UUID."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.replace("Bearer ", "")

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_anon_key,
            }
        )

    if res.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return res.json()["id"]


def require_admin(x_admin_secret: str = Header(..., alias="X-Admin-Secret")) -> None:
    if x_admin_secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Not authorised")
