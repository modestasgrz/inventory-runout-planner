from inventory_runout_planner.models import scenario_errors

VALID: dict[str, float | int | str] = {
    "horizon_months": 12,
    "growth_pct": 0,
    "delay_weeks": 0,
    "budget_gbp": 50000,
    "safety_months": 1.0,
    "method": "seasonal_naive",
}


def test_ac_37_entered_value_format() -> None:
    """AC-37: entered values print as typed: whole numbers with U+202F thousands, raw text, fractions with :g."""
    assert scenario_errors(VALID | {"budget_gbp": 2000000}) == [
        "Purchase budget (£, whole horizon) must be between 0 and 1 000 000 — you entered 2 000 000."
    ]
    assert scenario_errors(VALID | {"growth_pct": "abc"}) == [
        "Demand growth (%) must be between -50 and 100 — you entered abc."
    ]
    assert scenario_errors(VALID | {"delay_weeks": 1.5}) == [
        "Supplier delay (weeks) must be between 0 and 26 — you entered 1.5."
    ]
