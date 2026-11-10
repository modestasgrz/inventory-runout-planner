import math
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from inventory_runout_planner.data import DataError, load
from inventory_runout_planner.fmt import month, units
from inventory_runout_planner.models import (
    Method,
    PlannerData,
    Product,
    ProductResult,
    Scenario,
    ScenarioResult,
)
from inventory_runout_planner.planner import backtest, lead_months, month_key, run
from inventory_runout_planner.presets import BASELINE, PRESETS

DATA = Path(__file__).resolve().parents[3] / "data"
MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)
METHODS: list[Method] = ["seasonal_naive", "trailing_3m"]


def toy(code: str, **overrides: Any) -> Product:
    fields: dict[str, Any] = {
        "stock_code": code,
        "description": f"TOY {code}",
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


def toy_scenario(**overrides: Any) -> Scenario:
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
    *products: Product,
    history: dict[str, list[int]] | None = None,
    prices: dict[str, float] | None = None,
) -> PlannerData:
    return PlannerData(
        products=list(products),
        history=history or {p.stock_code: [60] * 24 for p in products},
        history_months=MONTHS,
        prices=prices or {p.stock_code: 5.00 for p in products},
    )


def one(p: Product, **scenario_overrides: Any) -> ProductResult:
    return run(toy_data(p), toy_scenario(**scenario_overrides)).products[0]


def of(result: ScenarioResult, code: str) -> ProductResult:
    return next(p for p in result.products if p.stock_code == code)


# ---------- hand-calculated edge cases ----------


def test_arrival_after_horizon_keeps_whole_horizon_in_window() -> None:
    """lead 12 w + delay 26 w = 9 months; order month 1 arrives month 10 > H=6, so e = H."""
    assert lead_months(38) == 9
    p = one(toy("A1", lead_time_weeks=12), delay_weeks=26)
    assert p.limiting_factor == "lead time"
    assert p.order is not None and p.order.funded
    assert p.order.arrival_month == "2012-09"
    assert p.plan_months == p.months
    assert p.lost_sales_gbp == 1300.00
    assert p.lost_sales_after_plan_gbp == 1300.00
    assert p.later_shortfall_units == 0
    assert p.later_shortfall_month is None
    assert p.later_shortfall_gbp == 0.00
    assert p.stockout_months == 5
    assert p.at_risk_after_plan
    assert p.stockout is not None
    assert (p.stockout.start_month, p.stockout.end_month) == ("2012-01", "2012-05")
    assert (p.stockout.months, p.stockout.units) == (5, 260)
    assert p.stockout.lost_sales_gbp == 1300.00
    assert not any(f.startswith("Later shortfall") for f in p.flags)


def test_lead_time_arrival_inside_12_month_horizon() -> None:
    """Same product at H=12: arrival month 10 (Sep 2012) ≤ H, e = min(12, 12)."""
    p = one(toy("A1", lead_time_weeks=12), delay_weeks=26, horizon_months=12)
    assert p.order is not None and p.order.funded and p.order.qty == 240
    assert p.lost_sales_gbp == 3100.00
    assert p.lost_sales_after_plan_gbp == 2200.00
    assert p.stockout_months == 8
    assert p.later_shortfall_units == 0
    assert p.stockout is not None
    assert (p.stockout.start_month, p.stockout.end_month) == ("2012-01", "2012-08")
    assert (p.stockout.months, p.stockout.units) == (8, 440)
    assert p.stockout.lost_sales_gbp == 2200.00


def test_unfunded_order_window_is_whole_horizon() -> None:
    r = run(toy_data(toy("T0001")), toy_scenario(budget_gbp=300))
    p = r.products[0]
    assert p.limiting_factor == "budget"
    assert p.order is not None and not p.order.funded and p.order.cost_gbp == 400.00
    assert p.lost_sales_after_plan_gbp == p.lost_sales_gbp == 1300.00
    assert p.stockout_months == 5
    assert p.stockout is None
    assert p.later_shortfall_units == 0
    assert r.kpis.unfunded_gbp == 400.00
    assert r.kpis.unfunded_orders == 1
    assert r.kpis.products_at_risk == 1


