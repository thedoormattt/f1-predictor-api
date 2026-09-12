"""
OpenF1 mapping tests, driven by real Monza 2026 data.

The whole point of these is the grid: measuring positions gained from qualifying
order rather than the starting grid gets the wrong driver whenever someone
recovers from a penalty.
"""

import pytest

from app.services import openf1
from tests import fixtures_monza_2026 as monza


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def make_fake_get(*, starting_grid=..., session_result=..., overrides=None):
    """Route OpenF1 calls to the Monza fixtures. Pass None to make an endpoint empty."""
    grid = monza.STARTING_GRID if starting_grid is ... else starting_grid
    results = {} if session_result is None else {
        monza.QUALI_KEY: monza.QUALI_RESULT,
        monza.RACE_KEY: monza.RACE_RESULT,
    }
    calls = []

    async def fake_get(client, url, params={}):
        path = url.rsplit("/", 1)[-1]
        calls.append((path, dict(params)))
        if overrides and path in overrides:
            return FakeResponse(overrides[path])
        if path == "sessions":
            return FakeResponse(monza.SESSIONS)
        if path == "drivers":
            return FakeResponse(monza.DRIVER_ROWS)
        if path == "starting_grid":
            return FakeResponse(grid or [])
        if path == "session_result":
            return FakeResponse(results.get(params.get("session_key"), []))
        if path == "position":
            return FakeResponse([])
        if path == "race_control":
            return FakeResponse([{"category": "Flag", "flag": "GREEN"}])
        return FakeResponse([])

    fake_get.calls = calls
    return fake_get


@pytest.fixture
def patched(monkeypatch):
    def _apply(fake_get):
        monkeypatch.setattr(openf1, "_get", fake_get)
        return fake_get
    return _apply


# ── the bug this fix exists for ──────────────────────────────

@pytest.mark.asyncio
async def test_positions_gained_uses_the_starting_grid(patched):
    patched(make_fake_get())
    finish = {dn: i + 1 for i, dn in enumerate(monza.RACE_ORDER)}

    winner = await openf1._get_most_positions_gained(
        None, monza.MEETING_KEY, monza.QUALI_KEY, finish, monza.DRIVERS
    )

    # ANT: grid P19 -> P1 = +18. From qualifying (P7) it would read +6 and lose
    # to TSU's apparent +7.
    assert winner == "ANT"


@pytest.mark.asyncio
async def test_qualifying_order_would_have_picked_the_wrong_driver(patched):
    """Guards the regression directly: no starting grid means the old answer."""
    patched(make_fake_get(starting_grid=None))
    finish = {dn: i + 1 for i, dn in enumerate(monza.RACE_ORDER)}

    winner = await openf1._get_most_positions_gained(
        None, monza.MEETING_KEY, monza.QUALI_KEY, finish, monza.DRIVERS
    )

    assert winner == "TSU"   # the documented fallback, and why we avoid it


@pytest.mark.asyncio
async def test_retirements_cannot_win_positions_gained(patched):
    patched(make_fake_get())
    finish = {dn: i + 1 for i, dn in enumerate(monza.RACE_ORDER)}

    # LEC started P3 and retired on lap 1 — absent from the classification.
    assert 16 not in finish


@pytest.mark.asyncio
async def test_grid_is_filtered_to_the_right_qualifying_session(patched):
    """A sprint weekend returns two grids from one meeting_key."""
    sprint_grid = [
        {"position": 1, "driver_number": 55, "session_key": 99999,
         "meeting_key": monza.MEETING_KEY},
    ]
    patched(make_fake_get(starting_grid=sprint_grid + monza.STARTING_GRID))

    grid = await openf1._get_starting_grid(None, monza.MEETING_KEY, monza.QUALI_KEY)

    assert grid[12] == 19          # ANT from the correct grid
    assert 55 not in grid or grid[55] == 13   # SAI's real grid slot, not the sprint row


# ── session resolution ───────────────────────────────────────

class TestQualifyingSessionResolution:
    def test_picks_qualifying_for_a_grand_prix(self):
        assert openf1._resolve_qualifying_session(monza.SESSIONS, monza.RACE_KEY) == monza.QUALI_KEY

    def test_picks_sprint_qualifying_for_a_sprint(self):
        sessions = monza.SESSIONS + [
            {"session_key": 500, "session_name": "Sprint Qualifying",
             "session_type": "Qualifying", "is_cancelled": False},
            {"session_key": 501, "session_name": "Sprint", "session_type": "Race",
             "is_cancelled": False},
        ]
        assert openf1._resolve_qualifying_session(sessions, 501) == 500

    def test_grand_prix_on_a_sprint_weekend_still_uses_qualifying(self):
        sessions = monza.SESSIONS + [
            {"session_key": 500, "session_name": "Sprint Qualifying",
             "session_type": "Qualifying", "is_cancelled": False},
        ]
        assert openf1._resolve_qualifying_session(sessions, monza.RACE_KEY) == monza.QUALI_KEY

    def test_skips_a_cancelled_session(self):
        sessions = [
            {"session_key": 1, "session_name": "Qualifying",
             "session_type": "Qualifying", "is_cancelled": True},
            {"session_key": 2, "session_name": "Sprint Qualifying",
             "session_type": "Qualifying", "is_cancelled": False},
        ]
        assert openf1._resolve_qualifying_session(sessions, 99) == 2

    def test_no_sessions(self):
        assert openf1._resolve_qualifying_session([], 1) is None


# ── classification handling ──────────────────────────────────

class TestClassification:
    def test_retirements_are_excluded(self):
        classified = openf1._classified(monza.RACE_RESULT)
        assert len(classified) == 19
        for dn in monza.RETIRED:
            assert dn not in classified

    def test_dsq_and_dns_are_excluded(self):
        rows = [
            {"position": 1, "driver_number": 1, "dns": False, "dsq": False},
            {"position": 2, "driver_number": 2, "dns": False, "dsq": True},
            {"position": 3, "driver_number": 3, "dns": True, "dsq": False},
        ]
        assert openf1._classified(rows) == {1: 1}


# ── full mapping ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_race_result_maps_monza(patched, monkeypatch):
    patched(make_fake_get(overrides={
        "laps": [{"driver_number": 63, "lap_duration": 79.1, "is_pit_out_lap": False}],
        "pit":  [{"driver_number": 12, "pit_duration": 21.4}],
        "race_control": [{"category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"}],
    }))

    result = await openf1.fetch_race_result(monza.MEETING_KEY, monza.RACE_KEY)

    assert result.p1 == "ANT"
    assert result.p2 == "RUS"
    assert result.p3 == "VER"
    assert result.last_place == "BOT"          # last classified finisher
    assert result.pole == "GAS"                # qualifying P1, despite the grid
    assert result.pos_gained_winner == "ANT"
    assert result.fastest_lap == "RUS"
    assert result.safety_car is True
    assert result.dotd is None                 # retired, never written
