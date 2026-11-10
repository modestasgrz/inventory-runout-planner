from pathlib import Path

import pandas as pd
import pytest
from inventory_runout_planner.data import DataError, load
from inventory_runout_planner.models import (
    PlannerData,
    Product,
    Scenario,
    scenario_errors,
)
from inventory_runout_planner.planner import lead_months, month_key, run

MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)
SCENARIO = Scenario(
    horizon_months=6,
    growth_pct=0,
    delay_weeks=0,
    budget_gbp=1000,
    safety_months=1.0,
    method="seasonal_naive",
)


def make(code: str = "T1", **overrides: float) -> Product:
    fields: dict[str, int | float | str] = {
        "stock_code": code,
        "description": "TOY",
        "group": "Gifts & small goods",
        "unit_cost": 2.0,
        "stock_on_hand": 100,
        "lead_time_weeks": 4,
        "moq": 50,
        "capacity": 400,
        "inbound_qty": 0,
        "inbound_weeks": 0,
    }
    return Product.model_validate(fields | overrides)


def data(*products: Product, demand: int = 60) -> PlannerData:
    return PlannerData(
        products=list(products),
        history={p.stock_code: [demand] * 24 for p in products},
        history_months=MONTHS,
        prices={p.stock_code: 5.0 for p in products},
    )


def test_month_key_rolls_over_years() -> None:
    assert [month_key(t) for t in (1, 2, 13, 14)] == [
        "2011-12",
        "2012-01",
        "2012-12",
        "2013-01",
    ]


def test_lead_months_boundaries() -> None:
    assert lead_months(0) == 0
    assert lead_months(4) == 1
    assert lead_months(5) == 2  # 35 / 30.44 = 1.15


def test_fractional_delay_is_an_error() -> None:
    raw: dict[str, float | int | str] = {
        "horizon_months": 12,
        "growth_pct": 0,
        "delay_weeks": 1.5,
        "budget_gbp": 0,
        "safety_months": 0,
        "method": "trailing_3m",
    }
    assert scenario_errors(raw) == [
        "Supplier delay (weeks) must be between 0 and 26 — you entered 1.5."
    ]


def test_inbound_after_horizon_is_flagged_and_ignored_in_view() -> None:
    p = run(
        data(make(stock_on_hand=1000, inbound_qty=500, inbound_weeks=40)), SCENARIO
    ).products[0]
    assert "Inbound arrives after horizon" in p.flags
    assert sum(r.inbound for r in p.months) == 0


def test_zero_demand_and_zero_stock_is_not_overstocked() -> None:
    p = run(data(make(stock_on_hand=0), demand=0), SCENARIO).products[0]
    assert p.cover_months == 0.0
    assert p.flags == []
    assert p.order is None
    assert p.limiting_factor == "none"


def test_no_runout_but_safety_breach_orders_with_safety_reason() -> None:
    p = run(data(make(stock_on_hand=400)), SCENARIO).products[0]
    assert p.runout_month is None
    assert p.order is not None
    assert p.order.reason.startswith("Falls below safety stock in")
    assert p.limiting_factor == "none"


def test_unfunded_reason_states_remaining_budget() -> None:
    result = run(data(make()), SCENARIO.model_copy(update={"budget_gbp": 300}))
    assert result.plan[0].reason.endswith("Not funded: £300.00 left of budget.")


def test_order_arriving_after_horizon_keeps_plan_rows_unchanged() -> None:
    long_lead = SCENARIO.model_copy(update={"delay_weeks": 26})
    p = run(data(make(lead_time_weeks=12)), long_lead).products[0]
    assert p.order is not None
    assert p.order.funded
    assert p.plan_months == p.months


def test_load_missing_products_file(tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "stock_code": ["T1"],
            "description": ["X"],
            "group": ["G"],
            "month": ["2011-11"],
            "units": [1],
        }
    ).to_csv(tmp_path / "demand_monthly.csv", index=False)
    with pytest.raises(DataError, match="Data file not found: products_synthetic.csv"):
        load(tmp_path)


def test_load_product_without_history(tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "stock_code": "T1",
            "description": "X",
            "group": "G",
            "month": MONTHS,
            "units": 1,
        }
    ).to_csv(tmp_path / "demand_monthly.csv", index=False)
    pd.DataFrame([make("T2").model_dump()]).to_csv(
        tmp_path / "products_synthetic.csv", index=False
    )
    pd.DataFrame({"stock_code": ["T2"], "median_price": [1.0]}).to_csv(
        tmp_path / "median_prices.csv", index=False
    )
    with pytest.raises(DataError, match="No demand history for: T2"):
        load(tmp_path)


def test_load_negative_units_is_a_data_error(tmp_path: Path) -> None:
    units = [1] * 23 + [-500]
    pd.DataFrame(
        {
            "stock_code": "T1",
            "description": "X",
            "group": "G",
            "month": MONTHS,
            "units": units,
        }
    ).to_csv(tmp_path / "demand_monthly.csv", index=False)
    pd.DataFrame([make("T1").model_dump()]).to_csv(
        tmp_path / "products_synthetic.csv", index=False
    )
    pd.DataFrame({"stock_code": ["T1"], "median_price": [1.0]}).to_csv(
        tmp_path / "median_prices.csv", index=False
    )
    with pytest.raises(DataError, match="units must be whole numbers"):
        load(tmp_path)
