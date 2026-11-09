from inventory_runout_planner.models import scenario_errors

VALID = {
    "horizon_months": 12,
    "growth_pct": 0,
    "delay_weeks": 0,
    "budget_gbp": 50000,
    "safety_months": 1.0,
    "method": "seasonal_naive",
}


def test_ac_21_validation() -> None:
    """AC-21: out-of-range inputs give the 4 DEC-10 messages in order; valid inputs give none."""
    bad = VALID | {
        "growth_pct": 150,
        "delay_weeks": 30,
        "budget_gbp": -100,
        "safety_months": -1,
    }
    assert scenario_errors(bad) == [
        "Demand growth (%) must be between -50 and 100 — you entered 150.",
        "Supplier delay (weeks) must be between 0 and 26 — you entered 30.",
        "Budget (£) must be between 0 and 1 000 000 — you entered -100.",
        "Safety stock (months) must be between 0 and 6 — you entered -1.",
    ]
    assert scenario_errors(VALID) == []
