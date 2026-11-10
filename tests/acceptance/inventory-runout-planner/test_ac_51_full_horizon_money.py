from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import PRESETS
from runout_toy import real_data


def test_ac_51_full_horizon_money() -> None:
    """AC-51: lost sales after plan = with-plan unmet over the whole horizon × sell price; stock-out months count every
    short product-month; Efficiency loses more than Baseline."""
    data = real_data()
    lost = {}
    for name, scenario in PRESETS.items():
        result = run(data, scenario)
        expected = sum(
            sum(r.unmet for r in p.plan_months) * data.prices[p.stock_code]
            for p in result.products
        )
        k = result.kpis.model_dump()
        assert abs(k["lost_sales_after_plan_gbp"] - expected) <= 0.05, name
        assert k["stockout_months"] == sum(
            r.unmet > 0 for p in result.products for r in p.plan_months
        ), name
        lost[name] = k["lost_sales_after_plan_gbp"]
    assert lost["Efficiency"] > lost["Baseline"]
