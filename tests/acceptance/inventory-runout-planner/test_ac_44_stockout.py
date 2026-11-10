from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import of, product, real_data, toy_run


def test_ac_44_stockout() -> None:
    """AC-44: a lead-time-blocked product reports its stock-out window: months, units and lost sales."""
    result = toy_run(product("T0001"), product("T0002", lead_time_weeks=10))
    assert of(result, "T0002").model_dump()["stockout"] == {
        "start_month": "2012-01",
        "end_month": "2012-02",
        "months": 2,
        "units": 80,
        "lost_sales_gbp": 400.00,
    }
    assert of(result, "T0001").model_dump()["stockout"] is None
    real = of(run(real_data(), BASELINE), "84347").model_dump()["stockout"]
    assert (real["start_month"], real["end_month"], real["months"], real["units"]) == (
        "2011-12",
        "2012-02",
        3,
        1006,
    )
