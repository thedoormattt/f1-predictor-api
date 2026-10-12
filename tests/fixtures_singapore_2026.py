"""
Real OpenF1 data for the 2026 Singapore GP (meeting 1296) — a sprint weekend.

This weekend is the reason positions are coerced rather than trusted. Hadjar
(driver 6) set no qualifying time and his qualifying result came back as
`"position": "RT"` — a string, with dnf/dns/dsq all false — while the other 21
drivers were integers. Passed through untouched that string reaches a
comparison in _get_pole_position and raises TypeError, which took down the
entire result fetch and left the race unscored.

He then started P22 and finished P10, making him the biggest gainer of the race
at +12, so the same driver exercises both the crash and the grid logic.
"""

MEETING_KEY = 1296
SPRINT_QUALI_KEY = 11379
SPRINT_KEY = 11383
QUALI_KEY = 11384
RACE_KEY = 11388

DRIVERS = {
    1: "NOR", 3: "VER", 5: "BOR", 6: "HAD", 10: "GAS", 11: "PER", 12: "ANT",
    14: "ALO", 16: "LEC", 18: "STR", 23: "ALB", 27: "HUL", 30: "LAW", 31: "OCO",
    41: "LIN", 43: "COL", 44: "HAM", 55: "SAI", 63: "RUS", 77: "BOT", 81: "PIA",
    87: "BEA",
}

DRIVER_ROWS = [
    {"driver_number": n, "name_acronym": a, "team_name": ""} for n, a in DRIVERS.items()
]

SESSIONS = [
    {"session_key": SPRINT_QUALI_KEY, "meeting_key": MEETING_KEY,
     "session_name": "Sprint Qualifying", "session_type": "Qualifying", "is_cancelled": False},
    {"session_key": SPRINT_KEY, "meeting_key": MEETING_KEY,
     "session_name": "Sprint", "session_type": "Race", "is_cancelled": False},
    {"session_key": QUALI_KEY, "meeting_key": MEETING_KEY,
     "session_name": "Qualifying", "session_type": "Qualifying", "is_cancelled": False},
    {"session_key": RACE_KEY, "meeting_key": MEETING_KEY,
     "session_name": "Race", "session_type": "Race", "is_cancelled": False},
]

# Qualifying — driver 6 is the "RT" row that caused the crash.
QUALI_RESULT = [
    {"position": p, "driver_number": d, "dnf": False, "dns": False, "dsq": False}
    for p, d in enumerate(
        [3, 16, 44, 12, 1, 63, 81, 10, 30, 41, 27, 87, 31, 55, 5, 43, 14, 23, 18, 11, 77],
        start=1,
    )
] + [{"position": "RT", "driver_number": 6, "dnf": False, "dns": False, "dsq": False}]

RACE_ORDER = [3, 16, 12, 1, 81, 44, 30, 27, 63, 6, 10, 87, 31, 55, 41, 14, 11, 23, 77]
RACE_RETIRED = {18: 36, 43: 29, 5: 7}

RACE_RESULT = [
    {"position": i + 1, "driver_number": d, "dnf": d == 23, "dns": False, "dsq": False}
    for i, d in enumerate(RACE_ORDER)
] + [
    {"position": None, "driver_number": d, "dnf": True, "dns": False,
     "dsq": False, "number_of_laps": laps}
    for d, laps in RACE_RETIRED.items()
]

# Two grids come back for one meeting_key on a sprint weekend.
GP_GRID_ORDER = [3, 16, 44, 12, 1, 81, 10, 30, 41, 27, 87, 31, 55, 5, 43, 23, 11, 77, 63, 14, 18, 6]
SPRINT_GRID_ORDER = [3, 63, 16, 81, 1, 44, 12, 30, 6, 10, 43, 27, 87, 5, 14, 31, 41, 18, 23, 11, 77, 55]

STARTING_GRID = [
    {"position": i + 1, "driver_number": d, "meeting_key": MEETING_KEY,
     "session_key": SPRINT_QUALI_KEY, "lap_duration": None}
    for i, d in enumerate(SPRINT_GRID_ORDER)
] + [
    {"position": i + 1, "driver_number": d, "meeting_key": MEETING_KEY,
     "session_key": QUALI_KEY, "lap_duration": None}
    for i, d in enumerate(GP_GRID_ORDER)
]

# ── Sprint ───────────────────────────────────────────────
# Sprint qualifying was all integers, and the sprint grid matched it exactly
# (no penalties), so the sprint exercises the happy path through a different
# pair of sessions. The sprint itself was carnage: 14 classified, 8 retired,
# and Piastri classified P14 on a DNF after 19 of 20 laps.

SPRINT_QUALI_ORDER = SPRINT_GRID_ORDER
SPRINT_QUALI_RESULT = [
    {"position": i + 1, "driver_number": d,
     "dnf": d in (6, 10), "dns": False, "dsq": False}
    for i, d in enumerate(SPRINT_QUALI_ORDER)
]

SPRINT_ORDER = [3, 44, 16, 12, 30, 87, 27, 1, 10, 31, 14, 55, 41, 81]
SPRINT_RETIRED = {23: 14, 5: 6, 77: 6, 6: 2, 43: 2, 63: 1, 11: 1, 18: 0}

SPRINT_RESULT = [
    {"position": i + 1, "driver_number": d, "dnf": d == 81,
     "dns": False, "dsq": False}
    for i, d in enumerate(SPRINT_ORDER)
] + [
    {"position": None, "driver_number": d, "dnf": True, "dns": False,
     "dsq": False, "number_of_laps": laps}
    for d, laps in SPRINT_RETIRED.items()
]