def test_budget_exactly_equal_to_cost_funds_order() -> None:
    p = one(toy("T0001"), budget_gbp=400)
    assert p.order is not None and p.order.funded
    assert p.lost_sales_after_plan_gbp == 0.00
    assert not p.at_risk_after_plan


def test_zero_budget_unfunded_gbp_is_total_suggested() -> None:
    r = run(
        toy_data(toy("T0001"), toy("T0002", lead_time_weeks=10)),
        toy_scenario(budget_gbp=0),
    )
    assert r.kpis.funded_spend_gbp == 0.00
    assert r.kpis.unfunded_gbp == r.kpis.suggested_spend_gbp > 0
    assert r.kpis.lost_sales_after_plan_gbp == r.kpis.lost_sales_gbp


def test_capacity_blocked_has_no_order_and_full_window() -> None:
    """room = 50 − 40 = 10 < MOQ 50."""
    r = run(toy_data(toy("C1", capacity=50)), toy_scenario())
    p = r.products[0]
    assert p.limiting_factor == "capacity"
    assert p.order is None
    assert "Capacity blocks order: room 10 < MOQ 50" in p.flags
    assert p.lost_sales_after_plan_gbp == 1300.00
    assert p.stockout_months == 5
    assert p.stockout is None
    assert p.later_shortfall_units == 0
    assert r.kpis.unfunded_gbp == 0.00
    assert r.kpis.unfunded_orders == 0


def test_one_month_stockout() -> None:
    """lead 5 weeks = 2 months: run-out Jan 2012, arrival Feb 2012, gap = Jan only."""
    assert lead_months(5) == 2
    p = one(toy("S1", lead_time_weeks=5))
    assert p.limiting_factor == "lead time"
    assert p.order is not None and p.order.arrival_month == "2012-02"
    assert p.stockout is not None
    assert p.stockout.start_month == p.stockout.end_month == "2012-01"
    assert (p.stockout.months, p.stockout.units) == (1, 20)
    assert p.stockout.lost_sales_gbp == 100.00
    assert p.stockout_months == 1
    assert p.at_risk_after_plan
    assert p.lost_sales_after_plan_gbp == 100.00
    assert p.later_shortfall_units == 0


def test_one_month_stockout_at_12_months_has_later_shortfall() -> None:
    """e = min(12, 3 + 2) = 5; with-plan unmet Jun–Nov 2012 = 6 × 60."""
    p = one(toy("S1", lead_time_weeks=5), horizon_months=12)
    assert p.lost_sales_after_plan_gbp == 100.00
    assert p.stockout_months == 1
    assert p.later_shortfall_units == 360
    assert p.later_shortfall_month == "2012-06"
    assert p.later_shortfall_gbp == 1800.00
    assert f"Later shortfall not covered: {units(360)} from Jun 2012" in p.flags


def test_delay_preset_style_turns_stock_into_lead_time() -> None:
    """Supplier delay +3 weeks: 4 + 3 = 7 weeks = 2 months for T0001."""
    p = one(toy("T0001"), delay_weeks=3)
    assert p.lead_months == 2
    assert p.limiting_factor == "lead time"
    assert p.stockout is not None and p.stockout.units == 20
    assert p.lost_sales_after_plan_gbp == 100.00


def test_growth_preset_style_hand_case() -> None:
    """Growth 25 %: demand 75; qty 275 arrives Jan 2012, e = 4; May 2012 short 75."""
    p = one(toy("T0001"), growth_pct=25)
    assert p.lost_sales_gbp == 1750.00
    assert p.order is not None and p.order.qty == 275 and p.order.funded
    assert p.lost_sales_after_plan_gbp == 0.00
    assert p.later_shortfall_units == 75
    assert p.later_shortfall_month == "2012-05"
    assert p.later_shortfall_gbp == 375.00
    assert not p.at_risk_after_plan


