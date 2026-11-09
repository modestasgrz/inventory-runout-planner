from inventory_runout_planner.models import Scenario
from inventory_runout_planner.planner import run
from runout_toy import product, scenario, toy_data


def test_ac_36_no_demand_flag() -> None:
    """AC-36: stock 100 with zero forecast demand -> no run-out, no order, flags == ['Overstocked: no forecast demand']."""
    toy = product("T0007")
    plan_scenario: Scenario = scenario()
    p = run(toy_data(toy, history={"T0007": [0] * 24}), plan_scenario).products[0]
    assert p.runout_month is None
    assert p.order is None
    assert p.flags == ["Overstocked: no forecast demand"]
