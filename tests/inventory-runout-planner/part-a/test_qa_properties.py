import math
from fractions import Fraction

import numpy as np
import pytest
from inventory_runout_planner.models import (
    MonthRow,
    PlannerData,
    Product,
    Scenario,
    ScenarioResult,
)
from inventory_runout_planner.planner import forecast, lead_months, month_key, run

MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)
SEEDS = list(range(40))


def ri(rng: np.random.Generator, low: int, high: int) -> int:
    return int(rng.integers(low, high + 1))


def pick[T](rng: np.random.Generator, options: list[T]) -> T:
    return options[int(rng.integers(len(options)))]


def half_up_exact(x: Fraction) -> int:
    return math.floor(x + Fraction(1, 2))


def rand_product(rng: np.random.Generator, i: int) -> Product:
    stock = pick(rng, [0, 1, ri(rng, 0, 3000)])
    inbound = pick(rng, [0, 0, ri(rng, 1, 1500)])
    return Product(
        stock_code=f"P{i:03d}",
        description=f"Toy {i}",
        group="Gifts & small goods",
        unit_cost=round(float(rng.uniform(0.01, 40)), 2),
        stock_on_hand=stock,
        lead_time_weeks=ri(rng, 0, 12),
        moq=pick(rng, [1, 50, ri(rng, 1, 400)]),
        capacity=pick(rng, [1, ri(rng, 1, 3000), 5000]),
        inbound_qty=inbound,
        inbound_weeks=ri(rng, 0, 30) if inbound else 0,
    )


def rand_history(rng: np.random.Generator) -> list[int]:
    kind = pick(rng, ["zero", "flat", "random", "sparse"])
    if kind == "zero":
        return [0] * 24
    if kind == "flat":
        return [ri(rng, 1, 300)] * 24
    if kind == "sparse":
        return [pick(rng, [0, 0, ri(rng, 1, 800)]) for _ in range(24)]
    return [ri(rng, 0, 600) for _ in range(24)]


def rand_scenario(rng: np.random.Generator) -> Scenario:
    return Scenario(
        horizon_months=ri(rng, 6, 12),
        growth_pct=pick(rng, [-50, 0, 100, ri(rng, -50, 100), 12.5]),
        delay_weeks=pick(rng, [0, 26, ri(rng, 0, 26)]),
        budget_gbp=pick(rng, [0, 1_000_000, ri(rng, 0, 20000)]),
        safety_months=pick(rng, [0, 6, 0.5, 1, ri(rng, 0, 12) / 2]),
        method=pick(rng, ["seasonal_naive", "trailing_3m"]),
    )


def world(seed: int) -> tuple[PlannerData, Scenario]:
    rng = np.random.default_rng(seed)
    products = [rand_product(rng, i) for i in range(ri(rng, 1, 8))]
    data = PlannerData(
        products=products,
        history={p.stock_code: rand_history(rng) for p in products},
        history_months=MONTHS,
    )
    return data, rand_scenario(rng)


def check_rows(rows: list[MonthRow], stock: int) -> None:
    prev = stock
    for r in rows:
        assert min(r.demand, r.opening, r.inbound, r.shipped, r.unmet, r.closing) >= 0
        assert r.shipped + r.unmet == r.demand
        assert r.closing == r.opening + r.inbound - r.shipped
        assert r.opening == prev
        assert r.shipped <= r.opening + r.inbound
        prev = r.closing