@pytest.mark.parametrize(
    ("horizon", "lost", "later_units", "later_gbp"),
    [(6, 1300.00, 60, 300.00), (12, 3100.00, 420, 2100.00)],
)
def test_horizon_6_vs_12(
    horizon: int, lost: float, later_units: int, later_gbp: float
) -> None:
    p = one(toy("T0001"), horizon_months=horizon)
    assert p.lost_sales_gbp == lost
    assert p.lost_sales_after_plan_gbp == 0.00
    assert p.later_shortfall_units == later_units
    assert p.later_shortfall_month == "2012-05"
    assert p.later_shortfall_gbp == later_gbp


def test_zero_demand_overstock_ties_up_all_stock() -> None:
    r = run(
        toy_data(toy("Z1", stock_on_hand=500), history={"Z1": [0] * 24}),
        toy_scenario(),
    )
    p = r.products[0]
    assert "Overstocked: no forecast demand" in p.flags
    assert p.tied_up_gbp == 1000.00
    assert p.lost_sales_gbp == p.lost_sales_after_plan_gbp == 0.00
    assert not p.at_risk_after_plan
    assert r.kpis.tied_up_gbp == 1000.00


def test_zero_demand_zero_stock_ties_up_nothing() -> None:
    p = run(
        toy_data(toy("Z0", stock_on_hand=0), history={"Z0": [0] * 24}),
        toy_scenario(),
    ).products[0]
    assert not any(f.startswith("Overstocked") for f in p.flags)
    assert p.tied_up_gbp == 0.00
    assert p.stockout_months == 0


@pytest.mark.parametrize(
    ("stock", "tied"), [(360, 0.00), (361, 2.00), (1000, 1280.00), (0, 0.00)]
)
def test_tied_up_boundary_at_six_months_cover(stock: int, tied: float) -> None:
    """Cover exactly 6.0 is not overstocked (> 6.0); one unit more is."""
    p = one(toy("O1", stock_on_hand=stock))
    assert p.tied_up_gbp == tied
    assert any(f.startswith("Overstocked") for f in p.flags) == (stock > 360)


def test_tied_up_rounds_half_up_not_bankers() -> None:
    """H=12, Σ forecast = 5: 6 × 5 / 12 = 2.5 → 3 (half up), excess 97 × £2."""
    history = [0] * 12 + [1] * 5 + [0] * 7
    p = run(
        toy_data(toy("R1", stock_on_hand=100), history={"R1": history}),
        toy_scenario(horizon_months=12),
    ).products[0]
    assert sum(r.demand for r in p.months) == 5
    assert p.tied_up_gbp == 194.00


def test_tied_up_uses_unit_cost_not_sell_price() -> None:
    p = run(
        toy_data(toy("U1", stock_on_hand=1000, unit_cost=0.37), prices={"U1": 9.99}),
        toy_scenario(),
    ).products[0]
    assert p.tied_up_gbp == round(640 * 0.37, 2)
    assert p.sell_price == 9.99


def test_lost_sales_use_sell_price_with_pennies() -> None:
    p = run(toy_data(toy("P1"), prices={"P1": 0.85}), toy_scenario()).products[0]
    assert p.sell_price == 0.85
    assert p.lost_sales_gbp == round(260 * 0.85, 2) == 221.00
    assert p.later_shortfall_gbp == round(60 * 0.85, 2) == 51.00


def test_inbound_inside_stockout_gap_counts_only_unmet() -> None:
    """Inbound 60 in Feb 2012 fills one gap month; stockout still spans run-out..arrival − 1."""
    p = one(
        toy("G1", lead_time_weeks=12, inbound_qty=60, inbound_weeks=8),
        horizon_months=12,
    )
    assert p.limiting_factor == "lead time"
    assert p.stockout is not None
    gap = [
        r for r in p.months if p.stockout.start_month <= r.month <= p.stockout.end_month
    ]
    assert p.stockout.months == len(gap)
    assert p.stockout.units == sum(r.unmet for r in gap)


# ---------- property checks ----------


def ri(rng: np.random.Generator, low: int, high: int) -> int:
    return int(rng.integers(low, high + 1))


