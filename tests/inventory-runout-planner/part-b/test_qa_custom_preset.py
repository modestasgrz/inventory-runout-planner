from pathlib import Path
from typing import Any

import pytest
from inventory_runout_planner.data import load
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import Scenario, ScenarioResult
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from streamlit.testing.v1 import AppTest

REPO = Path(__file__).resolve().parents[3]
DATA = load(REPO / "data")
PAGES = [
    "app_pages/overview.py",
    "app_pages/forecast.py",
    "app_pages/scenarios.py",
    "app_pages/reorder_plan.py",
    "app_pages/methodology.py",
]
EDITS: list[tuple[str, str, Any, Any]] = [
    ("slider", "horizon_months", 8, 8),
    ("number_input", "growth_pct", 12.5, 12.5),
    ("number_input", "delay_weeks", 5, 5),
    (
        "number_input",
        "budget_gbp",
        BASELINE.budget_gbp + 1000,
        BASELINE.budget_gbp + 1000,
    ),
    ("number_input", "safety_months", 2.5, 2.5),
    ("radio", "method", "trailing_3m", "trailing_3m"),
]


def app() -> AppTest:
    return AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()


def kpis(at: AppTest) -> dict[str, tuple[str, str]]:
    """Every DEC-14 card in page order: label -> (value, sub-line)."""
    return {m.label: (str(m.value), str(m.proto.delta)) for m in at.metric}


def expected(result: ScenarioResult) -> dict[str, tuple[str, str]]:
    k = result.kpis
    return {
        "At risk": (
            number(k.products_at_risk),
            f"of {number(len(result.products))} products",
        ),
        "Earliest run-out": (
            month(k.earliest_runout_month)
            if k.earliest_runout_month
            else "None in horizon",
            next(
                (
                    p.description.title()
                    for p in result.products
                    if p.stock_code == k.earliest_runout_code
                ),
                "—",
            ),
        ),
        "Spend": (gbp(k.funded_spend_gbp), f"of {gbp(k.budget_gbp)}"),
        "Unfunded": (
            number(k.unfunded_orders),
            f"{gbp(k.unfunded_gbp)} short" if k.unfunded_orders else "none",
        ),
        "Lost sales": (
            gbp(k.lost_sales_after_plan_gbp),
            f"{gbp(k.lost_sales_gbp)} if nothing ordered",
        ),
    }


def widget(at: AppTest, kind: str, key: str) -> Any:
    return getattr(at, kind)(key=key)


def edit(at: AppTest, kind: str, key: str, value: Any) -> AppTest:
    widget(at, kind, key).set_value(value)
    return at.run()


def inputs(at: AppTest) -> dict[str, Any]:
    return {
        "horizon_months": at.slider(key="horizon_months").value,
        "growth_pct": at.number_input(key="growth_pct").value,
        "delay_weeks": at.number_input(key="delay_weeks").value,
        "budget_gbp": at.number_input(key="budget_gbp").value,
        "safety_months": at.number_input(key="safety_months").value,
        "method": at.radio(key="method").value,
    }


def preset(at: AppTest) -> str:
    return str(at.selectbox(key="preset").value)


def order_now_codes(result: ScenarioResult) -> list[str]:
    return [p.stock_code for p in result.products if p.order_now]


def table_codes(at: AppTest) -> list[str]:
    table = next(d.value for d in at.dataframe if "Runs out" in d.value.columns)
    return [str(c) for c in table["Code"]]


@pytest.mark.parametrize(("kind", "key", "value", "field"), EDITS)
def test_every_input_switches_to_custom_and_kpis_follow(
    kind: str, key: str, value: Any, field: Any
) -> None:
    at = app()
    assert preset(at) == "Baseline"
    at = edit(at, kind, key, value)
    assert not at.exception
    assert preset(at) == "Custom"
    scenario = BASELINE.model_copy(update={key: field})
    assert kpis(at) == expected(run(DATA, scenario))
    assert inputs(at) == scenario.model_dump()


@pytest.mark.parametrize("start", list(PRESETS))
@pytest.mark.parametrize(("kind", "key", "value", "field"), EDITS)
def test_edit_from_any_preset_switches_to_custom(
    start: str, kind: str, key: str, value: Any, field: Any
) -> None:
    at = app()
    at.selectbox(key="preset").select(start).run()
    at = edit(at, kind, key, value)
    assert preset(at) == "Custom"
    scenario = PRESETS[start].model_copy(update={key: field})
    assert kpis(at) == expected(run(DATA, scenario))


@pytest.mark.parametrize("target", list(PRESETS))
def test_reselecting_each_preset_from_custom_reloads_exact_values(target: str) -> None:
    at = app()
    for kind, key, value, _ in EDITS:
        at = edit(at, kind, key, value)
    assert preset(at) == "Custom"
    at.selectbox(key="preset").select(target).run()
    assert not at.exception
    assert preset(at) == target
    assert inputs(at) == PRESETS[target].model_dump()
    assert kpis(at) == expected(run(DATA, PRESETS[target]))


@pytest.mark.parametrize("target", list(PRESETS))
def test_reselecting_same_preset_after_single_edit_reloads(target: str) -> None:
    at = app()
    at.selectbox(key="preset").select(target).run()
    at = edit(at, "number_input", "delay_weeks", 9)
    assert preset(at) == "Custom"
    at.selectbox(key="preset").select(target).run()
    assert preset(at) == target
    assert inputs(at) == PRESETS[target].model_dump()
    assert kpis(at) == expected(run(DATA, PRESETS[target]))


