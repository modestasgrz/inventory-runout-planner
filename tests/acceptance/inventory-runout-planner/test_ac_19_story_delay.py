from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import PRESETS
from runout_toy import of, real_data


def test_ac_19_story_delay() -> None:
    """AC-19: Supplier delay +3 weeks: 85099B inbound arrives Feb 2012 and it runs out Jan 2012."""
    bag = of(run(real_data(), PRESETS["Supplier delay +3 weeks"]), "85099B")
    assert bag.inbound_month == "2012-02"
    assert bag.runout_month == "2012-01"