def pick[T](rng: np.random.Generator, options: list[T]) -> T:
    return options[int(rng.integers(len(options)))]


def world(seed: int) -> tuple[PlannerData, Scenario]:
    rng = np.random.default_rng(1000 + seed)
    products = []
    for i in range(ri(rng, 1, 8)):
        inbound = pick(rng, [0, 0, ri(rng, 1, 1500)])
        products.append(
            Product(
                stock_code=f"Q{i:03d}",
                description=f"Toy {i}",
                group="Gifts & small goods",
                unit_cost=round(float(rng.uniform(0.01, 40)), 2),
                stock_on_hand=pick(rng, [0, 1, ri(rng, 0, 3000)]),
                lead_time_weeks=ri(rng, 0, 12),
                moq=pick(rng, [1, 50, ri(rng, 1, 400)]),
                capacity=pick(rng, [1, ri(rng, 1, 3000), 5000]),
                inbound_qty=inbound,
                inbound_weeks=ri(rng, 0, 30) if inbound else 0,
            )
        )
    history = {
        p.stock_code: pick(
            rng,
            [
                [0] * 24,
                [ri(rng, 1, 300)] * 24,
                [pick(rng, [0, 0, ri(rng, 1, 800)]) for _ in range(24)],
                [ri(rng, 0, 600) for _ in range(24)],
            ],
        )
        for p in products
    }
    prices = {p.stock_code: round(float(rng.uniform(0.01, 50)), 2) for p in products}
    scenario = Scenario(
        horizon_months=ri(rng, 6, 12),
        growth_pct=pick(rng, [-50, 0, 100, ri(rng, -50, 100), 12.5]),
        delay_weeks=pick(rng, [0, 26, ri(rng, 0, 26)]),
        budget_gbp=pick(rng, [0, 1_000_000, ri(rng, 0, 20000)]),
        safety_months=pick(rng, [0, 6, 0.5, 1, ri(rng, 0, 12) / 2]),
        method=pick(rng, ["seasonal_naive", "trailing_3m"]),
    )
    return (
        PlannerData(
            products=products, history=history, history_months=MONTHS, prices=prices
        ),
        scenario,
    )


def month_index(key: str) -> int:
    y, m = key.split("-")
    return int(y) * 12 + int(m) - 1 - (2011 * 12 + 11) + 1


