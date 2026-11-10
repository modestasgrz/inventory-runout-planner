from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from runout_toy import of, real_data


def test_ac_50_real_orders() -> None:
    """AC-50: £350k / £175k budgets; up to 4 orders per product, numbered and arriving in sequence; the plan lists
    them all; 84347's second order (Aug 2012) is funded under Baseline."""
    assert BASELINE.budget_gbp == 350_000
    assert PRESETS["Tight budget"].budget_gbp == 175_000
    data = real_data()
    for name, scenario in PRESETS.items():
        result = run(data, scenario)
        total = 0
        for p in result.products:
            orders = p.model_dump()["orders"]
            assert len(orders) <= 4, (name, p.stock_code)
            assert [o["order_no"] for o in orders] == list(range(1, len(orders) + 1))
            arrivals = [o["arrival_month"] for o in orders]
            assert arrivals == sorted(set(arrivals)), (name, p.stock_code)
            total += len(orders)
        assert len(result.plan) == total, name
        assert [line.rank for line in result.plan] == list(range(1, total + 1)), name
    orders = of(run(data, BASELINE), "84347").model_dump()["orders"]
    assert orders[1]["arrival_month"] == "2012-08"
    assert orders[1]["funded"] is True
