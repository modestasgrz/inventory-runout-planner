from typing import Any

from inventory_runout_planner.fmt import gbp, number
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import PAGES, app, real_data, texts


def test_ac_52_readability() -> None:
    """AC-52: Overview's 3-line strip with live values (Overview only), plain-words KPI help, product name under
    Earliest run-out, Funded as text in Order now, 'products' on the run-outs y-axis."""
    result = run(real_data(), BASELINE)
    k = result.kpis
    first = next(p for p in result.products if p.stock_code == k.earliest_runout_code)
    at = app().run()
    assert not at.exception
    main = texts(at.main)
    for label in ("The question", "Right now", "Do this"):
        assert label in main, label
    for value in (
        f"{number(k.products_at_risk)} of {number(len(result.products))} products run short",
        gbp(k.budget_gbp),
        gbp(k.funded_spend_gbp),
        gbp(k.lost_sales_after_plan_gbp),
        first.description.title(),
    ):
        assert value in main, value
    for m in at.metric:
        assert m.proto.help.startswith("In plain words:"), m.label
        assert "=" in m.proto.help, m.label
    earliest = next(m for m in at.metric if m.label == "Earliest run-out")
    assert str(earliest.proto.delta) == first.description.title()
    table = next(d.value for d in at.dataframe if "Runs out" in d.value.columns)
    wanted = [
        ("✓ Funded" if p.order.funded else "Not funded") if p.order else ""
        for p in result.products
        if p.order_now
    ]
    assert list(table["Funded"]) == wanted
    charts: list[Any] = at.get("plotly_chart")
    titles = [str(c.proto.spec) for c in charts]
    assert any('"text":"products"' in t.replace(" ", "") for t in titles)
    for page in PAGES[1:]:
        at.switch_page(page).run()
        assert "The question" not in texts(at.main), page