def check_dec19(data: PlannerData, result: ScenarioResult) -> None:
    horizon = result.scenario.horizon_months
    by_code = {p.stock_code: p for p in data.products}
    for pr in result.products:
        p = by_code[pr.stock_code]
        price = data.prices[p.stock_code]
        assert pr.sell_price == price
        order = pr.order
        arrival = month_index(order.arrival_month) if order else None
        funded_in = order is not None and order.funded and arrival is not None
        e = (
            min(horizon, arrival + 2)
            if funded_in and arrival is not None and arrival <= horizon
            else horizon
        )
        window, later = pr.plan_months[:e], pr.plan_months[e:]
        do_nothing_unmet = sum(r.unmet for r in pr.months)
        plan_unmet = sum(r.unmet for r in pr.plan_months)
        assert pr.lost_sales_gbp == round(do_nothing_unmet * price, 2)
        assert pr.lost_sales_after_plan_gbp == round(
            sum(r.unmet for r in window) * price, 2
        )
        assert pr.stockout_months == sum(r.unmet > 0 for r in window)
        assert pr.at_risk_after_plan == (pr.stockout_months > 0)
        assert pr.later_shortfall_units == sum(r.unmet for r in later)
        assert sum(r.unmet for r in window) + pr.later_shortfall_units == plan_unmet
        assert pr.later_shortfall_month == next(
            (r.month for r in later if r.unmet > 0), None
        )
        assert pr.later_shortfall_gbp == round(pr.later_shortfall_units * price, 2)
        later_flags = [f for f in pr.flags if f.startswith("Later shortfall")]
        if pr.later_shortfall_units:
            assert pr.later_shortfall_month is not None
            text = units(pr.later_shortfall_units)
            when = month(pr.later_shortfall_month)
            assert later_flags == [f"Later shortfall not covered: {text} from {when}"]
        else:
            assert later_flags == []
            assert pr.later_shortfall_month is None
        # with-plan unmet never exceeds do-nothing month by month, so window ⊆ 1..H bounds it
        for a, b in zip(pr.plan_months, pr.months, strict=True):
            assert a.unmet <= b.unmet
        assert pr.lost_sales_after_plan_gbp <= pr.lost_sales_gbp
        assert (
            pr.lost_sales_after_plan_gbp + pr.later_shortfall_gbp
            <= pr.lost_sales_gbp + 0.011
        )
        if pr.limiting_factor == "lead time":
            assert pr.stockout is not None and pr.runout_month is not None
            start = month_index(pr.runout_month)
            arrives = arrival is not None and pr.order is not None and pr.order.funded
            end = min(arrival - 1, horizon) if arrival and arrives else horizon
            assert start <= end <= horizon
            gap = pr.months[start - 1 : end]
            assert pr.stockout.start_month == pr.runout_month == month_key(start)
            assert pr.stockout.end_month == month_key(end)
            assert pr.stockout.months == len(gap) == end - start + 1
            assert pr.stockout.units == sum(r.unmet for r in gap)
            assert pr.stockout.lost_sales_gbp == round(pr.stockout.units * price, 2)
        else:
            assert pr.stockout is None
        overstocked = any(f.startswith("Overstocked") for f in pr.flags)
        if overstocked:
            normal = math.floor(
                Fraction(6 * sum(r.demand for r in pr.months), horizon) + Fraction(1, 2)
            )
            assert pr.tied_up_gbp == round(
                max(p.stock_on_hand - normal, 0) * p.unit_cost, 2
            )
        else:
            assert pr.tied_up_gbp == 0.0
        assert pr.tied_up_gbp >= 0
    k = result.kpis
    prods = result.products
    assert k.products_at_risk == sum(p.at_risk_after_plan for p in prods)
    assert k.stockout_months == sum(p.stockout_months for p in prods)
    assert k.lost_sales_gbp == round(sum(p.lost_sales_gbp for p in prods), 2)
    assert k.lost_sales_after_plan_gbp == round(
        sum(p.lost_sales_after_plan_gbp for p in prods), 2
    )
    assert k.later_shortfall_gbp == round(sum(p.later_shortfall_gbp for p in prods), 2)
    assert k.tied_up_gbp == round(sum(p.tied_up_gbp for p in prods), 2)
    assert k.unfunded_gbp == round(
        sum(line.cost_gbp for line in result.plan if not line.funded), 2
    )
    assert k.unfunded_gbp == pytest.approx(
        k.suggested_spend_gbp - k.funded_spend_gbp, abs=0.011
    )


@pytest.mark.parametrize("seed", list(range(60)))
def test_random_worlds_follow_dec19(seed: int) -> None:
    data, scenario = world(seed)
    check_dec19(data, run(data, scenario))


@pytest.mark.parametrize("seed", list(range(10)))
def test_repeat_run_is_identical(seed: int) -> None:
    data, scenario = world(seed)
    assert run(data, scenario) == run(data, scenario)


@pytest.mark.parametrize("seed", list(range(20)))
def test_money_scales_with_sell_price(seed: int) -> None:
    """Doubling every price doubles all lost-sales money and leaves units, plan and £ tied up alone."""
    data, scenario = world(seed)
    doubled = data.model_copy(
        update={"prices": {c: v * 2 for c, v in data.prices.items()}}
    )
    a, b = run(data, scenario), run(doubled, scenario)
    assert a.plan == b.plan
    for x, y in zip(a.products, b.products, strict=True):
        assert y.lost_sales_gbp == pytest.approx(2 * x.lost_sales_gbp, abs=0.011)
        assert y.lost_sales_after_plan_gbp == pytest.approx(
            2 * x.lost_sales_after_plan_gbp, abs=0.011
        )
        assert y.later_shortfall_units == x.later_shortfall_units
        assert y.tied_up_gbp == x.tied_up_gbp
        assert y.at_risk_after_plan == x.at_risk_after_plan


