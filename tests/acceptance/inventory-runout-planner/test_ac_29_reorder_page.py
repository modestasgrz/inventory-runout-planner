from inventory_runout_planner.fmt import gbp
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import app, kpis, real_data, texts

COLUMNS = [
    "#",
    "Product",
    "Code",
    "Order",
    "Order month",
    "Arrives",
    "Qty",
    "Cost",
    "Status",
    "Limiting factor",
]
FILES = ["products.csv", "monthly_projection.csv", "scenario.csv", "reorder_plan.csv"]


def test_ac_29_reorder_page() -> None:
    """AC-29: Reorder plan lists every order (follow-ups included) in rank order with title-case names and a Status
    column, every reason, 4 labelled downloads, 'Funded total: £X' (= Spend KPI) and the stock value."""
    result = run(real_data(), BASELINE)
    at = app().run()
    at.switch_page("app_pages/reorder_plan.py").run()
    assert not at.exception
    plan = next(d.value for d in at.dataframe if list(d.value.columns) == COLUMNS)
    assert list(plan["#"]) == [line.rank for line in result.plan]
    assert list(plan["Code"].astype(str)) == [line.stock_code for line in result.plan]
    assert list(plan["Product"]) == [line.description.title() for line in result.plan]
    assert list(plan["Status"]) == [
        "✓ Funded" if line.funded else "Not funded" for line in result.plan
    ]
    main = texts(at.main)
    for line in result.plan:
        assert line.reason in main, line.stock_code
    labels = sorted(str(b.proto.label) for b in at.get("download_button"))
    assert labels == sorted(f"Download {f}" for f in FILES)
    funded = gbp(result.kpis.funded_spend_gbp)
    assert f"Funded total: {funded}" in main
    assert kpis(at)["Spend"] == funded
    assert f"Stock value: {gbp(result.kpis.stock_value_gbp)}" in main
