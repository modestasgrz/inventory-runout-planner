from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import of, product, real_data, toy_run


def test_ac_43_later_shortfall() -> None:
    """AC-43: unmet demand after the funded order's 3-month cover is flagged as a later shortfall, not lost after plan."""
    p = of(toy_run(product("T0001")), "T0001")
    d = p.model_dump()
    assert d["later_shortfall_units"] == 60
    assert d["later_shortfall_month"] == "2012-05"
    assert d["later_shortfall_gbp"] == 300.00
    assert "Later shortfall not covered: 60 units from May 2012" in p.flags
    assert d["lost_sales_after_plan_gbp"] == 0.00
    real = of(run(real_data(), BASELINE), "84347")
    assert "Later shortfall not covered: 5 759 units from Sep 2012" in real.flags