# ---------- backtest ----------


def test_backtest_hand_case_seasonal_and_trailing() -> None:
    """First 12 months 1..12, actual 12 × 10. Seasonal forecast = 1..12; trailing = mean(10, 11, 12) = 11."""
    history = list(range(1, 13)) + [10] * 12
    data = toy_data(toy("K1"), history={"K1": history})
    seasonal = backtest(data, "seasonal_naive")
    assert seasonal.as_of == "2010-12"
    row = seasonal.rows[0]
    errors = [abs(10 - f) for f in range(1, 13)]
    assert row.abs_error_units == sum(errors) == 48
    assert row.actual_units == 120
    assert row.mape_pct == pytest.approx(sum(errors) / 12 / 10 * 100)
    assert seasonal.overall_pct == 40.00
    trailing = backtest(data, "trailing_3m")
    assert trailing.rows[0].abs_error_units == 12
    assert trailing.rows[0].mape_pct == pytest.approx(10.0)
    assert trailing.overall_pct == 10.00


def test_backtest_trailing_rounds_half_up_mean() -> None:
    """Sep–Nov 2010 = 1, 2, 2 → 5/3 → 2; actual 2 → zero error."""
    history = [0] * 9 + [1, 2, 2] + [2] * 12
    data = toy_data(toy("K2"), history={"K2": history})
    assert backtest(data, "trailing_3m").rows[0].abs_error_units == 0


def test_backtest_all_zero_actual_gives_none_mape() -> None:
    data = toy_data(
        toy("K3"),
        toy("K4"),
        history={"K3": [5] * 12 + [0] * 12, "K4": [10] * 24},
    )
    for method in METHODS:
        bt = backtest(data, method)
        k3 = next(r for r in bt.rows if r.stock_code == "K3")
        assert k3.mape_pct is None
        assert k3.abs_error_units == 60
        assert k3.actual_units == 0
        assert bt.overall_pct == 50.00


def test_backtest_ignores_scenario_growth_and_last_history_only_as_actual() -> None:
    """Changing months 13–24 changes only the actuals; forecast comes from months 1–12."""
    base = [7] * 12
    a = toy_data(toy("K5"), history={"K5": base + [7] * 12})
    b = toy_data(toy("K5"), history={"K5": base + [14] * 12})
    for method in METHODS:
        assert backtest(a, method).rows[0].abs_error_units == 0
        assert backtest(b, method).rows[0].abs_error_units == 84
        assert backtest(b, method).rows[0].mape_pct == pytest.approx(50.0)


@pytest.mark.parametrize("seed", list(range(20)))
def test_backtest_random_properties(seed: int) -> None:
    data, _ = world(seed)
    for method in METHODS:
        bt = backtest(data, method)
        assert [r.stock_code for r in bt.rows] == [p.stock_code for p in data.products]
        for r in bt.rows:
            actual = data.history[r.stock_code][12:]
            assert r.actual_units == sum(actual)
            assert (r.mape_pct is None) == (not any(actual))
            assert r.abs_error_units >= 0
            if r.mape_pct is not None:
                assert r.mape_pct >= 0
        total = sum(r.actual_units for r in bt.rows)
        if total:
            assert bt.overall_pct == round(
                sum(r.abs_error_units for r in bt.rows) / total * 100, 2
            )


# ---------- data.load: median_prices.csv ----------


def copy_data(tmp: Path) -> Path:
    for name in ("demand_monthly.csv", "products_synthetic.csv", "median_prices.csv"):
        shutil.copy(DATA / name, tmp / name)
    return tmp


def first_code() -> str:
    return (DATA / "median_prices.csv").read_text().splitlines()[1].split(",")[0]


def test_load_reads_prices_for_every_product() -> None:
    d = load(DATA)
    assert set(d.prices) >= {p.stock_code for p in d.products}
    assert all(d.prices[p.stock_code] > 0 for p in d.products)
    assert all(isinstance(c, str) for c in d.prices)


