"""
Real OpenF1 data for the 2026 Italian GP at Monza (meeting 1293).

This weekend is the reason positions gained is measured from the starting grid:
the grid differed from qualifying for 15 of 22 drivers. Antonelli qualified P7,
started P19 on a penalty and won — +18 places, the biggest gain in the field —
while measuring from qualifying scores him only +6 and hands the points to
Tsunoda at +7 (whose real gain is +5, since he started P15 not P17).
"""

MEETING_KEY = 1293
QUALI_KEY = 11357
RACE_KEY = 11361

SESSIONS = [
    {"session_key": 11354, "meeting_key": MEETING_KEY, "session_name": "Practice 1",
     "session_type": "Practice", "is_cancelled": False},
    {"session_key": 11355, "meeting_key": MEETING_KEY, "session_name": "Practice 2",
     "session_type": "Practice", "is_cancelled": False},
    {"session_key": 11356, "meeting_key": MEETING_KEY, "session_name": "Practice 3",
     "session_type": "Practice", "is_cancelled": False},
    {"session_key": QUALI_KEY, "meeting_key": MEETING_KEY, "session_name": "Qualifying",
     "session_type": "Qualifying", "is_cancelled": False},
    {"session_key": RACE_KEY, "meeting_key": MEETING_KEY, "session_name": "Race",
     "session_type": "Race", "is_cancelled": False},
]

DRIVERS = {
    1: "NOR", 3: "VER", 5: "BOR", 10: "GAS", 11: "PER", 12: "ANT", 14: "ALO",
    16: "LEC", 18: "STR", 22: "TSU", 23: "ALB", 27: "HUL", 30: "LAW", 31: "OCO",
    41: "LIN", 43: "COL", 44: "HAM", 55: "SAI", 63: "RUS", 77: "BOT", 81: "PIA",
    87: "BEA",
}

DRIVER_ROWS = [
    {"driver_number": n, "name_acronym": a, "team_name": ""} for n, a in DRIVERS.items()
]

# Qualifying classification — what the old code wrongly used as the grid.
QUALI_ORDER = [10, 63, 81, 16, 44, 3, 12, 43, 1, 41, 5, 87, 27, 30, 55, 31, 22, 23, 77, 11, 14, 18]

# The actual starting grid. Note ANT 7 -> 19 and LAW 14 -> 22.
GRID_ORDER = [10, 63, 16, 44, 3, 81, 43, 1, 41, 5, 87, 27, 55, 31, 22, 77, 11, 18, 12, 23, 14, 30]

# Classified finishers, in order. LEC, ALO and STR retired.
RACE_ORDER = [12, 63, 3, 1, 81, 44, 10, 41, 43, 22, 5, 27, 55, 30, 87, 31, 23, 11, 77]
RETIRED = {18: 26, 14: 23, 16: 1}   # driver_number -> laps completed


def _result_rows(order: list[int], retired: dict[int, int] | None = None) -> list[dict]:
    rows = [
        {"position": i + 1, "driver_number": dn, "dnf": False, "dns": False, "dsq": False}
        for i, dn in enumerate(order)
    ]
    for dn, laps in (retired or {}).items():
        rows.append({"position": None, "driver_number": dn, "dnf": True,
                     "dns": False, "dsq": False, "number_of_laps": laps})
    return rows


QUALI_RESULT = _result_rows(QUALI_ORDER)
RACE_RESULT = _result_rows(RACE_ORDER, RETIRED)

# starting_grid rows carry the QUALIFYING session_key, not the race's.
STARTING_GRID = [
    {"position": i + 1, "driver_number": dn, "meeting_key": MEETING_KEY,
     "session_key": QUALI_KEY, "lap_duration": None}
    for i, dn in enumerate(GRID_ORDER)
]
