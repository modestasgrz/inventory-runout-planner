from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import of, real_data


def test_ac_17_story_runouts() -> None:
    """AC-17: Baseline earliest run-out = 84347, Dec 2011, lead time; 85123A runs out Jan 2012, stock, order now."""
    result = run(real_data(), BASELINE)
    assert result.kpis.earliest_runout_code == "84347"
    assert result.kpis.earliest_runout_month == "2011-12"
    assert result.kpis.earliest_limiting_factor == "lead time"
    p = of(result, "85123A")
    assert p.runout_month == "2012-01"
    assert p.limiting_factor == "stock"
    assert p.order is not None
    assert p.order.order_month == "2011-12"