def test_load_missing_price_file(tmp_path: Path) -> None:
    copy_data(tmp_path)
    (tmp_path / "median_prices.csv").unlink()
    with pytest.raises(DataError, match="^Data file not found: median_prices.csv$"):
        load(tmp_path)


def test_load_price_file_is_a_directory(tmp_path: Path) -> None:
    copy_data(tmp_path)
    (tmp_path / "median_prices.csv").unlink()
    (tmp_path / "median_prices.csv").mkdir()
    with pytest.raises(DataError, match="median_prices.csv"):
        load(tmp_path)


def test_load_price_row_missing_for_one_product(tmp_path: Path) -> None:
    copy_data(tmp_path)
    path = tmp_path / "median_prices.csv"
    lines = path.read_text().splitlines()
    code = lines[1].split(",")[0]
    path.write_text("\n".join([lines[0], *lines[2:]]) + "\n")
    with pytest.raises(DataError, match=f"^median_prices.csv: no price for {code}$"):
        load(tmp_path)


@pytest.mark.parametrize("bad", ["0", "0.0", "-1.25", "", "abc", "nan", " "])
def test_load_bad_price_values(tmp_path: Path, bad: str) -> None:
    copy_data(tmp_path)
    path = tmp_path / "median_prices.csv"
    lines = path.read_text().splitlines()
    code = lines[1].split(",")[0]
    lines[1] = f"{code},{bad}"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(DataError, match=f"^median_prices.csv: no price for {code}$"):
        load(tmp_path)


def test_load_price_file_empty(tmp_path: Path) -> None:
    copy_data(tmp_path)
    (tmp_path / "median_prices.csv").write_text("")
    with pytest.raises(DataError, match="median_prices.csv"):
        load(tmp_path)


def test_load_price_file_header_only(tmp_path: Path) -> None:
    copy_data(tmp_path)
    (tmp_path / "median_prices.csv").write_text("stock_code,median_price\n")
    with pytest.raises(DataError, match="^median_prices.csv: no price for "):
        load(tmp_path)


def test_load_price_file_wrong_columns(tmp_path: Path) -> None:
    copy_data(tmp_path)
    path = tmp_path / "median_prices.csv"
    path.write_text(path.read_text().replace("median_price", "price", 1))
    with pytest.raises(DataError, match="median_prices.csv"):
        load(tmp_path)


def test_load_price_file_binary_garbage(tmp_path: Path) -> None:
    copy_data(tmp_path)
    (tmp_path / "median_prices.csv").write_bytes(b"\xff\xfe\x00\x81" * 100)
    with pytest.raises(DataError, match="median_prices.csv"):
        load(tmp_path)


def test_load_price_extra_codes_and_reordered_rows_ok(tmp_path: Path) -> None:
    copy_data(tmp_path)
    path = tmp_path / "median_prices.csv"
    lines = path.read_text().splitlines()
    path.write_text(
        "\n".join([lines[0], *reversed(lines[1:]), "ZZZ999,1.50", "Ünïcødé,2.00"])
        + "\n"
    )
    d = load(tmp_path)
    assert d.prices == load(DATA).prices | {"ZZZ999": 1.50, "Ünïcødé": 2.00}


def test_load_other_missing_file_reported_before_prices(tmp_path: Path) -> None:
    copy_data(tmp_path)
    (tmp_path / "median_prices.csv").unlink()
    (tmp_path / "products_synthetic.csv").unlink()
    with pytest.raises(DataError, match="products_synthetic.csv"):
        load(tmp_path)


def test_load_price_file_first_code_matches_real_data() -> None:
    assert first_code() in load(DATA).prices


# ---------- real data on the 5 presets ----------


@pytest.fixture(scope="module")
def real() -> PlannerData:
    return load(DATA)


@pytest.fixture(scope="module")
def preset_runs(real: PlannerData) -> dict[str, ScenarioResult]:
    return {name: run(real, s) for name, s in PRESETS.items()}


