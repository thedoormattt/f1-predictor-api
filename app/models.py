from datetime import datetime
from pydantic import BaseModel


# ── Races ────────────────────────────────────────────────────

class Race(BaseModel):
    id: int
    round: int
    location: str
    type: str
    race_key: str
    scheduled_at: datetime
    openf1_meeting_key: int | None = None
    openf1_session_key: int | None = None


# ── Results ──────────────────────────────────────────────────

class ResultBase(BaseModel):
    pole: str | None = None
    p1: str | None = None
    p2: str | None = None
    p3: str | None = None
    last_place: str | None = None
    fastest_lap: str | None = None
    fastest_pitstop: str | None = None
    dotd: str | None = None
    safety_car: bool | None = None
    pos_gained_winner: str | None = None


class ResultCreate(ResultBase):
    race_id: int


class Result(ResultBase):
    id: int
    race_id: int
    created_at: datetime
    updated_at: datetime


# ── Predictions ──────────────────────────────────────────────

class PredictionBase(BaseModel):
    pole: str | None = None
    p1: str | None = None
    p2: str | None = None
    p3: str | None = None
    last_place: str | None = None
    fastest_lap: str | None = None
    fastest_pitstop: str | None = None
    dotd: str | None = None
    safety_car: bool | None = None
    pos_gained: str | None = None


class PredictionCreate(PredictionBase):
    race_id: int


class Prediction(PredictionBase):
    id: int
    player_id: str
    race_id: int
    submitted_at: datetime
    updated_at: datetime


# ── Scores ───────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    pole_pts: int = 0
    p1_pts: int = 0
    p2_pts: int = 0
    p3_pts: int = 0
    podium_bonus: int = 0
    podium_pts: int = 0
    last_pts: int = 0
    fl_pts: int = 0
    fp_pts: int = 0
    dotd_pts: int = 0
    sc_pts: int = 0
    gains_pts: int = 0
    total: int = 0


class Score(ScoreBreakdown):
    id: int
    player_id: str
    race_id: int
    scored_at: datetime


# ── Leaderboard ──────────────────────────────────────────────

class LeaderboardEntry(BaseModel):
    position: int
    player_id: str
    player_name: str
    total_score: int
    races_scored: int


class CumulativeEntry(BaseModel):
    player_name: str
    race_id: int
    race_key: str
    round: int
    location: str
    type: str
    scheduled_at: datetime
    race_score: int
    cumulative_score: int


# ── Drivers / Teams ──────────────────────────────────────────

class Driver(BaseModel):
    id: int
    full_name: str
    acronym: str
    number: int | None = None
    team: str | None = None
    active: bool = True


class Team(BaseModel):
    id: int
    name: str
    acronym: str
    active: bool = True
