from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import races, predictions, results, leaderboard, reference
from routers import leagues

app = FastAPI(
    title="F1 Predictions League API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your Vercel URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(races.router)
app.include_router(predictions.router)
app.include_router(results.router)
app.include_router(leaderboard.router)
app.include_router(reference.router)
app.include_router(leagues.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "F1 Predictions League API"}
