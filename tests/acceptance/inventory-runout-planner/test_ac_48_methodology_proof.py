from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from inventory_runout_planner import planner
from runout_toy import app, real_data, texts

COLUMNS = ["Product", "Code", "MAPE seasonal naive %", "MAPE trailing 3-month %"]


def whole(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def test_ac_48_methodology_proof() -> None:
    """AC-48: Methodology shows the money formulas, the later-shortfall rule and the backtest table + overall errors."""
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
    assert "Later shortfall not covered" in main
    table = next(d.value for d in at.dataframe if list(d.value.columns) == COLUMNS)
    assert len(table) == 36
    seasonal = whole(backtest(data, "seasonal_naive").overall_pct)
    trailing = whole(backtest(data, "trailing_3m").overall_pct)
    assert f"Overall error, seasonal naive: {seasonal}%" in main
    assert f"Overall error, trailing 3-month: {trailing}%" in main
