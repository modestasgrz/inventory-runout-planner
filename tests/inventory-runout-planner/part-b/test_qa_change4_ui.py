"""QA for Change 4 UI (DEC-14, DEC-22): every preset and edge scenario, checked against planner.run."""

import html
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from inventory_runout_planner.data import HISTORY_MONTHS, load
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import (
    PlannerData,
    ProductResult,
    Scenario,
    ScenarioResult,
)
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
KPI_ORDER = ["At risk", "Earliest run-out", "Spend", "Unfunded", "Lost sales"]
BUDGET_LABEL = "Purchase budget (£, whole horizon)"
DOI = "doi.org/10.24432/C5CG6D"
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
REORDER_COLUMNS = [
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
SCENARIO_COLUMNS = [
    "Preset",
    "Products at risk",
    "Lost sales £",
    "vs Baseline £",
    "Unfunded orders",
    "Unfunded £",
    "Earliest run-out",
]


def whole(x: float) -> int:
    return half_up(Fraction(str(x)))


def set_inputs(at: AppTest, inputs: dict[str, Any]) -> AppTest:
    for key, value in inputs.items():
        if key == "horizon_months":
            at.slider(key=key).set_value(value)
        elif key == "method":
            at.radio(key=key).set_value(value)
        else:
            at.number_input(key=key).set_value(value)
    return at.run()


def start(case: str) -> AppTest:
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    if case in PRESETS:
        return at.selectbox(key="preset").select(case).run()
    return set_inputs(at, EDGES[case])


def main_md(at: AppTest) -> str:
    return html.unescape("\n".join(str(m.value) for m in at.main.markdown))


def main_text(at: AppTest) -> str:
    parts = [str(m.value) for m in at.main.markdown]
    parts += [str(c.value) for c in at.main.caption]
    parts += [str(s.value) for s in at.main.subheader]
    parts += [str(s.value) for s in at.main.success]
    return html.unescape("\n".join(parts))


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def cards(at: AppTest) -> list[tuple[str, str, str]]:
    return [(m.label, str(m.value), str(m.proto.delta)) for m in at.metric]


def expected_cards(r: ScenarioResult) -> list[tuple[str, str, str]]:
    k = r.kpis
    return [
        (
            "At risk",
            number(k.products_at_risk),
            f"of {number(len(r.products))} products",
        ),
        (
            "Earliest run-out",
            month(k.earliest_runout_month)
            if k.earliest_runout_month
            else "None in horizon",
            k.earliest_runout_code or "—",
        ),
        ("Spend", gbp(k.funded_spend_gbp), f"of {gbp(k.budget_gbp)}"),
        (
            "Unfunded",
            number(k.unfunded_orders),
            f"{gbp(k.unfunded_gbp)} short" if k.unfunded_orders else "none",
        ),
        (
            "Lost sales",
            gbp(k.lost_sales_after_plan_gbp),
            f"{gbp(k.lost_sales_gbp)} if nothing ordered",
        ),
    ]


def expected_flag_groups(r: ScenarioResult) -> dict[str, list[tuple[str, float]]]:
    """Group -> (code, £) rows, straight from the core result (DEC-20/DEC-22 grouping)."""
    groups: dict[str, list[tuple[str, float]]] = {name: [] for name in FLAG_TYPES}
    for p in r.products:
        if p.stockout:
            groups["Lead time"].append((p.stock_code, p.stockout.lost_sales_gbp))
        groups["Budget not funded"] += [
            (p.stock_code, o.cost_gbp) for o in p.orders if not o.funded
        ]
        if any(f.startswith("Capacity blocks order") for f in p.flags):
            groups["Capacity blocks order"].append(
                (p.stock_code, p.lost_sales_after_plan_gbp)
            )
        if p.later_shortfall_units > 0:
            groups["Short after plan"].append((p.stock_code, p.later_shortfall_gbp))
        if any(f.startswith("Overstocked") for f in p.flags):
            groups["Overstocked"].append((p.stock_code, p.tied_up_gbp))
        if "Inbound arrives after horizon" in p.flags:
            groups["Inbound arrives after horizon"].append((p.stock_code, 0.0))
    return {name: rows for name, rows in groups.items() if rows}


def flag_expanders(at: AppTest) -> list[Any]:
    return [e for e in at.expander if e.label.split(" · ")[0] in FLAG_TYPES]


def earliest(r: ScenarioResult) -> ProductResult | None:
    return next(
        (p for p in r.products if p.stock_code == r.kpis.earliest_runout_code), None
    )


def expected_status(p: ProductResult) -> str:
    """DEC-22 status line, built from the core result."""
    gap = p.stockout
    if gap is None:
        return f"Runs out {month(p.runout_month or '')} if nothing is ordered"
    horizon = {row.month for row in p.months}
    arrivals = sorted(
        o.arrival_month for o in p.orders if o.funded and o.arrival_month in horizon
    )
    if not arrivals:
        return f"Out of stock from {month(gap.start_month)}, no funded order arrives in the horizon"
    span = (
        month(gap.start_month)
        if gap.months == 1
        else f"{month(gap.start_month)}–{month(gap.end_month)}"
    )
    return f"Out of stock {span}, covered from {month(arrivals[0])}"


def hero(at: AppTest) -> dict[str, str]:
    block = next(
        str(m.value) for m in at.main.markdown if "runout-hero" in str(m.value)
    )
    parts = {
        cls: html.unescape(strip_tags(m.group(1)))
        for cls, m in (
            (cls, re.search(rf'class="{cls}">(.*?)</div>', block))
            for cls in ("product", "status", "reason", "cost", "later")
        )
        if m
    }
    parts["chips"] = "|".join(re.findall(r'class="chip[^"]*"[^>]*>([^<]*)<', block))
    return parts


@pytest.fixture(scope="module")
def real() -> PlannerData:
    return load(DATA)


@pytest.mark.parametrize("case", list(CASES))
def test_kpi_cards_equal_core_and_identical_on_all_pages(
    case: str, real: PlannerData
) -> None:
    r = run(real, CASES[case])
    expected = expected_cards(r)
    at = start(case)
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, (case, page)
        assert not at.error, (case, page, [e.value for e in at.error])
        assert cards(at) == expected, (case, page)
        for m in at.metric:
            assert "=" in m.proto.help, (case, page, m.label)


@pytest.mark.parametrize("case", list(CASES))
def test_header_chip_and_sidebar_on_every_page(case: str, real: PlannerData) -> None:
    wape = whole(backtest(real, CASES[case].method).overall_pct)
    at = start(case)
    for page in PAGES:
        at.switch_page(page).run()
        head = main_md(at)
        chip = re.search(
            r'<span class="chip" title="([^"]+)">Forecast error (\d+)% ', head
        )
        assert chip is not None, (case, page)
        assert int(chip.group(2)) == wape, (case, page)
        assert "WAPE" in chip.group(1)
        assert "Synthetic stock data — demonstration only" in head
        assert "Data as of Dec 2011" in head
        assert "Planning as of" not in main_text(at)
        captions = [str(c.value) for c in at.sidebar.caption]
        assert len(captions) == 2, captions
        assert captions[0].startswith("Planning as of 1 Dec 2011 · ")
        assert (
            captions[1]
            == "Demand: UCI Online Retail II (CC BY 4.0) · stock data synthetic"
        )
        assert DOI not in " ".join(
            str(m.value) for m in at.sidebar.markdown
        ) + " ".join(captions)
        assert at.number_input(key="budget_gbp").label == BUDGET_LABEL
        if not page.endswith("methodology.py"):
            assert DOI not in main_text(at), page
    assert DOI in main_text(at)


def test_header_chip_follows_method_switch(real: PlannerData) -> None:
    seasonal = whole(backtest(real, "seasonal_naive").overall_pct)
    trailing = whole(backtest(real, "trailing_3m").overall_pct)
    assert seasonal != trailing
    at = start("Baseline")
    assert f"Forecast error {seasonal}%" in main_md(at)
    at.radio(key="method").set_value("trailing_3m").run()
    assert f"Forecast error {trailing}%" in main_md(at)
    assert f"Forecast error {seasonal}%" not in main_md(at)
    at.radio(key="method").set_value("seasonal_naive").run()
    assert f"Forecast error {seasonal}%" in main_md(at)


@pytest.mark.parametrize("case", list(CASES))
def test_flag_groups_equal_core_sums(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    k = r.kpis
    expected = expected_flag_groups(r)
    at = start(case)
    assert not at.exception
    shown = flag_expanders(at)
    names = [e.label.split(" · ")[0] for e in shown]
    assert sorted(names) == sorted(expected), case
    assert len(set(names)) == len(names)
    if "Lead time" in names:
        assert names[0] == "Lead time"
    rest = [round(sum(v for _, v in expected[n]), 2) for n in names if n != "Lead time"]
    assert rest == sorted(rest, reverse=True), (case, names)
    for e in shown:
        parts = e.label.split(" · ")
        name = parts[0]
        rows = expected[name]
        assert parts[1] == number(len(rows)), (case, e.label)
        if name == "Inbound arrives after horizon":
            assert len(parts) == 2, e.label
        else:
            assert len(parts) == 3, e.label
            assert parts[2].startswith(gbp(sum(v for _, v in rows)) + " "), (
                case,
                e.label,
            )
        assert e.proto.expanded == (name == "Lead time"), e.label
        frame = e.dataframe[0].value
        assert list(frame.columns)[:2] == ["Product", "Code"]
        assert sorted(frame["Code"].astype(str)) == sorted(c for c, _ in rows), (
            case,
            name,
        )
    if k.unfunded_orders:
        rows = expected["Budget not funded"]
        assert len(rows) == k.unfunded_orders
        assert round(sum(v for _, v in rows), 2) == k.unfunded_gbp
        label = next(e.label for e in shown if e.label.startswith("Budget not funded"))
        assert (
            label
            == f"Budget not funded · {number(k.unfunded_orders)} · {gbp(k.unfunded_gbp)} short"
        )
    else:
        assert "Budget not funded" not in names
    if k.later_shortfall_gbp:
        label = next(e.label for e in shown if e.label.startswith("Short after plan"))
        assert label.endswith(f" · {gbp(k.later_shortfall_gbp)} lost sales")
        assert (
            round(sum(v for _, v in expected["Short after plan"]), 2)
            == k.later_shortfall_gbp
        )
    if "Overstocked" in expected:
        assert round(sum(v for _, v in expected["Overstocked"]), 2) == k.tied_up_gbp
    assert not any(e.label.startswith("Later shortfall") for e in at.expander)


@pytest.mark.parametrize("case", list(CASES))
def test_runout_card_matches_core(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    page = main_text(at)
    assert "Expedite?" not in page
    assert "(funded)" not in page
    p = earliest(r)
    if p is None:
        assert not any("runout-hero" in str(m.value) for m in at.main.markdown)
        assert "No product runs out within the horizon." in page
        return
    card = hero(at)
    assert card["product"].startswith(f"{p.description.title()} ({p.stock_code})"), card
    assert card["chips"] == p.limiting_factor.capitalize(), card
    assert card["status"] == expected_status(p), (case, card)
    lost = p.stockout.lost_sales_gbp if p.stockout else p.lost_sales_after_plan_gbp
    if lost > 0:
        assert card["cost"] == f"{gbp(lost)} lost sales", (case, card)
    else:
        assert "cost" not in card, (case, card)
    if p.later_shortfall_month and p.stockout:
        assert (
            f"+ {gbp(p.later_shortfall_gbp)} short after plan from {month(p.later_shortfall_month)}"
            in page
        ), (case, card)
    elif p.later_shortfall_month:
        assert f"Short after plan from {month(p.later_shortfall_month)}" in page
    if p.order is not None and p.order.funded:
        assert number(p.order.qty) in card["reason"]
        assert month(p.order.arrival_month) in card["reason"]
    elif p.order is not None:
        assert "not funded" in card["reason"]


@pytest.mark.parametrize("case", list(CASES))
def test_reorder_rows_equal_plan_with_follow_ups(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    at.switch_page("app_pages/reorder_plan.py").run()
    assert not at.exception
    frame = next(d.value for d in at.dataframe if "#" in d.value.columns)
    assert list(frame.columns) == REORDER_COLUMNS
    expected = [
        {
            "#": line.rank,
            "Product": line.description.title(),
            "Code": line.stock_code,
            "Order": line.order_no,
            "Order month": month(line.order_month),
            "Arrives": month(line.arrival_month),
            "Qty": line.qty,
            "Cost": line.cost_gbp,
            "Status": "✓ Funded" if line.funded else "Not funded",
            "Limiting factor": line.limiting_factor,
        }
        for line in sorted(r.plan, key=lambda x: x.rank)
    ]
    assert frame.to_dict("records") == expected, case
    assert list(frame["#"]) == list(range(1, len(r.plan) + 1))
    assert (frame["Order"] > 1).sum() == sum(line.order_no > 1 for line in r.plan)
    page = main_text(at)
    assert f"Funded total: {gbp(r.kpis.funded_spend_gbp)}" in page
    assert f"Stock value: {gbp(r.kpis.stock_value_gbp)}" in page
    assert next(m for m in at.metric if m.label == "Spend").value == gbp(
        r.kpis.funded_spend_gbp
    )
    why = next(e for e in at.expander if e.label.startswith("Why each order"))
    reasons = html.unescape("\n".join(str(m.value) for m in why.markdown))
    for line in r.plan:
        assert line.reason in reasons, (line.stock_code, line.order_no)
    if r.scenario.budget_gbp == 0:
        assert set(frame["Status"]) <= {"Not funded"}


@pytest.mark.parametrize(
    "case",
    ["Baseline", "Tight budget", "budget 0", "growth 100", "delay 26", "horizon 6"],
)
def test_scenarios_table_vs_baseline(case: str, real: PlannerData) -> None:
    runs = {name: run(real, preset).kpis for name, preset in PRESETS.items()}
    base = runs["Baseline"].lost_sales_after_plan_gbp
    at = start(case)
    at.switch_page("app_pages/scenarios.py").run()
    assert not at.exception
    frame = next(d.value for d in at.dataframe if "Preset" in d.value.columns)
    assert list(frame.columns) == SCENARIO_COLUMNS
    assert list(frame["Preset"]) == list(PRESETS)
    for (_, row), (name, k) in zip(frame.iterrows(), runs.items(), strict=True):
        assert row["Products at risk"] == k.products_at_risk, name
        assert abs(row["Lost sales £"] - k.lost_sales_after_plan_gbp) <= 1, name
        assert abs(row["vs Baseline £"] - (k.lost_sales_after_plan_gbp - base)) <= 1, (
            name
        )
        assert row["Unfunded orders"] == k.unfunded_orders, name
        assert abs(row["Unfunded £"] - k.unfunded_gbp) <= 1, name
        assert row["Earliest run-out"] == (
            f"{month(k.earliest_runout_month)} · {k.earliest_runout_code}"
            if k.earliest_runout_month
            else "None"
        ), name
        assert "(" not in str(row["Earliest run-out"])
    assert frame.loc[0, "vs Baseline £"] == 0
    head = [str(m.value) for m in at.main.markdown]
    assert sum('class="chip' in m for m in head) == 1, "only the header chip"
    assert not any("mini-stat" in m or "Horizon" in m for m in head)


def test_scenarios_preset_descriptions_match_presets() -> None:
    """The Baseline lever text names the budget; it must be Baseline's budget (DEC-16, £350 000 in Change 4)."""
    at = start("Baseline")
    at.switch_page("app_pages/scenarios.py").run()
    line = next(
        ln for ln in main_md(at).splitlines() if ln.startswith("- **Baseline:**")
    )
    amounts = re.findall(r"£[\d ]+", line)
    assert amounts == [gbp(PRESETS["Baseline"].budget_gbp)], line


@pytest.mark.parametrize("case", ["Baseline", "Peak season +25%", "budget 0"])
def test_forecast_lists_every_order_of_the_product(
    case: str, real: PlannerData
) -> None:
    r = run(real, CASES[case])
    multi = [p for p in r.products if len(p.orders) >= 2]
    none = [p for p in r.products if not p.orders]
    picks = multi[:4] + none[:1]
    if case != "budget 0":
        assert multi, "real data should have follow-up orders"
    at = start(case)
    at.switch_page("app_pages/forecast.py").run()
    for p in picks:
        at.selectbox(key="product").select(f"{p.description} ({p.stock_code})").run()
        assert not at.exception, p.stock_code
        text = main_md(at)
        for line in p.orders:
            assert f"Order {line.order_no}" in text, (p.stock_code, line.order_no)
            assert line.reason in text, (p.stock_code, line.order_no)
        if not p.orders:
            assert "No order suggested" in text


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
    pd.DataFrame(
        [
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
    ).to_csv(directory / "demand_monthly.csv", index=False)
    pd.DataFrame(
        [
            {"stock_code": code, "description": f"TOY ITEM {code}"} | TOY_DEFAULTS | o
            for code, o in products.items()
        ]
    ).to_csv(directory / "products_synthetic.csv", index=False)
    pd.DataFrame(
        [{"stock_code": code, "median_price": 5.0} for code in products]
    ).to_csv(directory / "median_prices.csv", index=False)


def toy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    products: dict[str, dict[str, Any]],
    inputs: dict[str, Any] | None = None,
) -> tuple[AppTest, ScenarioResult]:
    write_toy(tmp_path, products)
    monkeypatch.setenv("RUNOUT_DATA_DIR", str(tmp_path))
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    if inputs:
        at = set_inputs(at, inputs)
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    return at, run(load(tmp_path), BASELINE.model_copy(update=inputs or {}))


def test_card_lead_time_covered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, r = toy(tmp_path, monkeypatch, {"T0002": {"lead_time_weeks": 10}})
    card = hero(at)
    assert card["product"].startswith("Toy Item T0002 (T0002)")
    assert card["chips"] == "Lead time"
    assert card["status"] == "Out of stock Jan 2012–Feb 2012, covered from Mar 2012"
    assert card["cost"] == "£400 lost sales"
    assert "240" in card["reason"] and "Mar 2012" in card["reason"]
    assert cards(at)[1] == ("Earliest run-out", "Jan 2012", "T0002")
    assert r.products[0].stockout is not None


def test_card_lead_time_unfunded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, r = toy(
        tmp_path, monkeypatch, {"T0002": {"lead_time_weeks": 10}}, {"budget_gbp": 0}
    )
    card = hero(at)
    assert card["chips"] == "Lead time"
    assert (
        card["status"]
        == "Out of stock from Jan 2012, no funded order arrives in the horizon"
    )
    # Jan 2012 … Nov 2012 with nothing arriving: 20 + 10 × 60 = 620 units × £5
    assert card["cost"] == f"{gbp(3100)} lost sales"
    assert "not funded" in card["reason"]
    assert "covered from" not in main_text(at)
    lines = r.products[0].orders
    assert lines[0].cost_gbp == 480.0 and not any(o.funded for o in lines)
    assert cards(at)[3] == (
        "Unfunded",
        number(len(lines)),
        f"{gbp(sum(o.cost_gbp for o in lines))} short",
    )


def test_card_lead_time_funded_but_arrives_after_horizon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, r = toy(
        tmp_path,
        monkeypatch,
        {"T0011": {"lead_time_weeks": 12}},
        {"horizon_months": 6, "delay_weeks": 26},
    )
    p = r.products[0]
    assert p.limiting_factor == "lead time"
    assert p.order is not None and p.order.funded
    card = hero(at)
    assert (
        card["status"]
        == "Out of stock from Jan 2012, no funded order arrives in the horizon"
    )
    assert p.stockout is not None
    assert card["cost"] == f"{gbp(p.stockout.lost_sales_gbp)} lost sales"


def test_card_one_month_stockout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, _ = toy(tmp_path, monkeypatch, {"T0007": {"stock_on_hand": 30}})
    card = hero(at)
    assert card["chips"] == "Lead time"
    assert card["status"] == "Out of stock Dec 2011, covered from Jan 2012"
    assert card["cost"] == "£150 lost sales"


def test_card_stock_limited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at, r = toy(tmp_path, monkeypatch, {"T0001": {}})
    p = r.products[0]
    card = hero(at)
    assert card["chips"] == "Stock"
    assert card["status"] == "Runs out Jan 2012 if nothing is ordered"
    assert "200" in card["reason"] and "Jan 2012" in card["reason"]
    assert (
        p.lost_sales_after_plan_gbp == p.later_shortfall_gbp
    )  # every loss is a later shortfall
    assert "cost" not in card
    assert card["later"] == "No lost sales with the plan"
    assert "Out of stock" not in main_text(at)


def test_card_budget_limited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at, r = toy(tmp_path, monkeypatch, {"T0001": {}}, {"budget_gbp": 300})
    p = r.products[0]
    assert p.limiting_factor == "budget"
    card = hero(at)
    assert card["chips"] == "Budget"
    assert card["status"] == "Runs out Jan 2012 if nothing is ordered"
    assert "not funded" in card["reason"]
    assert card["cost"] == f"{gbp(p.lost_sales_after_plan_gbp)} lost sales"


def test_card_capacity_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at, _ = toy(tmp_path, monkeypatch, {"T0009": {"moq": 400}})
    card = hero(at)
    assert card["chips"] == "Capacity"
    assert card["status"] == "Runs out Jan 2012 if nothing is ordered"
    assert "Capacity blocks order: room 360 < MOQ 400" in card["reason"]


def test_no_runout_card_and_kpis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, r = toy(
        tmp_path,
        monkeypatch,
        {"T0005": {"stock_on_hand": 1000}, "T0008": {"stock_on_hand": 2000}},
    )
    assert r.kpis.earliest_runout_code is None
    assert "No product runs out within the horizon." in main_text(at)
    assert not any("runout-hero" in str(m.value) for m in at.main.markdown)
    assert cards(at) == expected_cards(r)
    assert cards(at)[1] == ("Earliest run-out", "None in horizon", "—")
    assert cards(at)[3] == ("Unfunded", "0", "none")
    labels = [e.label for e in flag_expanders(at)]
    assert labels == [f"Overstocked · 2 · {gbp(r.kpis.tied_up_gbp)} tied up"]
    for page in PAGES[1:]:
        at.switch_page(page).run()
        assert not at.exception, page
        assert cards(at) == expected_cards(r), page
    at.switch_page("app_pages/scenarios.py").run()
    frame = next(d.value for d in at.dataframe if "Preset" in d.value.columns)
    assert set(frame["Earliest run-out"]) == {"None"}
    assert set(frame["vs Baseline £"]) == {0}


def test_follow_up_unfunded_in_flags_and_reorder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-49 case in the UI: budget £700 funds order 1 (£400) but not follow-up order 2 (£360)."""
    at, r = toy(
        tmp_path, monkeypatch, {"T0001": {}}, {"budget_gbp": 700, "horizon_months": 6}
    )
    p = r.products[0]
    assert [(o.order_no, o.funded) for o in p.orders] == [(1, True), (2, False)]
    labels = [e.label for e in flag_expanders(at)]
    assert f"Budget not funded · 1 · {gbp(360)} short" in labels
    assert f"Short after plan · 1 · {gbp(300)} lost sales" in labels
    assert cards(at)[2:] == [
        ("Spend", gbp(400), f"of {gbp(700)}"),
        ("Unfunded", "1", f"{gbp(360)} short"),
        ("Lost sales", gbp(300), f"{gbp(p.lost_sales_gbp)} if nothing ordered"),
    ]
    at.switch_page("app_pages/reorder_plan.py").run()
    frame = at.dataframe[0].value
    assert list(frame["Order"]) == [1, 2]
    assert list(frame["Status"]) == ["✓ Funded", "Not funded"]
    assert list(frame["Limiting factor"]) == ["stock", "budget"]


def test_both_orders_unfunded_in_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-49: budget £380 funds neither order (order 2 is blocked by the unfunded order 1)."""
    at, r = toy(
        tmp_path, monkeypatch, {"T0001": {}}, {"budget_gbp": 380, "horizon_months": 6}
    )
    assert [o.funded for o in r.products[0].orders] == [False, False]
    labels = [e.label for e in flag_expanders(at)]
    assert f"Budget not funded · 2 · {gbp(760)} short" in labels
    assert not any(label.startswith("Short after plan") for label in labels)
    group = next(
        e for e in flag_expanders(at) if e.label.startswith("Budget not funded")
    )
    assert list(group.dataframe[0].value["Code"]) == ["T0001", "T0001"]