@pytest.mark.parametrize("seed", SEEDS)
def test_random_world_invariants(seed: int) -> None:
    data, sc = world(seed)
    res = run(data, sc)
    by_code = {p.stock_code: p for p in data.products}
    assert {p.stock_code for p in res.products} == set(by_code)
    assert len(res.products) == len(data.products)
    for pr in res.products:
        prod = by_code[pr.stock_code]
        assert len(pr.months) == len(pr.plan_months) == sc.horizon_months
        check_rows(pr.months, prod.stock_on_hand)
        check_rows(pr.plan_months, prod.stock_on_hand)
        assert [r.demand for r in pr.months] == [r.demand for r in pr.plan_months]
        assert pr.months[0].month == "2011-12"
        # runout = first month with unmet
        first = next((r.month for r in pr.months if r.unmet), None)
        assert pr.runout_month == first
        assert pr.value_at_risk_gbp == pytest.approx(
            sum(r.unmet for r in pr.months) * prod.unit_cost, abs=0.006
        )
        # plan never worse than do-nothing
        assert sum(r.unmet for r in pr.plan_months) <= sum(r.unmet for r in pr.months)
        # conservation of units: closing_end = stock + inbound_total - shipped_total
        for rows in (pr.months, pr.plan_months):
            inbound = sum(r.inbound for r in rows)
            shipped = sum(r.shipped for r in rows)
            assert rows[-1].closing == prod.stock_on_hand + inbound - shipped
        funded_qty = pr.order.qty if pr.order and pr.order.funded else 0
        base_in = sum(r.inbound for r in pr.months)
        plan_in = sum(r.inbound for r in pr.plan_months)
        arr = pr.order.arrival_month if pr.order else None
        in_horizon = arr is not None and arr <= pr.months[-1].month
        assert plan_in == base_in + (funded_qty if in_horizon else 0)
        assert pr.lead_months == lead_months(prod.lead_time_weeks + sc.delay_weeks)
        # limiting factor precedence
        if pr.runout_month is None:
            assert pr.limiting_factor == "none"
        elif pr.order is not None and pr.order.arrival_month > pr.runout_month:
            assert pr.limiting_factor == "lead time"
        elif pr.order is None:
            assert pr.limiting_factor in ("capacity", "lead time")
            assert any(f.startswith("Capacity blocks order") for f in pr.flags)
        elif not pr.order.funded:
            assert pr.limiting_factor == "budget"
        else:
            assert pr.limiting_factor == "stock"
        if pr.order is not None:
            o = pr.order
            assert o.limiting_factor == pr.limiting_factor
            assert o.qty >= prod.moq
            assert o.qty > 0
            assert o.cost_gbp == pytest.approx(round(o.qty * prod.unit_cost, 2))
            assert o.arrival_month > o.order_month or pr.lead_months == 0
            assert o.stock_code == pr.stock_code
            if o.funded:
                assert "Not funded" not in o.reason
            else:
                assert o.reason.endswith("left of budget.")
    # budget / plan
    assert [line.rank for line in res.plan] == list(range(1, len(res.plan) + 1))
    funded = [line for line in res.plan if line.funded]
    spend = round(sum(line.cost_gbp for line in funded), 2)
    assert res.kpis.funded_spend_gbp == spend
    assert spend <= sc.budget_gbp + 1e-6
    assert res.kpis.suggested_spend_gbp == round(
        sum(line.cost_gbp for line in res.plan), 2
    )
    assert res.kpis.unfunded_orders == len(res.plan) - len(funded)
    assert res.kpis.budget_gbp == sc.budget_gbp
    # greedy: every unfunded order did not fit in what remained at its turn
    remaining = sc.budget_gbp
    for line in res.plan:
        if line.funded:
            assert line.cost_gbp <= remaining + 1e-6
            remaining -= line.cost_gbp
        else:
            assert line.cost_gbp > remaining - 1e-6
    # rank order DEC-09
    byc = {p.stock_code: p for p in res.products}
    keys = []
    for line in res.plan:
        pr = byc[line.stock_code]
        idx = (
            int(pr.runout_month[:4]) * 12 + int(pr.runout_month[5:])
            if pr.runout_month
            else None
        )
        t = idx - (2011 * 12 + 11) + 1 if idx else sc.horizon_months + 1
        keys.append((t, -pr.value_at_risk_gbp, line.stock_code))
    assert keys == sorted(keys)
    # products list is in the same rank order (ranked drafts)
    codes_plan = [line.stock_code for line in res.plan]
    codes_prod = [p.stock_code for p in res.products if p.order]
    assert codes_plan == codes_prod
    # kpis
    at_risk = [p for p in res.products if p.runout_month]
    order_now = [
        p
        for p in at_risk
        if p.runout_month and p.runout_month <= month_key(p.lead_months + 1)
    ]
    assert res.kpis.products_at_risk == len(order_now)
    if at_risk:
        best = min(
            at_risk,
            key=lambda p: (p.runout_month or "", -p.value_at_risk_gbp, p.stock_code),
        )
        assert res.kpis.earliest_runout_code == best.stock_code
        assert res.kpis.earliest_runout_month == best.runout_month
        assert res.kpis.earliest_limiting_factor == best.limiting_factor
    else:
        assert res.kpis.earliest_runout_code is None
        assert res.kpis.earliest_runout_month is None


