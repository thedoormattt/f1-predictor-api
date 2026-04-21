"""
Scoring engine — mirrors the Race Predictions spreadsheet logic exactly.

Points structure:
  Pole position:        5 pts (exact match)
  P1:                  10 pts (exact match)
  P2:                   8 pts (exact match)
  P3:                   6 pts (exact match)
  Podium bonus:         5 pts (all three correct, any order)
  Podium wrong slot:    4 pts per driver (on podium but wrong position)
  Last place:           5 pts
  Fastest lap:          4 pts
  Fastest pitstop:      4 pts
  Driver of the Day:    4 pts
  Safety car correct:   4 pts
  Pos gained winner:    6 pts
"""

from app.models import PredictionBase, ResultBase, ScoreBreakdown


def calculate_score(pred: PredictionBase, result: ResultBase) -> ScoreBreakdown:
    s = ScoreBreakdown()

    if not _has_result(result):
        return s

    # ── Pole ─────────────────────────────────────────────────
    if pred.pole and pred.pole == result.pole:
        s.pole_pts = 5

    # ── Podium exact positions ────────────────────────────────
    if pred.p1 and pred.p1 == result.p1:
        s.p1_pts = 10
    if pred.p2 and pred.p2 == result.p2:
        s.p2_pts = 8
    if pred.p3 and pred.p3 == result.p3:
        s.p3_pts = 6

    # ── Podium bonus (exact podium in any order = 5 extra) ───
    actual_podium = {result.p1, result.p2, result.p3} - {None}
    pred_podium   = {pred.p1,   pred.p2,   pred.p3}   - {None}
    if len(actual_podium) == 3 and actual_podium == pred_podium:
        if s.p1_pts + s.p2_pts + s.p3_pts == 24:
            s.podium_bonus = 5

    # ── Podium partial (right driver, wrong slot) — 4 pts each ─
    # Only awarded when the player did NOT score full points for that position
    podium_partial = 0
    if pred.p1 and s.p1_pts == 0 and pred.p1 in actual_podium:
        podium_partial += 4
    if pred.p2 and s.p2_pts == 0 and pred.p2 in actual_podium:
        podium_partial += 4
    if pred.p3 and s.p3_pts == 0 and pred.p3 in actual_podium:
        podium_partial += 4
    s.podium_pts = podium_partial

    # ── Last place ───────────────────────────────────────────
    if pred.last_place and pred.last_place == result.last_place:
        s.last_pts = 5

    # ── Fastest lap ──────────────────────────────────────────
    if pred.fastest_lap and pred.fastest_lap == result.fastest_lap:
        s.fl_pts = 4

    # ── Fastest pitstop ──────────────────────────────────────
    if pred.fastest_pitstop and pred.fastest_pitstop == result.fastest_pitstop:
        s.fp_pts = 4

    # ── Driver of the Day ────────────────────────────────────
    if pred.dotd and pred.dotd == result.dotd:
        s.dotd_pts = 4

    # ── Safety car ───────────────────────────────────────────
    if pred.safety_car is not None and pred.safety_car == result.safety_car:
        s.sc_pts = 4

    # ── Position gained ──────────────────────────────────────
    if pred.pos_gained and pred.pos_gained == result.pos_gained_winner:
        s.gains_pts = 6

    # ── Total ────────────────────────────────────────────────
    s.total = (
        s.pole_pts + s.p1_pts + s.p2_pts + s.p3_pts
        + s.podium_bonus + s.podium_pts
        + s.last_pts + s.fl_pts + s.fp_pts
        + s.dotd_pts + s.sc_pts + s.gains_pts
    )

    return s


def _has_result(result: ResultBase) -> bool:
    """Return True if the result has at minimum the podium filled in."""
    return bool(result.p1 and result.p2 and result.p3)
