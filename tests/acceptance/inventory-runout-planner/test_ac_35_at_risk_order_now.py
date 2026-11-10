from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from runout_toy import of, product, real_data, toy_run


def test_ac_35_at_risk_order_now() -> None:
    """AC-35: order now = run-out within lead months + 1 (T0001, T0002 yes; T0006, T0005 no);
    real data: Baseline order-now count < Supplier delay +3 weeks, and at most 10."""
    result = toy_run(
        product("T0001"),
        product("T0002", lead_time_weeks=10),
        product("T0006", stock_on_hand=300),
        product("T0005", stock_on_hand=1000),
    )
    assert of(result, "T0006").runout_month == "2012-05"
    assert result.kpis.products_at_risk == 2

    data = real_data()
    base = run(data, BASELINE).kpis.products_at_risk
    delay = run(data, PRESETS["Supplier delay +3 weeks"]).kpis.products_at_risk
    assert base < delay
    assert base <= 10
