import pytest
from app.models import PredictionBase, ResultBase
from app.services.scoring import calculate_score


def make_result(**kwargs) -> ResultBase:
    defaults = dict(
        pole="RUS", p1="RUS", p2="ANT", p3="LEC",
        last_place="STR", fastest_lap="VER", fastest_pitstop="MCL",
        dotd="BOT", safety_car=True, pos_gained_winner="HAM",
    )
    return ResultBase(**{**defaults, **kwargs})


def make_pred(**kwargs) -> PredictionBase:
    defaults = dict(
        pole="RUS", p1="RUS", p2="ANT", p3="LEC",
        last_place="STR", fastest_lap="VER", fastest_pitstop="MCL",
        dotd="BOT", safety_car=True, pos_gained="HAM",
    )
    return PredictionBase(**{**defaults, **kwargs})


class TestExactScores:
    def test_perfect_prediction(self):
        s = calculate_score(make_pred(), make_result())
        assert s.pole_pts   == 10
        assert s.p1_pts     == 10
        assert s.p2_pts     == 8
        assert s.p3_pts     == 6
        assert s.podium_bonus == 5
        assert s.podium_pts == 0   # no partial when exact
        assert s.last_pts   == 5
        assert s.fl_pts     == 5
        assert s.fp_pts     == 5
        assert s.dotd_pts   == 5
        assert s.sc_pts     == 5
        assert s.gains_pts  == 5
        assert s.total      == 69

    def test_no_prediction_scores_zero(self):
        s = calculate_score(make_pred(p1="VER", p2="VER", p3="VER"), make_result())
        assert s.p1_pts == 0
        assert s.p2_pts == 0
        assert s.p3_pts == 0


class TestPodiumPartial:
    def test_two_correct_wrong_position(self):
        # Actual: RUS, ANT, LEC — Predicted: ANT, RUS, LEC
        pred = make_pred(p1="ANT", p2="RUS", p3="LEC")
        s = calculate_score(pred, make_result())
        # p3 is correct (LEC=6pts), p1 and p2 are wrong slot but on podium
        assert s.p3_pts     == 6
        assert s.p1_pts     == 0
        assert s.p2_pts     == 0
        assert s.podium_pts == 8   # 2 drivers × 4pts
        assert s.podium_bonus == 0  # not exact

    def test_example_from_spec(self):
        # Actual: RUS, ANT, LEC — Predicted: ANT, RUS, LEC → 8pts
        pred = make_pred(p1="ANT", p2="RUS", p3="LEC")
        s = calculate_score(pred, make_result())
        assert s.podium_pts == 8

    def test_no_partial_when_exact(self):
        pred = make_pred(p1="RUS", p2="ANT", p3="LEC")
        s = calculate_score(pred, make_result())
        assert s.podium_pts == 0
        assert s.p1_pts == 10

    def test_driver_not_on_podium_scores_nothing(self):
        pred = make_pred(p1="VER", p2="ANT", p3="LEC")
        s = calculate_score(pred, make_result())
        assert s.p1_pts == 0
        assert s.podium_pts == 4  # only ANT and LEC on podium (ANT wrong slot)


class TestPodiumBonus:
    def test_bonus_only_when_all_three_exact(self):
        s = calculate_score(make_pred(), make_result())
        assert s.podium_bonus == 5

    def test_no_bonus_when_wrong_order(self):
        pred = make_pred(p1="ANT", p2="RUS", p3="LEC")
        s = calculate_score(pred, make_result())
        assert s.podium_bonus == 0


class TestMiscScoring:
    def test_safety_car_correct(self):
        s = calculate_score(make_pred(safety_car=True), make_result(safety_car=True))
        assert s.sc_pts == 5

    def test_safety_car_wrong(self):
        s = calculate_score(make_pred(safety_car=False), make_result(safety_car=True))
        assert s.sc_pts == 0

    def test_no_result_returns_zero(self):
        result = ResultBase()
        s = calculate_score(make_pred(), result)
        assert s.total == 0
