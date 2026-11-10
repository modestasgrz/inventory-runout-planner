from typing import Any

from inventory_runout_planner import planner
from runout_toy import product, real_data, toy_data

B1 = [60] * 9 + [120] * 3 + [75] * 12
B2 = [100] * 12 + [50] * 11 + [0]


def test_ac_42_backtest() -> None:
    """AC-42: forecast as of Dec 2010 vs actual Dec 2010–Nov 2011; MAPE per product (zero months skipped),
    overall = Σ|error| ÷ Σ actual."""
    backtest: Any = vars(planner)["backtest"]
    data = toy_data(
        product("B0001"), product("B0002"), history={"B0001": B1, "B0002": B2}
    )
    seasonal = backtest(data, "seasonal_naive")
    assert seasonal.as_of == "2010-12"
    assert {r.stock_code: r.mape_pct for r in seasonal.rows} == {
        "B0001": 30.0,
        "B0002": 100.0,
    }
    assert seasonal.overall_pct == 63.45
    trailing = backtest(data, "trailing_3m")
    assert {r.stock_code: r.mape_pct for r in trailing.rows} == {
        "B0001": 60.0,
        "B0002": 100.0,
    }
    assert trailing.overall_pct == 82.07
    real = real_data()
    for method in ("seasonal_naive", "trailing_3m"):
        result = backtest(real, method)
        assert len(result.rows) == 36, method
        assert result.overall_pct > 0, method
