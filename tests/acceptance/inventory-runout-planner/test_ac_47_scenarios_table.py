from inventory_runout_planner.fmt import month
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from runout_toy import app, real_data, texts

COLUMNS = [
    "Preset",
    "Products at risk",
    "Lost sales £",
    "vs Baseline £",
    "Unfunded orders",
    "Unfunded £",
    "Earliest run-out",
]


def test_ac_47_scenarios_table() -> None:
    """AC-47: Scenarios compares the presets on full-horizon lost sales, the change vs Baseline, risk and unfunded
    orders; no input chips repeating the sidebar."""
    data = real_data()
    base = run(data, BASELINE).kpis.model_dump()["lost_sales_after_plan_gbp"]
    at = app().run()
    at.switch_page("app_pages/scenarios.py").run()
    assert not at.exception
    table = next(d.value for d in at.dataframe if list(d.value.columns) == COLUMNS)
    assert list(table["Preset"]) == list(PRESETS)
    for (name, preset), (_, row) in zip(PRESETS.items(), table.iterrows(), strict=True):
        k = run(data, preset).kpis.model_dump()
        lost = k["lost_sales_after_plan_gbp"]
        assert int(row["Products at risk"]) == k["products_at_risk"], name
        assert abs(float(row["Lost sales £"]) - lost) <= 1, name
        assert abs(float(row["vs Baseline £"]) - (lost - base)) <= 1, name
        assert int(row["Unfunded orders"]) == k["unfunded_orders"], name
        assert abs(float(row["Unfunded £"]) - k["unfunded_gbp"]) <= 1, name
        assert row["Earliest run-out"] == (
            f"{month(k['earliest_runout_month'])} · {k['earliest_runout_code']}"
        ), name
    assert "Current assumptions" not in texts(at.main)