def oracle_order(
    p: Product, hist: list[int], sc: Scenario
) -> tuple[str | None, str | None, int | None, str | None]:
    """Independent DEC-08/09 implementation: runout, order_month, qty, arrival."""
    h = sc.horizon_months
    lead = math.ceil((p.lead_time_weeks + sc.delay_weeks) * 7 / 30.44)
    span = h + lead + 3
    dem = forecast(hist, sc.method, sc.growth_pct, span)
    inb_t = 1 + math.ceil((p.inbound_weeks + sc.delay_weeks) * 7 / 30.44)
    opening = [0] * (span + 1)
    inbound = [0] * (span + 1)
    closing = [0] * (span + 1)
    unmet = [0] * (span + 1)
    stock = p.stock_on_hand
    for t in range(1, span + 1):
        opening[t] = stock
        inbound[t] = p.inbound_qty if (p.inbound_qty and t == inb_t) else 0
        avail = stock + inbound[t]
        ship = min(dem[t - 1], avail)
        unmet[t] = dem[t - 1] - ship
        closing[t] = avail - ship
        stock = closing[t]
    safety = [half_up_exact(Fraction(str(sc.safety_months)) * d) for d in dem]
    runout = next((t for t in range(1, h + 1) if unmet[t] > 0), None)
    trig = next(
        (t for t in range(1, h + 1) if closing[t] < safety[t - 1] or unmet[t] > 0),
        None,
    )
    if trig is None:
        return (month_key(runout) if runout else None, None, None, None)
    ot = max(1, trig - lead)
    a = ot + lead
    avail = opening[a] + inbound[a]
    need = sum(dem[a - 1 : a + 2]) + safety[a - 1] - avail
    room = p.capacity - avail
    rm = month_key(runout) if runout else None
    if room < p.moq:
        return (rm, None, None, None)
    return (rm, month_key(ot), min(max(p.moq, need), room), month_key(a))


@pytest.mark.parametrize("seed", range(100, 160))
def test_orders_match_independent_oracle(seed: int) -> None:
    data, sc = world(seed)
    res = run(data, sc)
    for p in data.products:
        pr = next(r for r in res.products if r.stock_code == p.stock_code)
        runout, om, qty, am = oracle_order(p, data.history[p.stock_code], sc)
        assert pr.runout_month == runout
        if qty is None:
            assert pr.order is None
        else:
            assert pr.order is not None
            assert (pr.order.order_month, pr.order.qty, pr.order.arrival_month) == (
                om,
                qty,
                am,
            )


@pytest.mark.parametrize("seed", SEEDS[:15])
def test_run_is_deterministic_and_pure(seed: int) -> None:
    data, sc = world(seed)
    snapshot = data.model_dump()
    a = run(data, sc)
    b = run(data, sc)
    assert a == b
    assert data.model_dump() == snapshot


