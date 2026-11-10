import html
import re
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
PAGES = [
    "app_pages/overview.py",
    "app_pages/forecast.py",
    "app_pages/scenarios.py",
    "app_pages/reorder_plan.py",
    "app_pages/methodology.py",
]
KPI_ORDER = [
    "Products at risk",
    "Earliest run-out",
    "Purchase spend",
    "Unfunded orders",
    "Lost sales after plan",
]
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
    "Later shortfall not covered",
    "Overstocked",
    "Inbound arrives after horizon",
]
REORDER_COLUMNS = [
    "Urgency rank",
    "Product",
    "Code",
    "Order month",
    "Arrives",
    "Qty",
    "Cost",
    "Funded",
    "Limiting factor",
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
    parts += [str(s.value) for s in at.subheader] + [str(s.value) for s in at.success]
    return html.unescape("\n".join(parts))


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def cards(at: AppTest) -> list[tuple[str, str, str]]:
    return [(m.label, str(m.value), str(m.proto.delta)) for m in at.metric]


def expected_cards(r: ScenarioResult, overview: bool) -> list[tuple[str, str, str]]:
    k = r.kpis
    rows = [
        ("Products at risk", number(k.products_at_risk), ""),
        (
            "Earliest run-out",
            month(k.earliest_runout_month)
            if k.earliest_runout_month
            else "None in horizon",
            k.earliest_runout_code or "",
        ),
        ("Purchase spend", gbp(k.funded_spend_gbp), f"of {gbp(k.budget_gbp)}"),
        (
            "Unfunded orders",
            number(k.unfunded_orders),
            f"{gbp(k.unfunded_gbp)} short" if k.unfunded_orders else "",
        ),
        (
            "Lost sales after plan",
            gbp(k.lost_sales_after_plan_gbp),
            f"{gbp(k.lost_sales_gbp)} if nothing ordered",
        ),
    ]
    return [c for c in rows if not (overview and c[0] == "Earliest run-out")]


def expected_flag_groups(r: ScenarioResult) -> dict[str, tuple[int, float]]:
    ps = r.products
    groups = {
        "Lead time": [p.stockout.lost_sales_gbp for p in ps if p.stockout],
        "Budget not funded": [
            p.order.cost_gbp for p in ps if p.order and not p.order.funded
        ],
        "Capacity blocks order": [
            p.lost_sales_gbp
            for p in ps
            if any(f.startswith("Capacity blocks order") for f in p.flags)
        ],
        "Later shortfall not covered": [
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


def hero_sentence(r: ScenarioResult) -> str | None:
    earliest = next(
        (p for p in r.products if p.stock_code == r.kpis.earliest_runout_code), None
    )
    if earliest is None or earliest.stockout is None:
        return None
    s = earliest.stockout
    span = (
        f"1 month ({month(s.start_month)})"
        if s.months == 1
        else f"{s.months} months ({month(s.start_month)}–{month(s.end_month)})"
    )
    return f"Out of stock {span}, {number(s.units)} units, {gbp(s.lost_sales_gbp)} lost sales. Expedite?"


@pytest.fixture(scope="module")
def real() -> PlannerData:
    return load(DATA)


@pytest.mark.parametrize("case", list(CASES))
def test_all_pages_render_and_kpis_equal_core(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    seen: dict[str, tuple[str, str]] = {}
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, (case, page)
        assert not at.error, (case, page, [e.value for e in at.error])
        got = cards(at)
        overview = page.endswith("overview.py")
        assert [c[0] for c in got] == [
            x for x in KPI_ORDER if not (overview and x == "Earliest run-out")
        ], page
        assert got == expected_cards(r, overview), (case, page)
        for label, value, sub in got:
            assert seen.setdefault(label, (value, sub)) == (value, sub), (
                case,
                page,
                label,
            )
        assert all("=" in str(m.help) for m in at.metric), (case, page)


@pytest.mark.parametrize("case", list(CASES))
def test_overview_flag_groups_match_core(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    expected = expected_flag_groups(r)
    at = start(case)
    assert not at.exception
    shown = [e for e in at.expander if e.label.split(" · ")[0] in FLAG_TYPES]
    names = [e.label.split(" · ")[0] for e in shown]
    assert sorted(names) == sorted(expected), case
    if "Lead time" in names:
        assert names[0] == "Lead time", (case, names)
    totals = [expected[n][1] for n in names if n != "Lead time"]
    assert totals == sorted(totals, reverse=True), (case, names, totals)
    for e in shown:
        parts = e.label.split(" · ")
        name = parts[0]
        count, total = expected[name]
        assert parts[1] == number(count), (case, e.label)
        if name == "Inbound arrives after horizon":
            assert len(parts) == 2, e.label
        else:
            assert len(parts) == 3, e.label
            assert parts[2].startswith(gbp(total) + " "), (case, e.label, gbp(total))
        assert e.proto.expanded == (name == "Lead time"), (case, e.label)
        frame = e.dataframe[0].value
        assert len(frame) == count, (case, name)
        cols = list(frame.columns)
        assert cols.index("Product") < cols.index("Code")
    k = r.kpis
    if k.unfunded_orders:
        assert expected["Budget not funded"] == (k.unfunded_orders, k.unfunded_gbp)
    if "Later shortfall not covered" in expected:
        assert expected["Later shortfall not covered"][1] == k.later_shortfall_gbp
    if "Overstocked" in expected:
        assert expected["Overstocked"][1] == k.tied_up_gbp


@pytest.mark.parametrize("case", list(CASES))
def test_overview_hero_and_wape_match_core(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    page = text(at)
    k = r.kpis
    if k.earliest_runout_code:
        p = next(x for x in r.products if x.stock_code == k.earliest_runout_code)
        hero = strip_tags(page)
        assert f"{p.description.title()} ({p.stock_code})" in hero
        assert month(k.earliest_runout_month or "") in hero
        assert f"Limiting factor: {k.earliest_limiting_factor}" in hero
    sentence = hero_sentence(r)
    if sentence:
        assert sentence in strip_tags(page), case
    else:
        assert "Out of stock" not in strip_tags(page), case
    wape = whole(backtest(real, r.scenario.method).overall_pct)
    assert f"Weighted forecast error (WAPE) last year: {wape}%" in page, case


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
            assert bool(row["Funded"]) == p.order.funded
        else:
            assert not row["Funded"]


@pytest.mark.parametrize("case", list(CASES))
def test_reorder_plan_order_funded_and_stock_value(
    case: str, real: PlannerData
) -> None:
    r = run(real, CASES[case])
    at = start(case)
    at.switch_page("app_pages/reorder_plan.py").run()
    assert not at.exception
    frame = next(d.value for d in at.dataframe if "Urgency rank" in d.value.columns)
    assert list(frame.columns) == REORDER_COLUMNS
    assert "Reason" not in frame.columns
    ordered = sorted(r.plan, key=lambda line: (line.order_month, line.rank))
    assert list(frame["Urgency rank"]) == [line.rank for line in ordered]
    assert frame["Funded"].dtype == bool
    assert list(frame["Funded"]) == [line.funded for line in ordered]
    assert list(frame["Cost"]) == [gbp(line.cost_gbp) for line in ordered]
    assert list(frame["Qty"]) == [number(line.qty) for line in ordered]
    assert list(frame["Order month"]) == [month(line.order_month) for line in ordered]
    page = text(at)
    assert f"Stock value: {gbp(r.kpis.stock_value_gbp)}" in page
    assert f"Funded total: {gbp(r.kpis.funded_spend_gbp)}" in page
    why = next(e for e in at.expander if e.label.startswith("Why each order"))
    reasons = html.unescape("\n".join(str(m.value) for m in why.markdown))
    for line in r.plan:
        assert line.reason in reasons, line.stock_code
    if r.scenario.budget_gbp == 0:
        assert not frame["Funded"].any()


@pytest.mark.parametrize("case", ["Baseline", "budget 0", "growth 100", "delay 26"])
def test_scenarios_table_independent_of_current_scenario(
    case: str, real: PlannerData
) -> None:
    at = start(case)
    at.switch_page("app_pages/scenarios.py").run()
    assert not at.exception
    frame = next(d.value for d in at.dataframe if "Preset" in d.value.columns)
    assert list(frame["Preset"]) == list(PRESETS)
    for (_, row), (name, preset) in zip(frame.iterrows(), PRESETS.items(), strict=True):
        k = run(real, preset).kpis
        assert row["Products at risk"] == k.products_at_risk, name
        assert row["Unfunded orders"] == k.unfunded_orders, name
        assert row["Unfunded £"] == whole(k.unfunded_gbp), name
        assert row["Lost sales £"] == whole(k.lost_sales_after_plan_gbp), name
        assert row["Stock-out months"] == k.stockout_months, name
        assert row["Earliest run-out"] == (
            f"{month(k.earliest_runout_month)} · {k.earliest_runout_code}"
            if k.earliest_runout_month
            else "None"
        ), name
        assert "(" not in str(row["Earliest run-out"])
    s = CASES[case]
    assert gbp(s.budget_gbp) in strip_tags(text(at))


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


def test_overview_wape_follows_selected_method(real: PlannerData) -> None:
    seasonal = whole(backtest(real, "seasonal_naive").overall_pct)
    trailing = whole(backtest(real, "trailing_3m").overall_pct)
    assert seasonal != trailing
    at = start("trailing_3m")
    assert f"Weighted forecast error (WAPE) last year: {trailing}%" in text(at)
    at.radio(key="method").set_value("seasonal_naive").run()
    assert f"Weighted forecast error (WAPE) last year: {seasonal}%" in text(at)


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


def toy_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, products: dict[str, dict[str, Any]]
) -> tuple[AppTest, ScenarioResult]:
    write_toy(tmp_path, products)
    monkeypatch.setenv("RUNOUT_DATA_DIR", str(tmp_path))
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    return at, run(load(tmp_path), BASELINE)


def test_hero_one_month_stockout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, r = toy_app(tmp_path, monkeypatch, {"T0007": {"stock_on_hand": 30}})
    assert not at.exception
    p = r.products[0]
    assert p.limiting_factor == "lead time"
    assert p.stockout is not None and p.stockout.months == 1
    page = strip_tags(text(at))
    assert "Toy Item T0007 (T0007)" in page
    assert (
        f"Out of stock 1 month (Dec 2011), 30 units, {gbp(p.stockout.lost_sales_gbp)} lost sales. Expedite?"
        in page
    )
    assert "–" not in page.split("Out of stock")[1].split("Expedite?")[0]


def test_hero_two_month_stockout_toy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, _ = toy_app(tmp_path, monkeypatch, {"T0002": {"lead_time_weeks": 10}})
    assert not at.exception
    page = strip_tags(text(at))
    assert (
        "Out of stock 2 months (Jan 2012–Feb 2012), 80 units, £400 lost sales. Expedite?"
        in page
    )
    assert "Limiting factor: lead time" in page


def test_hero_stock_limited_has_no_stockout_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, _ = toy_app(tmp_path, monkeypatch, {"T0001": {}})
    assert not at.exception
    page = strip_tags(text(at))
    assert "Toy Item T0001 (T0001)" in page
    assert "Limiting factor: stock" in page
    assert "Out of stock" not in page


def test_no_runout_anywhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at, r = toy_app(
        tmp_path,
        monkeypatch,
        {"T0005": {"stock_on_hand": 1000}, "T0008": {"stock_on_hand": 2000}},
    )
    assert not at.exception
    assert r.kpis.earliest_runout_code is None
    page = strip_tags(text(at))
    assert "Out of stock" not in page
    assert "Limiting factor:" not in page
    labels = [e.label for e in at.expander]
    assert any(label.startswith("Overstocked · 2 · ") for label in labels), labels
    for page_file in PAGES[1:]:
        at.switch_page(page_file).run()
        assert not at.exception, page_file
        earliest = next(m for m in at.metric if m.label == "Earliest run-out")
        assert str(earliest.value) == "None in horizon"
        assert str(earliest.proto.delta) == ""
    at.switch_page("app_pages/scenarios.py").run()
    frame = next(d.value for d in at.dataframe if "Preset" in d.value.columns)
    assert set(frame["Earliest run-out"]) == {"None"}


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
        "Later shortfall not covered",
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
    assert (
        shown["Budget not funded"].split(" · ")[2].startswith(gbp(r.kpis.unfunded_gbp))
    )
