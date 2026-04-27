from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.routers import races, predictions, results, leaderboard, reference, players, leagues

app = FastAPI(
    title="F1 Predictions League API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(races.router)
app.include_router(predictions.router)
app.include_router(results.router)
app.include_router(leaderboard.router)
app.include_router(reference.router)
app.include_router(players.router)
app.include_router(leagues.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "F1 Predictions League API"}


@app.get("/docs", include_in_schema=False)
async def custom_swagger(secret: str = "") -> HTMLResponse:
    if secret != settings.secret_key:
        raise HTTPException(status_code=404)
    return get_swagger_ui_html(
        openapi_url=f"/openapi.json?secret={secret}",
        title="F1 API Docs"
    )


@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi(secret: str = "") -> JSONResponse:
    if secret != settings.secret_key:
        raise HTTPException(status_code=404)
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    return JSONResponse(openapi_schema)