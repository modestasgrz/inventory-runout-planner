from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from inventory_runout_planner import planner
from inventory_runout_planner.fmt import gbp
from inventory_runout_planner.presets import BASELINE
from runout_toy import app, kpis, real_data, texts


def test_ac_46_overview_money() -> None:
    """AC-46: Overview shows last year's weighted forecast error (WAPE) and the Lost sales after plan KPI with its formula."""
    data = real_data()
    backtest: Any = vars(planner)["backtest"]
    overall = backtest(data, "seasonal_naive").overall_pct
    n = int(Decimal(str(overall)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    lost = planner.run(data, BASELINE).kpis.model_dump()["lost_sales_after_plan_gbp"]
    at = app().run()
    assert not at.exception
    assert f"Weighted forecast error (WAPE) last year: {n}%" in texts(at.main)
    assert kpis(at)["Lost sales after plan"].startswith(gbp(lost))
    metric = next(m for m in at.metric if m.label == "Lost sales after plan")
    assert "=" in metric.proto.help
