"""Change 3 UI that Change 4 kept: Order now table (AC-40), Methodology backtest (AC-48), every flag group on toy data.
KPI cards, run-out card, header chip, flag sums, Reorder plan and Scenarios checks moved to test_qa_change4_ui.py."""

import html
from fractions import Fraction
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from inventory_runout_planner.data import HISTORY_MONTHS, load
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import PlannerData, Scenario, ScenarioResult
from inventory_runout_planner.planner import backtest, half_up, run
from inventory_runout_planner.presets import BASELINE, PRESETS
from streamlit.testing.v1 import AppTest

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "data"
EDGES: dict[str, dict[str, Any]] = {
    "budget 0": {"budget_gbp": 0},
    "horizon 6": {"horizon_months": 6},
    "growth -50": {"growth_pct": -50},
    "growth 100": {"growth_pct": 100},
    "delay 26": {"delay_weeks": 26},
    "trailing_3m": {"method": "trailing_3m"},
}
CASES: dict[str, Scenario] = {
    **PRESETS,
    **{name: BASELINE.model_copy(update=combo) for name, combo in EDGES.items()},
}
FLAG_TYPES = [
    "Lead time",
    "Budget not funded",
    "Capacity blocks order",
    "Short after plan",
    "Overstocked",
    "Inbound arrives after horizon",
]
ORDER_NOW_COLUMNS = [
    "Product",
    "Code",
    "Runs out",
    "Order by",
    "Qty",
    "Cost £",
    "Funded",
    "Limiting factor",
]


def whole(x: float) -> int:
    return half_up(Fraction(str(x)))


def start(case: str) -> AppTest:
    """Open the app and put the sidebar into the named preset or edge scenario."""
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    if case in PRESETS:
        return at.selectbox(key="preset").select(case).run()
    for key, value in EDGES[case].items():
        if key == "horizon_months":
            at.slider(key=key).set_value(value)
        elif key == "method":
            at.radio(key=key).set_value(value)
        else:
            at.number_input(key=key).set_value(value)
    return at.run()


def text(at: AppTest) -> str:
    parts = [str(m.value) for m in at.markdown] + [str(c.value) for c in at.caption]
    return html.unescape("\n".join(parts))


def expected_flag_groups(r: ScenarioResult) -> dict[str, tuple[int, float]]:
    ps = r.products
    groups = {
        "Lead time": [p.stockout.lost_sales_gbp for p in ps if p.stockout],
        "Budget not funded": [o.cost_gbp for p in ps for o in p.orders if not o.funded],
        "Capacity blocks order": [
            p.lost_sales_after_plan_gbp
            for p in ps
            if any(f.startswith("Capacity blocks order") for f in p.flags)
        ],
        "Short after plan": [
            p.later_shortfall_gbp for p in ps if p.later_shortfall_units > 0
        ],
        "Overstocked": [
            p.tied_up_gbp
            for p in ps
            if any(f.startswith("Overstocked") for f in p.flags)
        ],
        "Inbound arrives after horizon": [
            0.0 for p in ps if "Inbound arrives after horizon" in p.flags
        ],
    }
    return {
        name: (len(values), round(sum(values), 2))
        for name, values in groups.items()
        if values
    }


@pytest.fixture(scope="module")
def real() -> PlannerData:
    return load(DATA)


