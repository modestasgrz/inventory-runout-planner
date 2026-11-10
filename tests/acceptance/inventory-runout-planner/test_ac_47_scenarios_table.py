from inventory_runout_planner.fmt import month
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import PRESETS
from runout_toy import app, real_data

COLUMNS = [
    "Preset",
    "Products at risk",
    "Unfunded orders",
    "Unfunded £",
    "Lost sales £",
    "Stock-out months",
    "Earliest run-out",
]


def test_ac_47_scenarios_table() -> None:
    """AC-47: Scenarios compares the presets on risk, unfunded orders and £, lost sales £, stock-out months and
    earliest run-out as '<Mon YYYY> · <code>'."""
    data = real_data()
    at = app().run()
    at.switch_page("app_pages/scenarios.py").run()
    assert not at.exception
    table = next(d.value for d in at.dataframe if list(d.value.columns) == COLUMNS)
    assert list(table["Preset"]) == list(PRESETS)
    for (name, preset), (_, row) in zip(PRESETS.items(), table.iterrows(), strict=True):
        k = run(data, preset).kpis.model_dump()
        assert int(row["Products at risk"]) == k["products_at_risk"], name
        assert int(row["Unfunded orders"]) == k["unfunded_orders"], name
        assert abs(float(row["Unfunded £"]) - k["unfunded_gbp"]) <= 1, name
        assert abs(float(row["Lost sales £"]) - k["lost_sales_after_plan_gbp"]) <= 1, (
            name
        )
        assert int(row["Stock-out months"]) == k["stockout_months"], name
        assert row["Earliest run-out"] == (
            f"{month(k['earliest_runout_month'])} · {k['earliest_runout_code']}"
        ), name