@pytest.mark.parametrize("seed", SEEDS[:15])
def test_more_budget_never_funds_less_total_orders_count_monotone_kpis(
    seed: int,
) -> None:
    data, sc = world(seed)
    lo = run(data, sc.model_copy(update={"budget_gbp": 0}))
    hi = run(data, sc.model_copy(update={"budget_gbp": 1_000_000}))
    assert lo.kpis.funded_spend_gbp == 0
    assert lo.kpis.unfunded_orders == len(lo.plan)
    assert hi.kpis.unfunded_orders == 0
    assert hi.kpis.funded_spend_gbp == hi.kpis.suggested_spend_gbp
    assert [x.qty for x in lo.plan] == [x.qty for x in hi.plan]
    for p in lo.products:
        assert p.plan_months == p.months


def test_forecast_matches_exact_half_up_for_all_integer_growths() -> None:
    hist = [
        0,
        1,
        2,
        3,
        5,
        7,
        11,
        13,
        17,
        19,
        23,
        29,
        31,
        37,
        41,
        43,
        47,
        50,
        55,
        99,
        101,
        333,
        1001,
        7,
    ]
    for growth in range(-50, 101):
        got = forecast(hist, "seasonal_naive", growth, 14)
        want = [
            half_up_exact(Fraction(hist[-12 + (t % 12)]) * (100 + growth) / 100)
            for t in range(14)
        ]
        assert got == want, growth
        got3 = forecast(hist, "trailing_3m", growth, 5)
        mean = Fraction(sum(hist[-3:]), 3)
        assert got3 == [half_up_exact(mean * (100 + growth) / 100)] * 5, growth


def test_forecast_halves_and_fractional_growth() -> None:
    hist = [10] * 24
    assert forecast(hist, "seasonal_naive", 12.5, 1) == [11]  # 11.25
    assert forecast(hist, "seasonal_naive", 15, 1) == [12]  # 11.5 -> 12
    assert forecast(hist, "seasonal_naive", -15, 1) == [9]  # 8.5 -> 9
    assert forecast(hist, "seasonal_naive", -50, 1) == [5]
    assert forecast([0] * 24, "trailing_3m", 100, 3) == [0, 0, 0]
    assert forecast(hist, "seasonal_naive", 0, 0) == []


def test_forecast_long_horizon_wraps_by_12() -> None:
    hist = list(range(24))
    f = forecast(hist, "seasonal_naive", 0, 40)
    assert f[:12] == list(range(12, 24))
    assert f[12:24] == f[:12] == f[24:36]
    assert len(f) == 40


def test_result_roundtrips_through_pydantic() -> None:
    data, sc = world(3)
    res = run(data, sc)
    assert ScenarioResult.model_validate(res.model_dump()) == res


def test_forecast_tie_after_float_error_rounds_up() -> None:
    # 25 * (1 - 0.34) = 16.5 exactly in decimal; DEC-07 says half up -> 17
    assert forecast([25] * 24, "seasonal_naive", -34, 1) == [17]
    # 50 * 1.13 = 56.5 -> 57
    assert forecast([50] * 24, "seasonal_naive", 13, 1) == [57]
    # trailing: mean(75,0,0)=25 * 0.66 = 16.5 -> 17
    assert forecast([0] * 21 + [75, 0, 0], "trailing_3m", -34, 1) == [17]


def test_safety_units_tie_rounds_up_for_decimal_safety_months() -> None:
    # safety_months=0.7 x demand 45 = 31.5 in decimal -> 32 (DEC-09); float product is 31.499999999999996
    data = PlannerData(
        products=[
            Product(
                stock_code="S",
                description="S",
                group="g",
                unit_cost=1.0,
                stock_on_hand=100,
                lead_time_weeks=0,
                moq=1,
                capacity=10_000,
                inbound_qty=0,
                inbound_weeks=0,
            )
        ],
        history={"S": [45] * 24},
        history_months=MONTHS,
    )
    sc = Scenario(
        horizon_months=6,
        growth_pct=0,
        delay_weeks=0,
        budget_gbp=1000,
        safety_months=0.7,
        method="seasonal_naive",
    )
    # month 1 closing = 55, month 2 = 10 (<32). Order at arrival month 2: available 55, need = 3*45 + 32 - 55 = 112
    order = run(data, sc).products[0].order
    assert order is not None
    assert order.qty == 135 + 32 - 55