@pytest.mark.parametrize("name", list(PRESETS))
def test_real_presets_follow_dec19(
    name: str, real: PlannerData, preset_runs: dict[str, ScenarioResult]
) -> None:
    check_dec19(real, preset_runs[name])


def test_real_do_nothing_money_ignores_budget_and_safety(
    preset_runs: dict[str, ScenarioResult],
) -> None:
    base = preset_runs["Baseline"].kpis
    for name in ("Tight budget", "Efficiency"):
        k = preset_runs[name].kpis
        assert k.lost_sales_gbp == base.lost_sales_gbp, name
        assert k.tied_up_gbp == base.tied_up_gbp, name


def test_real_peak_loses_more_and_ties_up_less(
    preset_runs: dict[str, ScenarioResult],
) -> None:
    base, peak = preset_runs["Baseline"], preset_runs["Peak season +25%"]
    base_by = {p.stock_code: p for p in base.products}
    for p in peak.products:
        b = base_by[p.stock_code]
        assert p.lost_sales_gbp >= b.lost_sales_gbp, p.stock_code
        assert p.tied_up_gbp <= b.tied_up_gbp, p.stock_code
    assert peak.kpis.lost_sales_gbp > base.kpis.lost_sales_gbp


def test_real_delay_never_lowers_do_nothing_lost_sales(
    preset_runs: dict[str, ScenarioResult],
) -> None:
    base_by = {p.stock_code: p for p in preset_runs["Baseline"].products}
    for p in preset_runs["Supplier delay +3 weeks"].products:
        assert p.lost_sales_gbp >= base_by[p.stock_code].lost_sales_gbp, p.stock_code


def test_real_tight_budget_has_unfunded_money(
    preset_runs: dict[str, ScenarioResult],
) -> None:
    tight = preset_runs["Tight budget"].kpis
    assert tight.unfunded_gbp > 0
    assert tight.funded_spend_gbp <= tight.budget_gbp
    assert (
        tight.lost_sales_after_plan_gbp
        >= preset_runs["Baseline"].kpis.lost_sales_after_plan_gbp
    )


def test_real_84347_baseline_story(preset_runs: dict[str, ScenarioResult]) -> None:
    p = of(preset_runs["Baseline"], "84347")
    assert p.stockout is not None
    assert (p.stockout.start_month, p.stockout.end_month, p.stockout.months) == (
        "2011-12",
        "2012-02",
        3,
    )
    assert p.stockout.units == 1006
    assert p.stockout.lost_sales_gbp == round(1006 * p.sell_price, 2)
    assert f"Later shortfall not covered: {units(5759)} from Sep 2012" in p.flags


@pytest.mark.parametrize("horizon", [6, 9, 12])
def test_real_baseline_other_horizons(real: PlannerData, horizon: int) -> None:
    check_dec19(
        real, run(real, BASELINE.model_copy(update={"horizon_months": horizon}))
    )


@pytest.mark.parametrize("method", METHODS)
def test_real_backtest(real: PlannerData, method: Method) -> None:
    bt = backtest(real, method)
    assert bt.method == method and bt.as_of == "2010-12"
    assert len(bt.rows) == 36
    assert 0 < bt.overall_pct < 1000
    assert {r.stock_code for r in bt.rows} == {p.stock_code for p in real.products}
    assert all(r.mape_pct is None or r.mape_pct >= 0 for r in bt.rows)


def test_capacity_blocked_with_long_lead_is_lead_time_stockout() -> None:
    """lead 2 months, room 10 < MOQ 50: no order, factor = lead time (DEC-09 order); nothing arrives, so the
    stockout runs to the horizon (DEC-19)."""
    p = one(toy("C2", lead_time_weeks=5, capacity=10))
    assert p.order is None
    assert p.limiting_factor == "lead time"
    assert p.stockout is not None
    assert (p.stockout.start_month, p.stockout.end_month, p.stockout.units) == (
        "2012-01",
        "2012-05",
        260,
    )
    assert p.lost_sales_after_plan_gbp == p.lost_sales_gbp == 1300.00
    assert p.stockout_months == 5
