from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from runout_toy import real_data


def test_ac_20_budget_presets() -> None:
    """AC-20: Baseline funds 70-99% of suggested spend; Tight budget = Baseline / 2 and has a budget-limited product."""
    data = real_data()
    base = run(data, BASELINE)
    assert BASELINE.budget_gbp % 1000 == 0
    assert 0.70 <= base.kpis.funded_spend_gbp / base.kpis.suggested_spend_gbp < 1.00
    tight = PRESETS["Tight budget"]
    assert tight.budget_gbp == BASELINE.budget_gbp / 2
    assert any(p.limiting_factor == "budget" for p in run(data, tight).products)
