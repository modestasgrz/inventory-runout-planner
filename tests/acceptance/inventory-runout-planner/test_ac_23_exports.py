from inventory_runout_planner.exports import tables
from inventory_runout_planner.models import Kpis, Product, ReorderLine, Scenario
from inventory_runout_planner.planner import run
from runout_toy import product, scenario, toy_data


def test_ac_23_exports() -> None:
    """AC-23: the 4 export tables have the DEC-13 columns; funded plan cost = 600.00; 36 projection rows; synthetic label."""
    data = toy_data(
        product("T0001"),
        product("T0002", lead_time_weeks=10),
        product("T0003", unit_cost=1.00),
    )
    result = run(data, scenario(budget_gbp=650))
    out = tables(data, result)
    assert list(out) == [
        "products.csv",
        "monthly_projection.csv",
        "scenario.csv",
        "reorder_plan.csv",
    ]
    assert list(out["products.csv"].columns) == [*Product.model_fields, "stock_data"]
    assert set(out["products.csv"]["stock_data"]) == {"synthetic"}
    proj = out["monthly_projection.csv"]
    assert list(proj.columns) == [
        "stock_code",
        "projection",
        "month",
        "demand",
        "opening",
        "inbound",
        "shipped",
        "unmet",
        "closing",
    ]
    assert len(proj) == 36
    assert set(proj["projection"]) == {"do_nothing", "with_plan"}
    sc = out["scenario.csv"]
    assert list(sc.columns) == ["key", "value"]
    assert list(sc["key"]) == ["as_of", *Scenario.model_fields, *Kpis.model_fields]
    assert sc["value"].iloc[0] == "2011-12-01"
    plan = out["reorder_plan.csv"]
    assert list(plan.columns) == list(ReorderLine.model_fields)
    assert round(float(plan.loc[plan["funded"], "cost_gbp"].sum()), 2) == 600.00
