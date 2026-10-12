"""Tests for the automatic post-race scoring sweep."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import ResultBase
from app.services import autoscore, race_scoring
from tests.fake_supabase import FakeSupabase

NOW = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def make_race(race_id=1, type_="Race", hours_ago=6, session_key=9999):
    return {
        "id": race_id,
        "round": 15,
        "location": "Monza",
        "type": type_,
        "race_key": f"r{race_id}",
        "scheduled_at": iso(NOW - timedelta(hours=hours_ago)),
        "openf1_meeting_key": 1234,
        "openf1_session_key": session_key,
    }


FULL_RESULT = ResultBase(
    pole="NOR", p1="NOR", p2="PIA", p3="VER",
    last_place="OCO", fastest_lap="RUS", fastest_pitstop="MCL",
    safety_car=False, pos_gained_winner="HAM", dotd=None,
)


@pytest.fixture
def patched_openf1(monkeypatch):
    calls = []

    async def fake_fetch(meeting_key, session_key):
        calls.append((meeting_key, session_key))
        return FULL_RESULT

    monkeypatch.setattr(race_scoring, "fetch_race_result", fake_fetch)
    return calls


# ── which races are due ──────────────────────────────────────

class TestDueRaces:
    def test_race_is_due_after_the_delay(self):
        sb = FakeSupabase(races=[make_race(hours_ago=6)])
        assert len(autoscore._due_races(sb, NOW)) == 1

    def test_race_is_not_due_immediately_after_lights_out(self):
        sb = FakeSupabase(races=[make_race(hours_ago=1)])
        assert autoscore._due_races(sb, NOW) == []

    def test_sprint_uses_the_shorter_delay(self):
        sb = FakeSupabase(races=[make_race(type_="Sprint", hours_ago=3)])
        assert len(autoscore._due_races(sb, NOW)) == 1
        sb = FakeSupabase(races=[make_race(type_="Sprint", hours_ago=1)])
        assert autoscore._due_races(sb, NOW) == []

    def test_race_without_a_session_key_is_skipped(self):
        sb = FakeSupabase(races=[make_race(session_key=None)])
        assert autoscore._due_races(sb, NOW) == []

    def test_races_beyond_the_lookback_window_are_left_alone(self):
        sb = FakeSupabase(races=[make_race(hours_ago=24 * 30)])
        assert autoscore._due_races(sb, NOW) == []

    def test_future_race_is_not_due(self):
        sb = FakeSupabase(races=[make_race(hours_ago=-24)])
        assert autoscore._due_races(sb, NOW) == []


# ── the sweep itself ─────────────────────────────────────────

def build_store(**overrides):
    base = dict(
        races=[make_race()],
        players=[{"id": "p1"}, {"id": "p2"}],
        predictions=[
            {"id": 1, "player_id": "p1", "race_id": 1, "p1": "NOR", "p2": "PIA", "p3": "VER"},
            {"id": 2, "player_id": "p2", "race_id": 1, "p1": "VER", "p2": "PIA", "p3": "NOR"},
        ],
        results=[],
        scores=[],
    )
    base.update(overrides)
    return FakeSupabase(**base)


@pytest.mark.asyncio
async def test_sweep_fetches_and_scores_a_finished_race(monkeypatch, patched_openf1):
    sb = build_store()
    monkeypatch.setattr(autoscore, "get_supabase", lambda: sb)
    monkeypatch.setattr(autoscore, "datetime", _FrozenDatetime)

    summary = await autoscore.sweep_once()

    assert summary == {1: "scored 2 players"}
    assert patched_openf1 == [(1234, 9999)]
    assert sb.store["results"][0]["p1"] == "NOR"
    assert len(sb.store["scores"]) == 2
    # p1 called the podium exactly: 10 + 8 + 6 + 5 bonus
    p1_score = next(s for s in sb.store["scores"] if s["player_id"] == "p1")
    assert p1_score["total"] == 29


@pytest.mark.asyncio
async def test_sweep_is_a_no_op_once_a_race_is_scored(monkeypatch, patched_openf1):
    sb = build_store()
    monkeypatch.setattr(autoscore, "get_supabase", lambda: sb)
    monkeypatch.setattr(autoscore, "datetime", _FrozenDatetime)

    await autoscore.sweep_once()
    patched_openf1.clear()

    assert await autoscore.sweep_once() == {}
    assert patched_openf1 == []  # OpenF1 is not called again


@pytest.mark.asyncio
async def test_sweep_retries_when_openf1_has_no_data_yet(monkeypatch):
    async def failing_fetch(meeting_key, session_key):
        raise ValueError("No position data for session 9999")

    monkeypatch.setattr(race_scoring, "fetch_race_result", failing_fetch)
    sb = build_store()
    monkeypatch.setattr(autoscore, "get_supabase", lambda: sb)
    monkeypatch.setattr(autoscore, "datetime", _FrozenDatetime)

    summary = await autoscore.sweep_once()

    assert "failed" in summary[1]
    assert sb.store["scores"] == []


@pytest.mark.asyncio
async def test_sweep_scores_a_race_that_already_has_a_result(monkeypatch, patched_openf1):
    sb = build_store(results=[{"id": 1, "race_id": 1, **FULL_RESULT.model_dump()}])
    monkeypatch.setattr(autoscore, "get_supabase", lambda: sb)
    monkeypatch.setattr(autoscore, "datetime", _FrozenDatetime)

    summary = await autoscore.sweep_once()

    assert summary == {1: "scored 2 players"}
    assert patched_openf1 == []  # stored result was reused


# ── driver of the day is never written, but still scores ─────

@pytest.mark.asyncio
async def test_openf1_fetch_never_clears_a_stored_dotd(patched_openf1):
    sb = build_store(results=[{"id": 1, "race_id": 1, "p1": "NOR", "dotd": "ALO"}])
    stored = await race_scoring.fetch_and_store_result(sb, make_race())
    assert stored["dotd"] == "ALO"


@pytest.mark.asyncio
async def test_override_cannot_set_dotd(patched_openf1):
    sb = build_store(results=[{"id": 1, "race_id": 1, "p1": "NOR", "dotd": "ALO"}])
    payload = race_scoring.preserve_fields(sb, 1, {"race_id": 1, "dotd": "VER"})
    assert payload["dotd"] == "ALO"


@pytest.mark.asyncio
async def test_historical_dotd_still_scores(patched_openf1):
    sb = build_store(
        results=[{"id": 1, "race_id": 1, **FULL_RESULT.model_dump(), "dotd": "ALO"}],
        predictions=[{"id": 1, "player_id": "p1", "race_id": 1, "dotd": "ALO"}],
        players=[{"id": "p1"}],
    )
    scores = await race_scoring.score_race(sb, 1, make_race())
    assert scores[0]["dotd_pts"] == 4


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


# ── Singapore 2026 regression, end to end through the sweep ──

@pytest.mark.asyncio
async def test_sweep_scores_a_race_with_an_unclassified_qualifier(monkeypatch):
    """
    The symptom that exposed the bug: a non-integer qualifying position raised
    inside fetch_race_result, so the sweep stored no result at all and the race
    stayed unscored — the podium and everything else lost to one bad field.

    Unlike the other tests here this drives the real OpenF1 mapping; only the
    HTTP layer is faked.
    """
    from app.services import openf1
    from tests import fixtures_singapore_2026 as sing
    from tests.test_openf1 import make_singapore_get

    race = {
        "id": 64, "round": 17, "location": "SIN 🇸🇬", "type": "GP",
        "race_key": "SIN_GP",
        "scheduled_at": iso(NOW - timedelta(hours=6)),
        "openf1_meeting_key": sing.MEETING_KEY,
        "openf1_session_key": sing.RACE_KEY,
    }
    sb = FakeSupabase(
        races=[race],
        players=[{"id": "p1"}, {"id": "p2"}],
        predictions=[
            {"id": 1, "player_id": "p1", "race_id": 64,
             "p1": "VER", "p2": "LEC", "p3": "ANT"},
            {"id": 2, "player_id": "p2", "race_id": 64,
             "p1": "NOR", "pos_gained": "HAD"},
        ],
        results=[],
        scores=[],
    )
    monkeypatch.setattr(openf1, "_get", make_singapore_get())
    monkeypatch.setattr(autoscore, "get_supabase", lambda: sb)
    monkeypatch.setattr(autoscore, "datetime", _FrozenDatetime)

    summary = await autoscore.sweep_once()

    assert summary == {64: "scored 2 players"}

    stored = sb.store["results"][0]
    assert (stored["p1"], stored["p2"], stored["p3"]) == ("VER", "LEC", "ANT")
    assert stored["pole"] == "VER"
    assert stored["last_place"] == "BOT"
    assert stored["pos_gained_winner"] == "HAD"

    # p1 called the podium exactly: 10 + 8 + 6, plus the 5pt bonus
    p1 = next(s for s in sb.store["scores"] if s["player_id"] == "p1")
    assert p1["total"] == 29
    # p2 only got positions gained, which needed the grid to survive the fetch
    p2 = next(s for s in sb.store["scores"] if s["player_id"] == "p2")
    assert p2["gains_pts"] == 6
