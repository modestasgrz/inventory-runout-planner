from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from runout_toy import of, product, real_data, toy_run

TOYS = (
    product("T0001"),
    product("T0002", lead_time_weeks=10),
    product("T0006", stock_on_hand=300),
    product("T0005", stock_on_hand=1000),
)


def test_ac_45_at_risk_after_plan() -> None:
    """AC-45: products at risk = products still losing sales after the plan; it moves with the budget."""
    result = toy_run(*TOYS, budget_gbp=1000)
    t6 = of(result, "T0006").order
    assert t6 is not None and t6.cost_gbp == 360.00 and not t6.funded
    at_risk = [
        p.stock_code for p in result.products if p.model_dump()["at_risk_after_plan"]
    ]
    assert sorted(at_risk) == ["T0002", "T0006"]
    k = result.kpis.model_dump()
    assert k["products_at_risk"] == 2
    assert k["stockout_months"] == 3
    assert k["unfunded_gbp"] == 360.00
    rich = toy_run(*TOYS, budget_gbp=2000)
    t6 = of(rich, "T0006").order
    assert t6 is not None and t6.funded
    assert rich.kpis.products_at_risk == 1

    data = real_data()
    for name, scenario in PRESETS.items():
        r = run(data, scenario)
        assert r.kpis.products_at_risk == sum(
            p.model_dump()["at_risk_after_plan"] for p in r.products
        ), name
    tight = run(data, PRESETS["Tight budget"]).kpis.products_at_risk
    assert tight > run(data, BASELINE).kpis.products_at_risk