def test_manual_select_custom_keeps_values_and_kpis() -> None:
    at = app()
    at.selectbox(key="preset").select("Peak season +25%").run()
    before_inputs, before_kpis = inputs(at), kpis(at)
    at.selectbox(key="preset").select("Custom").run()
    assert not at.exception
    assert preset(at) == "Custom"
    assert inputs(at) == before_inputs
    assert kpis(at) == before_kpis
    at = edit(at, "number_input", "safety_months", 3)
    at.selectbox(key="preset").select("Custom").run()
    assert preset(at) == "Custom"
    assert at.number_input(key="safety_months").value == 3
    assert at.number_input(key="growth_pct").value == 25
    scenario = PRESETS["Peak season +25%"].model_copy(update={"safety_months": 3.0})
    assert kpis(at) == expected(run(DATA, scenario))


def test_select_custom_on_fresh_app_keeps_baseline_values() -> None:
    at = app()
    at.selectbox(key="preset").select("Custom").run()
    assert preset(at) == "Custom"
    assert inputs(at) == BASELINE.model_dump()
    assert kpis(at) == expected(run(DATA, BASELINE))


def test_reset_from_custom_returns_to_baseline() -> None:
    at = app()
    for kind, key, value, _ in EDITS:
        at = edit(at, kind, key, value)
    assert preset(at) == "Custom"
    at.button(key="reset").click().run()
    assert not at.exception
    assert preset(at) == "Baseline"
    assert inputs(at) == BASELINE.model_dump()
    assert kpis(at) == expected(run(DATA, BASELINE))


def test_reset_from_invalid_custom_clears_error() -> None:
    at = edit(app(), "number_input", "budget_gbp", 2_000_000)
    assert preset(at) == "Custom"
    assert len(at.error) == 1
    at.button(key="reset").click().run()
    assert len(at.error) == 0
    assert preset(at) == "Baseline"


@pytest.mark.parametrize("page", PAGES)
def test_custom_survives_page_switch(page: str) -> None:
    at = app()
    at = edit(at, "number_input", "growth_pct", 15)
    at = edit(at, "radio", "method", "trailing_3m")
    scenario = BASELINE.model_copy(update={"growth_pct": 15.0, "method": "trailing_3m"})
    at.switch_page(page).run()
    assert not at.exception
    assert preset(at) == "Custom"
    assert inputs(at) == scenario.model_dump()
    assert kpis(at) == expected(run(DATA, scenario))
    at.switch_page(PAGES[0]).run()
    assert preset(at) == "Custom"
    assert kpis(at) == expected(run(DATA, scenario))


def test_custom_survives_walk_through_all_pages() -> None:
    at = edit(app(), "slider", "horizon_months", 9)
    scenario = BASELINE.model_copy(update={"horizon_months": 9})
    for page in [*PAGES, *reversed(PAGES)]:
        at.switch_page(page).run()
        assert not at.exception, page
        assert preset(at) == "Custom", page
        assert kpis(at) == expected(run(DATA, scenario)), page


@pytest.mark.parametrize("page", PAGES)
def test_edit_on_other_pages_switches_to_custom(page: str) -> None:
    at = app()
    at.switch_page(page).run()
    at = edit(at, "number_input", "delay_weeks", 4)
    assert not at.exception
    assert preset(at) == "Custom"
    scenario = BASELINE.model_copy(update={"delay_weeks": 4})
    assert kpis(at) == expected(run(DATA, scenario))


@pytest.mark.parametrize("target", list(PRESETS))
@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("growth_pct", 150),
        ("growth_pct", -51),
        ("delay_weeks", 27),
        ("budget_gbp", 1_000_001),
        ("safety_months", 6.5),
    ],
)
def test_invalid_input_then_any_preset_clears_error(
    target: str, key: str, bad: float
) -> None:
    at = edit(app(), "number_input", key, bad)
    assert preset(at) == "Custom"
    assert len(at.error) == 1
    at.selectbox(key="preset").select(target).run()
    assert not at.exception
    assert len(at.error) == 0
    assert preset(at) == target
    assert inputs(at) == PRESETS[target].model_dump()
    assert kpis(at) == expected(run(DATA, PRESETS[target]))


def test_invalid_then_custom_keeps_error() -> None:
    at = edit(app(), "number_input", "growth_pct", 150)
    at.selectbox(key="preset").select("Custom").run()
    assert not at.exception
    assert len(at.error) == 1
    assert preset(at) == "Custom"


@pytest.mark.parametrize(("kind", "key", "value", "field"), EDITS)
def test_overview_order_now_table_matches_for_custom(
    kind: str, key: str, value: Any, field: Any
) -> None:
    at = edit(app(), kind, key, value)
    scenario = BASELINE.model_copy(update={key: field})
    result = run(DATA, scenario)
    assert preset(at) == "Custom"
    assert table_codes(at) == order_now_codes(result)
    assert kpis(at)["At risk"][0] == number(result.kpis.products_at_risk)


@pytest.mark.parametrize(
    "update",
    [
        {"delay_weeks": 26},
        {"growth_pct": 100, "delay_weeks": 12},
        {"growth_pct": -50},
        {"horizon_months": 6},
        {"safety_months": 6.0, "method": "trailing_3m"},
        {"budget_gbp": 0.0},
    ],
)
def test_overview_order_now_table_matches_multi_edit_custom(
    update: dict[str, Any],
) -> None:
    at = app()
    for key, value in update.items():
        kind = {"horizon_months": "slider", "method": "radio"}.get(key, "number_input")
        at = edit(at, kind, key, value)
    scenario = Scenario.model_validate(BASELINE.model_dump() | update)
    result = run(DATA, scenario)
    assert preset(at) == "Custom"
    assert table_codes(at) == order_now_codes(result)
    assert kpis(at)["At risk"][0] == number(result.kpis.products_at_risk)
