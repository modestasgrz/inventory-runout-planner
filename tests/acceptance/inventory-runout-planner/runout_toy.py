"""Shared toy fixtures and AppTest helpers for the inventory-runout-planner acceptance tests (spec AC hand cases).

Core imports are inside the helpers so each test fails on its own missing piece, not on another part's module."""

import html
from pathlib import Path
from typing import TYPE_CHECKING, Any

from streamlit.testing.v1 import AppTest

if TYPE_CHECKING:
    from inventory_runout_planner.models import (
        MonthRow,
        PlannerData,
        Product,
        ProductResult,
        Scenario,
        ScenarioResult,
    )

REPO = Path(__file__).resolve().parents[3]
DATA_DIR = REPO / "data"
MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)
PAGES = [
    "app_pages/overview.py",
    "app_pages/forecast.py",
    "app_pages/scenarios.py",
    "app_pages/reorder_plan.py",
    "app_pages/methodology.py",
]
KPI_LABELS = [
    "Products at risk",
    "Earliest run-out",
    "Purchase spend",
    "Unfunded orders",
    "Stock value",
]
PRESET_NAMES = [
    "Baseline",
    "Peak season +25%",
    "Supplier delay +3 weeks",
    "Tight budget",
    "Efficiency",
]


def product(code: str, **overrides: Any) -> "Product":
    from inventory_runout_planner.models import Product

    fields: dict[str, Any] = {
        "stock_code": code,
        "description": f"TOY PRODUCT {code}",
        "group": "Gifts & small goods",
        "unit_cost": 2.00,
        "stock_on_hand": 100,
        "lead_time_weeks": 4,
        "moq": 50,
        "capacity": 400,
        "inbound_qty": 0,
        "inbound_weeks": 0,
    }
    return Product(**(fields | overrides))


def scenario(**overrides: Any) -> "Scenario":
    from inventory_runout_planner.models import Scenario

    fields: dict[str, Any] = {
        "horizon_months": 6,
        "growth_pct": 0,
        "delay_weeks": 0,
        "budget_gbp": 1000,
        "safety_months": 1.0,
        "method": "seasonal_naive",
    }
    return Scenario(**(fields | overrides))


def toy_data(
    *products: "Product", history: dict[str, list[int]] | None = None
) -> "PlannerData":
    from inventory_runout_planner.models import PlannerData

    return PlannerData(
        products=list(products),
        history=history or {p.stock_code: [60] * 24 for p in products},
        history_months=MONTHS,
    )


def toy_run(*products: "Product", **scenario_overrides: Any) -> "ScenarioResult":
    from inventory_runout_planner.planner import run

    return run(toy_data(*products), scenario(**scenario_overrides))


def real_data() -> "PlannerData":
    from inventory_runout_planner.data import load

    return load(DATA_DIR)


def of(result: "ScenarioResult", code: str) -> "ProductResult":
    return next(p for p in result.products if p.stock_code == code)


def row(r: "MonthRow") -> tuple[str, int, int, int, int, int, int]:
    return (r.month, r.opening, r.inbound, r.demand, r.shipped, r.unmet, r.closing)


def app() -> AppTest:
    return AppTest.from_file(str(REPO / "app.py"), default_timeout=30)


def kpis(at: AppTest) -> dict[str, str]:
    return {m.label: str(m.value) for m in at.metric}


def texts(node: Any) -> str:
    parts: list[str] = []
    for kind in (
        "title",
        "header",
        "subheader",
        "markdown",
        "caption",
        "text",
        "info",
        "warning",
        "error",
        "success",
        "latex",
        "code",
    ):
        parts += [str(e.value) for e in getattr(node, kind)]
    return html.unescape("\n".join(parts))
