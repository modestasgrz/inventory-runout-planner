from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import of, real_data


def test_ac_18_story_others() -> None:
    """AC-18: Baseline: 47566 overstocked with no order; 21212 fine; 85099B inbound Jan 2012, no run-out before May 2012."""
    result = run(real_data(), BASELINE)
    bunting = of(result, "47566")
    assert bunting.order is None
    assert any(f.startswith("Overstocked") for f in bunting.flags)
    cases = of(result, "21212")
    assert cases.runout_month is None
    assert cases.limiting_factor == "none"
    bag = of(result, "85099B")
    assert bag.inbound_month == "2012-01"
    assert bag.runout_month is None or bag.runout_month > "2012-04"
