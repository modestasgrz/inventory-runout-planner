from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from inventory_runout_planner import planner
from inventory_runout_planner.fmt import gbp
from inventory_runout_planner.presets import BASELINE
from runout_toy import PAGES, app, kpis, real_data, texts


def test_ac_46_overview_money() -> None:
    """AC-46: every page header shows 'Forecast error <n>%' (WAPE of the selected method); the Lost sales KPI is the
    full-horizon figure with the plan, sub-line '<£> if nothing ordered', help with its formula."""
    data = real_data()
    backtest: Any = vars(planner)["backtest"]
    overall = backtest(data, BASELINE.method).overall_pct
    n = int(Decimal(str(overall)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    k = planner.run(data, BASELINE).kpis.model_dump()
    at = app().run()
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        assert f"Forecast error {n}%" in texts(at.main), page
    assert kpis(at)["Lost sales"] == gbp(k["lost_sales_after_plan_gbp"])
    metric = next(m for m in at.metric if m.label == "Lost sales")
    assert str(metric.proto.delta) == f"{gbp(k['lost_sales_gbp'])} if nothing ordered"
    assert "=" in metric.proto.help
