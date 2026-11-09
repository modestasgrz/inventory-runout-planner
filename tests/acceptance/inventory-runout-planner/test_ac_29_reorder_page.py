from inventory_runout_planner.fmt import gbp
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import app, kpis, real_data, texts

COLUMNS = [
    "Rank",
    "Product",
    "Code",
    "Order month",
    "Arrives",
    "Qty",
    "Cost",
    "Funded",
    "Limiting factor",
    "Reason",
]
FILES = ["products.csv", "monthly_projection.csv", "scenario.csv", "reorder_plan.csv"]


def test_ac_29_reorder_page() -> None:
    """AC-29: Reorder plan lists every order in rank order with the DEC-15 columns, 4 labelled downloads,
    and 'Funded total: £X' matching the Purchase spend KPI."""
    result = run(real_data(), BASELINE)
    at = app().run()
    at.switch_page("app_pages/reorder_plan.py").run()
    assert not at.exception
    plan = next(d.value for d in at.dataframe if list(d.value.columns) == COLUMNS)
    assert list(plan["Rank"]) == [line.rank for line in result.plan]
    assert list(plan["Code"].astype(str)) == [line.stock_code for line in result.plan]
    labels = sorted(str(b.proto.label) for b in at.get("download_button"))
    assert labels == sorted(f"Download {f}" for f in FILES)
    funded = gbp(result.kpis.funded_spend_gbp)
    assert f"Funded total: {funded}" in texts(at.main)
    assert kpis(at)["Purchase spend"].startswith(funded)