@pytest.mark.parametrize("case", list(CASES))
def test_order_now_table_matches_core(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    frame = next(
        d.value for d in at.dataframe if list(d.value.columns) == ORDER_NOW_COLUMNS
    )
    expected = [p for p in r.products if p.order_now]
    assert list(frame["Code"]) == [p.stock_code for p in expected], case
    for (_, row), p in zip(frame.iterrows(), expected, strict=True):
        assert row["Runs out"] == month(p.runout_month or "")
        if p.order:
            assert row["Qty"] == number(p.order.qty)
            assert row["Cost £"] == number(p.order.cost_gbp)
            assert row["Funded"] == ("✓ Funded" if p.order.funded else "Not funded")
        else:
            assert row["Funded"] == ""


@pytest.mark.parametrize("method", ["seasonal_naive", "trailing_3m"])
def test_methodology_numbers_equal_backtest(method: str, real: PlannerData) -> None:
    seasonal = backtest(real, "seasonal_naive")
    trailing = backtest(real, "trailing_3m")
    at = start("Baseline" if method == "seasonal_naive" else "trailing_3m")
    at.switch_page("app_pages/methodology.py").run()
    assert not at.exception
    page = text(at)
    assert (
        f"Weighted forecast error (WAPE), seasonal naive: {whole(seasonal.overall_pct)}%"
        in page
    )
    assert (
        f"Weighted forecast error (WAPE), trailing 3-month: {whole(trailing.overall_pct)}%"
        in page
    )
    mapes = [x.mape_pct for x in seasonal.rows if x.mape_pct is not None]
    mean = whole(round(sum(mapes) / len(mapes), 10))
    assert f"Plain average of per-product MAPE, seasonal naive: {mean}%" in page
    assert "WAPE = Σ |actual − forecast| ÷ Σ actual" in page
    frame = next(
        d.value for d in at.dataframe if "MAPE seasonal naive %" in d.value.columns
    )
    assert len(frame) == 36
    assert list(frame["Code"]) == [x.stock_code for x in seasonal.rows]
    trailing_by = {x.stock_code: x.mape_pct for x in trailing.rows}
    for (_, row), x in zip(frame.iterrows(), seasonal.rows, strict=True):
        assert abs(float(row["MAPE seasonal naive %"]) - (x.mape_pct or 0)) <= 0.5
        assert (
            abs(
                float(row["MAPE trailing 3-month %"]) - (trailing_by[x.stock_code] or 0)
            )
            <= 0.5
        )


TOY_DEFAULTS: dict[str, Any] = {
    "group": "Gifts & small goods",
    "unit_cost": 2.0,
    "stock_on_hand": 100,
    "lead_time_weeks": 4,
    "moq": 50,
    "capacity": 400,
    "inbound_qty": 0,
    "inbound_weeks": 0,
}


def write_toy(directory: Path, products: dict[str, dict[str, Any]]) -> None:
    """Flat demand 60 every month, sell price £5.00, AC toy defaults unless overridden."""
    rows = [
        {
            "stock_code": code,
            "description": f"TOY ITEM {code}",
            "group": "Gifts & small goods",
            "month": m,
            "units": 60,
        }
        for code in products
        for m in HISTORY_MONTHS
    ]
    pd.DataFrame(rows).to_csv(directory / "demand_monthly.csv", index=False)
    pd.DataFrame(
        [
            {"stock_code": code, "description": f"TOY ITEM {code}"}
            | TOY_DEFAULTS
            | overrides
            for code, overrides in products.items()
        ]
    ).to_csv(directory / "products_synthetic.csv", index=False)
    pd.DataFrame(
        [{"stock_code": code, "median_price": 5.0} for code in products]
    ).to_csv(directory / "median_prices.csv", index=False)


def test_toy_flag_groups_every_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    products: dict[str, dict[str, Any]] = {
        "T0002": {"lead_time_weeks": 10},
        "T0009": {"moq": 400},
        "T0005": {"stock_on_hand": 1000},
        "T0010": {"stock_on_hand": 500, "inbound_qty": 100, "inbound_weeks": 60},
        "T0001": {"unit_cost": 1.0},
    }
    write_toy(tmp_path, products)
    monkeypatch.setenv("RUNOUT_DATA_DIR", str(tmp_path))
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    at.number_input(key="budget_gbp").set_value(300).run()
    assert not at.exception
    r = run(load(tmp_path), BASELINE.model_copy(update={"budget_gbp": 300}))
    expected = expected_flag_groups(r)
    assert {
        "Lead time",
        "Budget not funded",
        "Capacity blocks order",
        "Short after plan",
        "Overstocked",
        "Inbound arrives after horizon",
    } <= set(expected), expected
    shown = {
        e.label.split(" · ")[0]: e.label
        for e in at.expander
        if e.label.split(" · ")[0] in FLAG_TYPES
    }
    assert set(shown) == set(expected)
    for name, (count, total) in expected.items():
        parts = shown[name].split(" · ")
        assert parts[1] == number(count), shown[name]
        if name != "Inbound arrives after horizon":
            assert parts[2].startswith(gbp(total)), shown[name]
    order = [
        e.label.split(" · ")[0]
        for e in at.expander
        if e.label.split(" · ")[0] in FLAG_TYPES
    ]
    assert order[0] == "Lead time"
    rest = [expected[n][1] for n in order[1:]]
    assert rest == sorted(rest, reverse=True)
    assert shown["Budget not funded"] == (
        f"Budget not funded · {number(r.kpis.unfunded_orders)} · {gbp(r.kpis.unfunded_gbp)} short"
    )
    assert shown["Short after plan"] == (
        f"Short after plan · {number(expected['Short after plan'][0])} · {gbp(r.kpis.later_shortfall_gbp)} lost sales"
    )
    assert not any(e.label.startswith("Later shortfall") for e in at.expander)
