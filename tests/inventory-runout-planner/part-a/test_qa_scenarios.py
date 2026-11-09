import itertools
import random

import pytest
from inventory_runout_planner.models import (
    PlannerData,
    Product,
    Scenario,
    ScenarioResult,
    scenario_errors,
)
from inventory_runout_planner.planner import lead_months, run
from pydantic import ValidationError

MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)


def prod(code: str = "T1", **kw: float) -> Product:
    f: dict[str, int | float | str] = {
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
    return Product.model_validate(f | kw)


def sc(**kw: float | str) -> Scenario:
    f: dict[str, float | str] = {
        "horizon_months": 6,
        "growth_pct": 0,
        "delay_weeks": 0,
        "budget_gbp": 1000,
        "safety_months": 1.0,
        "method": "seasonal_naive",
    }
    return Scenario.model_validate(f | kw)


def go(*products: Product, demand: int = 60, **kw: float | str) -> ScenarioResult:
    data = PlannerData(
        products=list(products),
        history={p.stock_code: [demand] * 24 for p in products},
        history_months=MONTHS,
    )
    return run(data, sc(**kw))


def test_scenario_model_bounds_exact() -> None:
    sc(horizon_months=6, growth_pct=-50, delay_weeks=0, budget_gbp=0, safety_months=0)
    sc(
        horizon_months=12,
        growth_pct=100,
        delay_weeks=26,
        budget_gbp=1_000_000,
        safety_months=6,
    )
    for bad in (
        {"horizon_months": 5},
        {"horizon_months": 13},
        {"growth_pct": -50.01},
        {"growth_pct": 100.01},
        {"delay_weeks": -1},
        {"delay_weeks": 27},
        {"budget_gbp": -0.01},
        {"budget_gbp": 1_000_000.01},
        {"safety_months": -0.01},
        {"safety_months": 6.01},
        {"method": "ets"},
    ):
        with pytest.raises(ValidationError):
            sc(**bad)


def test_scenario_errors_exact_boundaries_pass() -> None:
    lows: dict[str, float | int | str] = {
        "growth_pct": -50,
        "delay_weeks": 0,
        "budget_gbp": 0,
        "safety_months": 0,
    }
    highs: dict[str, float | int | str] = {
        "growth_pct": 100,
        "delay_weeks": 26,
        "budget_gbp": 1_000_000,
        "safety_months": 6,
    }
    assert scenario_errors(lows) == []
    assert scenario_errors(highs) == []
    assert scenario_errors({**highs, "delay_weeks": 26.0}) == []


@pytest.mark.parametrize(
    ("key", "value", "text"),
    [
        (
            "growth_pct",
            -50.5,
            "Demand growth (%) must be between -50 and 100 — you entered -50.5.",
        ),
        (
            "growth_pct",
            101,
            "Demand growth (%) must be between -50 and 100 — you entered 101.",
        ),
        (
            "delay_weeks",
            27,
            "Supplier delay (weeks) must be between 0 and 26 — you entered 27.",
        ),
        (
            "delay_weeks",
            2.5,
            "Supplier delay (weeks) must be between 0 and 26 — you entered 2.5.",
        ),
        (
            "delay_weeks",
            -1,
            "Supplier delay (weeks) must be between 0 and 26 — you entered -1.",
        ),
        (
            "budget_gbp",
            1_000_001,
            "Budget (£) must be between 0 and 1 000 000 — you entered 1e+06.",
        ),
        (
            "budget_gbp",
            -0.5,
            "Budget (£) must be between 0 and 1 000 000 — you entered -0.5.",
        ),
        (
            "safety_months",
            6.5,
            "Safety stock (months) must be between 0 and 6 — you entered 6.5.",
        ),
        (
            "safety_months",
            -0.1,
            "Safety stock (months) must be between 0 and 6 — you entered -0.1.",
        ),
    ],
)
def test_scenario_errors_single_field(key: str, value: float, text: str) -> None:
    raw: dict[str, float | int | str] = {
        "growth_pct": 0,
        "delay_weeks": 0,
        "budget_gbp": 1000,
        "safety_months": 1,
    }
    raw[key] = value
    assert scenario_errors(raw) == [text]


def test_scenario_errors_nan_and_inf_are_errors() -> None:
    raw: dict[str, float | int | str] = {
        "growth_pct": float("nan"),
        "delay_weeks": float("inf"),
        "budget_gbp": float("-inf"),
        "safety_months": 1,
    }
    assert len(scenario_errors(raw)) == 3


def test_scenario_errors_numeric_strings_and_extra_keys() -> None:
    raw: dict[str, float | int | str] = {
        "growth_pct": "10",
        "delay_weeks": "3",
        "budget_gbp": "500",
        "safety_months": "1",
        "horizon_months": 12,
        "method": "seasonal_naive",
    }
    assert scenario_errors(raw) == []


@pytest.mark.parametrize("seed", range(30))
def test_scenario_errors_agree_with_model(seed: int) -> None:
    rng = random.Random(seed)
    raw: dict[str, float | int | str] = {
        "growth_pct": rng.choice([-51, -50, 0, 100, 101, rng.uniform(-60, 110)]),
        "delay_weeks": rng.choice([-1, 0, 26, 27, rng.randint(-3, 30)]),
        "budget_gbp": rng.choice([-1, 0, 1_000_000, 1_000_001, rng.uniform(-5, 2e6)]),
        "safety_months": rng.choice([-1, 0, 6, 7, rng.uniform(-1, 8)]),
    }
    errors = scenario_errors(raw)
    try:
        Scenario.model_validate(
            raw | {"horizon_months": 12, "method": "seasonal_naive"}
        )
        valid = True
    except ValidationError:
        valid = False
    assert (errors == []) == valid


@pytest.mark.parametrize(
    ("horizon", "growth", "delay", "safety", "method"),
    list(
        itertools.product(
            [6, 12], [-50, 100], [0, 26], [0, 6], ["seasonal_naive", "trailing_3m"]
        )
    ),
)
def test_every_corner_runs_clean(
    horizon: int, growth: float, delay: int, safety: float, method: str
) -> None:
    products = [
        prod("A"),
        prod(
            "B", stock_on_hand=0, lead_time_weeks=12, inbound_qty=300, inbound_weeks=12
        ),
        prod("C", stock_on_hand=5000, capacity=9000),
        prod("D", moq=500, capacity=400),
    ]
    r = go(
        *products,
        horizon_months=horizon,
        growth_pct=growth,
        delay_weeks=delay,
        safety_months=safety,
        method=method,
        budget_gbp=500,
    )
    assert all(len(p.months) == horizon for p in r.products)
    assert r.kpis.funded_spend_gbp <= 500
    for line in r.plan:
        p = next(x for x in products if x.stock_code == line.stock_code)
        assert p.moq <= line.qty


def test_horizon_does_not_change_shared_prefix() -> None:
    a = go(prod(), horizon_months=6).products[0]
    b = go(prod(), horizon_months=12).products[0]
    assert a.months == b.months[:6]
    assert a.runout_month == b.runout_month


def test_hand_safety_zero() -> None:
    p = go(prod(), safety_months=0).products[0]
    assert p.runout_month == "2012-01"
    assert p.order is not None
    assert (p.order.order_month, p.order.arrival_month, p.order.qty) == (
        "2011-12",
        "2012-01",
        140,
    )
    assert p.order.cost_gbp == 280.0
    assert p.limiting_factor == "stock"


def test_hand_safety_six_is_capacity_clipped() -> None:
    p = go(prod(), safety_months=6).products[0]
    assert p.order is not None
    assert p.order.qty == 360  # room 400 - 40; need 180+360-40=500
    assert p.order.cost_gbp == 720.0
    assert p.order.funded


def test_hand_max_delay_arrives_after_horizon() -> None:
    p = go(prod(), delay_weeks=26).products[0]
    assert p.lead_months == 7
    assert p.order is not None
    assert (p.order.order_month, p.order.arrival_month, p.order.qty) == (
        "2011-12",
        "2012-07",
        240,
    )
    assert p.limiting_factor == "lead time"
    assert p.order.funded
    assert p.plan_months == p.months


def test_hand_zero_lead_time_arrives_same_month() -> None:
    p = go(prod(lead_time_weeks=0)).products[0]
    assert p.lead_months == 0
    assert p.order is not None
    assert (p.order.order_month, p.order.arrival_month, p.order.qty) == (
        "2011-12",
        "2011-12",
        140,
    )
    assert p.limiting_factor == "stock"
    assert p.plan_months[0].inbound == 140
    assert p.plan_months[0].closing == 100 + 140 - 60


def test_hand_negative_growth_trailing() -> None:
    p = go(prod(), growth_pct=-50, method="trailing_3m").products[0]
    assert [r.demand for r in p.months] == [30] * 6
    assert [r.closing for r in p.months[:3]] == [70, 40, 10]
    assert p.runout_month == "2012-03"
    assert p.value_at_risk_gbp == (20 + 30 + 30) * 2.0


def test_hand_growth_100_doubles_demand() -> None:
    p = go(prod(), growth_pct=100).products[0]
    assert [r.demand for r in p.months] == [120] * 6
    assert p.runout_month == "2011-12"
    assert p.months[0].unmet == 20


def test_hand_zero_demand_product_never_orders() -> None:
    r = go(prod(stock_on_hand=0), demand=0)
    p = r.products[0]
    assert p.runout_month is None
    assert p.order is None
    assert p.limiting_factor == "none"
    assert r.kpis.products_at_risk == 0
    assert r.kpis.earliest_runout_code is None
    assert r.kpis.earliest_limiting_factor is None


def test_hand_inbound_at_horizon_edge() -> None:
    # inbound_weeks=26 -> 1 + ceil(182/30.44)=1+6=7 > horizon 6 -> flagged, not delivered
    p = go(prod(inbound_qty=500, inbound_weeks=26)).products[0]
    assert p.inbound_month == "2012-06"
    assert "Inbound arrives after horizon" in p.flags
    # inbound_weeks=21 -> 1 + ceil(147/30.44)=1+5=6 -> in horizon
    q = go(prod(inbound_qty=500, inbound_weeks=21)).products[0]
    assert q.inbound_month == "2012-05"
    assert "Inbound arrives after horizon" not in q.flags


def test_hand_zero_budget_funds_nothing_and_ties_rank_by_code() -> None:
    r = go(prod("B"), prod("A"), budget_gbp=0)
    assert [line.stock_code for line in r.plan] == ["A", "B"]
    assert not any(line.funded for line in r.plan)
    assert r.kpis.funded_spend_gbp == 0
    assert all(line.limiting_factor == "budget" for line in r.plan)


def test_budget_exactly_equal_to_cost_is_funded() -> None:
    r = go(prod(), budget_gbp=400)
    assert r.plan[0].funded
    assert r.kpis.funded_spend_gbp == 400


def test_budget_one_penny_short_is_not_funded() -> None:
    r = go(prod(), budget_gbp=399.99)
    assert not r.plan[0].funded
    assert "Not funded: £399.99 left of budget." in r.plan[0].reason


def test_greedy_skips_big_order_and_funds_later_small_one() -> None:
    big = prod("A", unit_cost=10.0)
    small = prod("B", unit_cost=1.0)
    r = go(big, small, budget_gbp=250)
    assert [(x.stock_code, x.funded) for x in r.plan] == [("A", False), ("B", True)]


def test_rank_prefers_earlier_runout_then_value_at_risk() -> None:
    soon = prod("Z", stock_on_hand=10)
    later = prod("A", stock_on_hand=100)
    r = go(later, soon)
    assert [x.stock_code for x in r.plan] == ["Z", "A"]
    cheap = prod("A", stock_on_hand=100, unit_cost=1.0)
    dear = prod("B", stock_on_hand=100, unit_cost=5.0)
    r2 = go(cheap, dear)
    assert [x.stock_code for x in r2.plan] == ["B", "A"]


def test_lead_months_table() -> None:
    cases = {0: 0, 1: 1, 4: 1, 5: 2, 8: 2, 9: 3, 13: 3, 14: 4, 38: 9}
    for weeks, months in cases.items():
        assert lead_months(weeks) == months, weeks
