from inventory_runout_planner.planner import forecast

HISTORY = [0] * 12 + [10 * i for i in range(1, 13)]


def test_ac_05_seasonal_naive() -> None:
    """AC-05: seasonal naive with +25% growth: Dec 2011 = 13 (12.5 half up), Jan 2012 = 25, Feb 2012 = 38, month 13 = 13."""
    values = forecast(HISTORY, "seasonal_naive", 25, 13)
    assert len(values) == 13
    assert values[0] == 13
    assert values[1] == 25
    assert values[2] == 38
    assert values[12] == 13
