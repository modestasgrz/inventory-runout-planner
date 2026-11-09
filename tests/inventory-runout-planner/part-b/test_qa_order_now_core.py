from pathlib import Path

import numpy as np
import pytest
from inventory_runout_planner.data import load
from inventory_runout_planner.models import PlannerData, Product, Scenario
from inventory_runout_planner.planner import lead_months, month_key, run
from inventory_runout_planner.presets import PRESETS

DEMAND = 60
DATA = Path(__file__).resolve().parents[3] / "data"
MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)


def stock_for_runout(index: int) -> int:
    """Flat demand of 60: stock 60 * (index - 1) + 30 first runs short in month `index`."""
    return DEMAND * (index - 1) + 30


def world(stocks_and_leads: list[tuple[int, int]]) -> PlannerData:
    products = [
        Product(
            stock_code=f"Q{i:04d}",
            description=f"QA PRODUCT {i}",
            group="Gifts & small goods",
            unit_cost=2.0,
            stock_on_hand=stock,
            lead_time_weeks=lead,
            moq=50,
            capacity=100_000,
            inbound_qty=0,
            inbound_weeks=0,
        )
        for i, (stock, lead) in enumerate(stocks_and_leads)
    ]
    return PlannerData(
        products=products,
        history={p.stock_code: [DEMAND] * 24 for p in products},
        history_months=MONTHS,
    )


def scen(**kw: float | str) -> Scenario:
    fields: dict[str, float | str] = {
        "horizon_months": 12,
        "growth_pct": 0,
        "delay_weeks": 0,
        "budget_gbp": 1000,
        "safety_months": 1.0,
        "method": "seasonal_naive",
    }
    return Scenario.model_validate(fields | kw)


def runout_index(months: list[str], runout: str | None) -> int | None:
    return months.index(runout) + 1 if runout else None


@pytest.mark.parametrize("lead_weeks", [0, 1, 4, 5, 9, 12])
def test_boundary_lead_plus_one_and_plus_two(lead_weeks: int) -> None:
    lead = lead_months(lead_weeks)
    data = world(
        [
            (stock_for_runout(lead + 1), lead_weeks),
            (stock_for_runout(lead + 2), lead_weeks),
            (stock_for_runout(max(1, lead)), lead_weeks),
        ]
    )
    res = run(data, scen())
    by_code = {p.stock_code: p for p in res.products}
    assert {p.lead_months for p in res.products} == {lead}
    at_boundary, past, early = (by_code[f"Q{i:04d}"] for i in range(3))
    assert at_boundary.order_now is True
    assert past.order_now is False
    assert early.order_now is True


def test_zero_stock_runs_out_month_one_is_order_now() -> None:
    res = run(world([(0, 0)]), scen())
    p = res.products[0]
    assert p.runout_month == month_key(1)
    assert p.order_now is True


def test_no_runout_is_not_order_now() -> None:
    res = run(world([(100_000, 12)]), scen())
    p = res.products[0]
    assert p.runout_month is None
    assert p.order_now is False
    assert res.kpis.products_at_risk == 0


def test_runout_exactly_after_horizon_is_not_order_now() -> None:
    data = world([(stock_for_runout(7), 12)])
    res = run(data, scen(horizon_months=6))
    assert res.products[0].runout_month is None
    assert res.products[0].order_now is False


@pytest.mark.parametrize(
    ("horizon", "expected"), [(6, False), (7, False), (8, True), (12, True)]
)
def test_horizon_changes_order_now_when_runout_beyond_short_horizon(
    horizon: int, expected: bool
) -> None:
    # runout index 8; lead 12 weeks = 3 months -> threshold 4, so use delay 26 -> 9 months, threshold 10
    data = world([(stock_for_runout(8), 12)])
    res = run(data, scen(horizon_months=horizon, delay_weeks=26))
    p = res.products[0]
    assert p.lead_months == lead_months(38)
    assert (p.runout_month is not None) is expected
    assert p.order_now is expected


@pytest.mark.parametrize("horizon", [6, 12])
def test_flag_is_same_for_same_runout_regardless_of_horizon(horizon: int) -> None:
    data = world([(stock_for_runout(3), 4)])
    p = run(data, scen(horizon_months=horizon)).products[0]
    assert p.runout_month == month_key(3)
    assert p.lead_months == 1
    assert p.order_now is False


@pytest.mark.parametrize("delay", range(27))
def test_delay_changes_lead_months_and_flag(delay: int) -> None:
    lead_w = 4
    data = world([(stock_for_runout(4), lead_w)])
    p = run(data, scen(delay_weeks=delay)).products[0]
    lead = lead_months(lead_w + delay)
    assert p.lead_months == lead
    assert p.order_now is (4 <= lead + 1)


def test_delay_flips_flag_exactly_at_threshold() -> None:
    data = world([(stock_for_runout(3), 4)])
    flags = {d: run(data, scen(delay_weeks=d)).products[0].order_now for d in range(27)}
    first_true = min(d for d, v in flags.items() if v)
    assert not any(flags[d] for d in range(first_true))
    assert all(flags[d] for d in range(first_true, 27))
    assert lead_months(4 + first_true) + 1 >= 3 > lead_months(4 + first_true - 1) + 1


def test_growth_pulls_runout_earlier_and_flips_flag() -> None:
    data = world([(stock_for_runout(3), 4)])
    assert run(data, scen()).products[0].order_now is False
    assert run(data, scen(growth_pct=100)).products[0].order_now is True


@pytest.mark.parametrize("seed", range(8))
def test_random_worlds_flag_matches_definition_and_kpi_matches_count(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 15))
    specs = [(int(rng.integers(0, 1500)), int(rng.integers(0, 13))) for _ in range(n)]
    data = world(specs)
    s = scen(
        horizon_months=int(rng.integers(6, 13)),
        growth_pct=float(rng.integers(-50, 101)),
        delay_weeks=int(rng.integers(0, 27)),
        safety_months=float(rng.integers(0, 7)),
        budget_gbp=float(rng.integers(0, 5000)),
        method=str(rng.choice(["seasonal_naive", "trailing_3m"])),
    )
    res = run(data, s)
    months = [month_key(t) for t in range(1, 13)]
    for p in res.products:
        idx = runout_index(months, p.runout_month)
        assert p.order_now is (idx is not None and idx <= p.lead_months + 1)
    assert res.kpis.products_at_risk == sum(p.order_now for p in res.products)


@pytest.mark.parametrize("name", list(PRESETS))
def test_real_data_every_preset_kpi_equals_count(name: str) -> None:
    res = run(load(DATA), PRESETS[name])
    months = [month_key(t) for t in range(1, 13)]
    assert res.kpis.products_at_risk == sum(p.order_now for p in res.products)
    for p in res.products:
        idx = runout_index(months, p.runout_month)
        assert p.order_now is (idx is not None and idx <= p.lead_months + 1)
