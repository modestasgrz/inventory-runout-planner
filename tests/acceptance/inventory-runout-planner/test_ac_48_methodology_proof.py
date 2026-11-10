from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from inventory_runout_planner import planner
from runout_toy import app, real_data, texts

COLUMNS = ["Product", "Code", "MAPE seasonal naive %", "MAPE trailing 3-month %"]


def whole(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def test_ac_48_methodology_proof() -> None:
    """AC-48: Methodology shows the money formulas, the later-shortfall rule and the backtest table, the WAPE headline and the plain MAPE average."""
    data = real_data()
    backtest: Any = vars(planner)["backtest"]
    at = app().run()
    at.switch_page("app_pages/methodology.py").run()
    assert not at.exception
    main = texts(at.main)
    assert "Lost sales = unmet units × median selling price" in main
    assert (
        "£ tied up = (stock on hand − 6 months of average forecast) × unit cost" in main
    )
    assert "Short after plan" in main
    assert "Follow-up orders" in main
    assert "band = forecast × (1 ± WAPE)" in main
    table = next(d.value for d in at.dataframe if list(d.value.columns) == COLUMNS)
    assert len(table) == 36
    seasonal = backtest(data, "seasonal_naive")
    trailing = whole(backtest(data, "trailing_3m").overall_pct)
    assert "WAPE = Σ |actual − forecast| ÷ Σ actual" in main
    assert (
        f"Weighted forecast error (WAPE), seasonal naive: {whole(seasonal.overall_pct)}%"
        in main
    )
    assert f"Weighted forecast error (WAPE), trailing 3-month: {trailing}%" in main
    mapes = [r.mape_pct for r in seasonal.rows if r.mape_pct is not None]
    plain = whole(sum(mapes) / len(mapes))
    assert f"Plain average of per-product MAPE, seasonal naive: {plain}%" in main
