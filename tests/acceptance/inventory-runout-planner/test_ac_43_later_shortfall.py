from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import of, product, real_data, toy_run


def test_ac_43_later_shortfall() -> None:
    """AC-43: unmet demand left after the funded order(s), outside the stock-out window, is flagged 'Short after plan'
    and counts in lost sales after plan."""
    p = of(toy_run(product("T0001")), "T0001")
    d = p.model_dump()
    assert d["later_shortfall_units"] == 60
    assert d["later_shortfall_month"] == "2012-05"
    assert d["later_shortfall_gbp"] == 300.00
    assert "Short after plan: 60 units from May 2012" in p.flags
    assert d["lost_sales_after_plan_gbp"] == 300.00
    real = of(run(real_data(), BASELINE), "84347")
    assert "Short after plan: 2 948 units from Nov 2012" in real.flags
