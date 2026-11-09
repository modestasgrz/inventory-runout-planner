from inventory_runout_planner.planner import forecast

HISTORY = [0] * 12 + [10 * i for i in range(1, 13)]


def test_ac_06_trailing_3m() -> None:
    """AC-06: trailing 3-month mean (100, 110, 120 = 110) x 1.25 = 137.5 -> 138 in every month."""
    assert forecast(HISTORY, "trailing_3m", 25, 12) == [138] * 12
