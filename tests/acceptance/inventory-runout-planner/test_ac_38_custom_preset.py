from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import ScenarioResult
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from runout_toy import app, kpis, real_data


def expected(result: ScenarioResult) -> dict[str, str]:
    """The KPI values (DEC-14, Change 4: the same 5 cards on every page)."""
    k = result.kpis.model_dump()
    return {
        "At risk": number(k["products_at_risk"]),
        "Earliest run-out": month(k["earliest_runout_month"])
        if k["earliest_runout_month"]
        else "None in horizon",
        "Spend": gbp(k["funded_spend_gbp"]),
        "Unfunded": number(k["unfunded_orders"]),
        "Lost sales": gbp(k["lost_sales_after_plan_gbp"]),
    }


def test_ac_38_custom_preset() -> None:
    """AC-38: editing an input switches the preset to Custom; re-selecting the same preset reloads it;
    selecting Baseline after an invalid input clears the error."""
    data = real_data()
    peak = PRESETS["Peak season +25%"]
    at = app().run()
    at.selectbox(key="preset").select("Peak season +25%").run()
    at.number_input(key="growth_pct").set_value(10).run()
    assert at.selectbox(key="preset").value == "Custom"
    assert kpis(at) == expected(run(data, peak.model_copy(update={"growth_pct": 10.0})))

    at.selectbox(key="preset").select("Peak season +25%").run()
    assert at.number_input(key="growth_pct").value == 25
    assert kpis(at) == expected(run(data, peak))

    at = app().run()
    at.number_input(key="growth_pct").set_value(150).run()
    assert len(at.error) == 1
    at.selectbox(key="preset").select("Baseline").run()
    assert not at.exception
    assert len(at.error) == 0
    assert kpis(at) == expected(run(data, BASELINE))
