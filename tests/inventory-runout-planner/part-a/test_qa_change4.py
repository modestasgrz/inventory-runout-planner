import itertools
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from inventory_runout_planner.data import load
from inventory_runout_planner.fmt import gbp, month, number, units
from inventory_runout_planner.models import (
    PlannerData,
    Product,
    ProductResult,
    ReorderLine,
    Scenario,
    ScenarioResult,
)
from inventory_runout_planner.planner import MAX_ORDERS, forecast, month_key, run
from inventory_runout_planner.presets import BASELINE, PRESETS
from pydantic import BaseModel

DATA = Path(__file__).resolve().parents[3] / "data"
MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)


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


def go(
    *products: Product,
    history: dict[str, list[int]] | None = None,
    max_orders: int = MAX_ORDERS,
    **scenario_overrides: Any,
) -> ScenarioResult:
    data = PlannerData(
        products=list(products),
        history=history or {p.stock_code: [60] * 24 for p in products},
        history_months=MONTHS,
        prices={p.stock_code: 5.00 for p in products},
    )
    return run(data, toy_scenario(**scenario_overrides), max_orders=max_orders)


def of(result: ScenarioResult, code: str) -> ProductResult:
    return next(p for p in result.products if p.stock_code == code)


def brief(line: ReorderLine) -> tuple[int, str, str, int, float, bool, str]:
    return (
        line.order_no,
        line.order_month,
        line.arrival_month,
        line.qty,
        line.cost_gbp,
        line.funded,
        line.limiting_factor,
    )


# ---------- hand cases ----------


def test_default_max_orders_is_four() -> None:
    assert MAX_ORDERS == 4


def test_four_orders_over_twelve_months_with_dependency_funding() -> None:
    """T0001, H=12: each order of 180 (+ the first of 200) lasts 3 months and stock dips again:
    o1 Dec→Jan 200, o2 Mar→Apr 180 (s May), o3 Jun→Jul 180 (s Aug), o4 Sep→Oct 180 (s Nov).
    Budget 1000: o1 400 + o2 360 funded (£240 left), o3 £360 not funded, o4 blocked by o3."""
    r = go(toy("T0001"), horizon_months=12)
    p = of(r, "T0001")
    assert [brief(o) for o in p.orders] == [
        (1, "2011-12", "2012-01", 200, 400.00, True, "stock"),
        (2, "2012-03", "2012-04", 180, 360.00, True, "stock"),
        (3, "2012-06", "2012-07", 180, 360.00, False, "budget"),
        (4, "2012-09", "2012-10", 180, 360.00, False, "budget"),
    ]
    assert p.order == p.orders[0]
    assert r.plan == p.orders
    assert [x.rank for x in r.plan] == [1, 2, 3, 4]
    assert p.orders[2].reason.endswith("Not funded: £240.00 left of budget.")
    assert p.orders[3].reason.endswith("Not funded: earlier order not funded.")
    assert p.limiting_factor == "stock"
    # with plan: o1 + o2 arrive; Aug–Nov 2012 short 4 × 60
    assert [r.unmet for r in p.plan_months] == [0] * 8 + [60] * 4
    assert p.lost_sales_after_plan_gbp == 1200.00
    assert p.stockout_months == 4
    assert p.later_shortfall_units == 240
    assert p.later_shortfall_month == "2012-08"
    assert f"Short after plan: {units(240)} from Aug 2012" in p.flags
    assert r.kpis.funded_spend_gbp == 760.00
    assert r.kpis.suggested_spend_gbp == 1480.00
    assert r.kpis.unfunded_orders == 2
    assert r.kpis.unfunded_gbp == 720.00
    assert r.kpis.products_at_risk == 1


def test_four_orders_all_funded_cover_the_horizon() -> None:
    p = of(go(toy("T0001"), horizon_months=12, budget_gbp=1480), "T0001")
    assert [o.funded for o in p.orders] == [True] * 4
    assert [o.limiting_factor for o in p.orders] == ["stock"] * 4
    assert all(r.unmet == 0 for r in p.plan_months)
    assert [r.inbound for r in p.plan_months] == [
        0,
        200,
        0,
        0,
        180,
        0,
        0,
        180,
        0,
        0,
        180,
        0,
    ]
    assert p.lost_sales_after_plan_gbp == 0.00
    assert not p.at_risk_after_plan
    assert p.later_shortfall_units == 0
    assert not any(f.startswith("Short after plan") for f in p.flags)


def test_one_penny_short_for_the_last_follow_up() -> None:
    p = of(go(toy("T0001"), horizon_months=12, budget_gbp=1479.99), "T0001")
    assert [o.funded for o in p.orders] == [True, True, True, False]
    assert p.orders[3].reason.endswith("Not funded: £359.99 left of budget.")
    assert p.lost_sales_after_plan_gbp == 300.00  # Nov 2012, 60 units


@pytest.mark.parametrize("max_orders", [1, 2, 3, 4])
def test_max_orders_caps_the_count(max_orders: int) -> None:
    r = go(toy("T0001"), horizon_months=12, max_orders=max_orders, budget_gbp=10_000)
    p = of(r, "T0001")
    assert [o.order_no for o in p.orders] == list(range(1, max_orders + 1))
    assert len(r.plan) == max_orders
    # each funded order covers 3 more months: unmet from month 3 × max_orders + 2 on
    covered = 3 * max_orders + 2
    assert [r.unmet > 0 for r in p.plan_months] == [t > covered for t in range(1, 13)]


def test_follow_up_reasons_follow_dec21_and_dec12() -> None:
    p = of(go(toy("T0001"), horizon_months=12, budget_gbp=2000), "T0001")
    assert p.orders[0].reason == (
        "Runs out Jan 2012 without an order. Lead time 4 weeks + delay 0 weeks = 1 month(s): order Dec 2011, "
        f"arrives Jan 2012. Order {units(200)} = 3 months demand 180 + safety 60 − available 40 (MOQ 50, room 360). "
        "Cost £400.00."
    )
    for o, runs_out, order_m, arrives in zip(
        p.orders[1:],
        ["May 2012", "Aug 2012", "Nov 2012"],
        ["Mar 2012", "Jun 2012", "Sep 2012"],
        ["Apr 2012", "Jul 2012", "Oct 2012"],
        strict=True,
    ):
        assert o.reason == (
            f"Follow-up order {o.order_no}: runs out {runs_out} after the earlier order(s). "
            f"Lead time 4 weeks + delay 0 weeks = 1 month(s): order {order_m}, arrives {arrives}. "
            f"Order {units(180)} = 3 months demand 180 + safety 60 − available 60 (MOQ 50, room 340). "
            "Cost £360.00."
        )


def test_follow_up_below_safety_only_has_factor_none() -> None:
    """H=11: o4 triggers in Oct 2012 (closing 0 < safety 60) but its short month (Nov 2012) is past the horizon,
    so s_4 = H + 1: reason `falls below safety stock`, factor `none` when funded, `budget` when not."""
    r = go(toy("T0001"), horizon_months=11, budget_gbp=2000)
    p = of(r, "T0001")
    assert len(p.orders) == 4
    o4 = p.orders[3]
    assert (o4.order_month, o4.arrival_month, o4.funded) == ("2012-09", "2012-10", True)
    assert o4.limiting_factor == "none"
    assert o4.reason.startswith(
        "Follow-up order 4: falls below safety stock in Oct 2012. Lead time 4 weeks"
    )
    assert [o.limiting_factor for o in p.orders[:3]] == ["stock"] * 3
    unfunded = of(go(toy("T0001"), horizon_months=11, budget_gbp=1479.99), "T0001")
    assert unfunded.orders[3].limiting_factor == "budget"
    assert not unfunded.orders[3].funded
    # o4 is not needed for with-plan unmet inside the horizon
    assert unfunded.lost_sales_after_plan_gbp == 0.00


def test_first_order_below_safety_without_runout() -> None:
    """Stock 360: closings 300…60, 0 — never short in 6 months, but May 2012 closing 0 < safety 60 → order 1 only
    (order Apr, arrives May), reason `Falls below safety stock`, factor `none` (cover exactly 6.0, not overstocked)."""
    p = of(go(toy("S0001", stock_on_hand=360)), "S0001")
    assert p.runout_month is None
    assert p.limiting_factor == "none"
    assert len(p.orders) == 1
    o = p.orders[0]
    assert (o.order_month, o.arrival_month) == ("2012-04", "2012-05")
    assert o.limiting_factor == "none"
    assert o.reason.startswith("Falls below safety stock in May 2012.")


def test_stop_when_no_further_dip() -> None:
    """H=6: o2 (arrives Apr 2012) carries stock to the horizon end, so no third order."""
    r = go(
        toy("T0001"), toy("T0005", stock_on_hand=1000), toy("T0006", stock_on_hand=300)
    )
    assert [o.order_no for o in of(r, "T0001").orders] == [1, 2]
    assert of(r, "T0005").orders == []
    assert of(r, "T0005").order is None
    assert [o.order_no for o in of(r, "T0006").orders] == [1]


def test_follow_up_for_lead_time_product() -> None:
    """T0002 (lead 3 months), H=12, budget 1000: o1 Dec→Mar 240 (£480), o2 placed Mar (when o1 lands) → Jun 180
    (£360), o3 Jun→Sep 180 not funded (£160 left). Stockout Jan–Feb (80 units); with plan Oct–Nov short 120."""
    r = go(toy("T0002", lead_time_weeks=10), horizon_months=12)
    p = of(r, "T0002")
    assert [brief(o) for o in p.orders] == [
        (1, "2011-12", "2012-03", 240, 480.00, True, "lead time"),
        (2, "2012-03", "2012-06", 180, 360.00, True, "stock"),
        (3, "2012-06", "2012-09", 180, 360.00, False, "budget"),
    ]
    assert p.orders[1].reason.startswith(
        "Follow-up order 2: runs out Jul 2012 after the earlier order(s). Lead time 10 weeks + delay 0 weeks"
        " = 3 month(s): order Mar 2012, arrives Jun 2012."
    )
    assert p.orders[2].reason.endswith("Not funded: £160.00 left of budget.")
    assert p.limiting_factor == "lead time"
    assert p.stockout is not None
    assert (p.stockout.start_month, p.stockout.end_month, p.stockout.units) == (
        "2012-01",
        "2012-02",
        80,
    )
    assert p.later_shortfall_units == 120
    assert p.later_shortfall_month == "2012-10"
    assert f"Short after plan: {units(120)} from Oct 2012" in p.flags
    assert p.lost_sales_after_plan_gbp == 1000.00  # (80 + 120) × £5
    assert p.stockout_months == 4


def test_lead_time_product_unfunded_first_order_blocks_follow_ups() -> None:
    p = of(
        go(toy("T0002", lead_time_weeks=10), horizon_months=12, budget_gbp=400), "T0002"
    )
    assert [o.funded for o in p.orders] == [False, False, False]
    assert p.orders[0].reason.endswith("Not funded: £400.00 left of budget.")
    assert all(
        o.reason.endswith("Not funded: earlier order not funded.") for o in p.orders[1:]
    )
    assert p.plan_months == p.months
    assert p.later_shortfall_units == 0
    assert not any(f.startswith("Short after plan") for f in p.flags)
    assert p.stockout is not None and p.stockout.end_month == "2012-11"


def test_capacity_stops_a_follow_up() -> None:
    """Lead 0, safety 0, MOQ 300, capacity 400, demand 60 except Apr 2012 = 200.
    o1 Jan 2012: available 40, room 360, qty max(300, 140) = 300. Stock 340→280→220→160; Apr needs 200:
    trigger Apr, available 160, room 240 < MOQ 300 → capacity flag, no order 2. Product factor stays `stock`."""
    last12 = [60, 60, 60, 60, 200, 60, 60, 60, 60, 60, 60, 60]
    r = go(
        toy("C0001", lead_time_weeks=0, moq=300),
        history={"C0001": last12 + last12},
        safety_months=0,
    )
    p = of(r, "C0001")
    assert [brief(o) for o in p.orders] == [
        (1, "2012-01", "2012-01", 300, 600.00, True, "stock"),
    ]
    assert "Capacity blocks order: room 240 < MOQ 300" in p.flags
    assert p.limiting_factor == "stock"
    assert [x.unmet for x in p.plan_months] == [0, 0, 0, 0, 40, 60]
    assert p.lost_sales_after_plan_gbp == 500.00
    assert p.later_shortfall_units == 100
    assert f"Short after plan: {units(100)} from Apr 2012" in p.flags


def test_unfunded_follow_up_frees_budget_for_other_product() -> None:
    """A's order 1 (£400) does not fit £380; A's order 2 (£360) would, but depends on order 1;
    B (unit cost £1) gets its order 1 (£200) and its order 2 (£180 = exactly the £180 left)."""
    r = go(toy("A0001"), toy("B0001", unit_cost=1.00), budget_gbp=380)
    assert [(x.stock_code, x.order_no, x.cost_gbp, x.funded) for x in r.plan] == [
        ("A0001", 1, 400.00, False),
        ("B0001", 1, 200.00, True),
        ("A0001", 2, 360.00, False),
        ("B0001", 2, 180.00, True),
    ]
    assert r.plan[2].reason.endswith("Not funded: earlier order not funded.")
    assert r.kpis.funded_spend_gbp == 380.00
    assert r.kpis.unfunded_gbp == 760.00


def test_ranking_follow_up_against_other_first_order() -> None:
    """X = T0001 (s1 Jan, s2 May, value at risk £520); Y = stock 300 runs out May (s1 May).
    Y cheap (£2, VaR £120): X2 before Y1. Y dear (£20, VaR £1 200): Y1 before X2."""
    cheap = go(toy("X0001"), toy("Y0001", stock_on_hand=300), budget_gbp=1_000_000)
    assert [(x.stock_code, x.order_no) for x in cheap.plan] == [
        ("X0001", 1),
        ("X0001", 2),
        ("Y0001", 1),
    ]
    dear = go(
        toy("X0001"),
        toy("Y0001", stock_on_hand=300, unit_cost=20.00),
        budget_gbp=1_000_000,
    )
    assert [(x.stock_code, x.order_no) for x in dear.plan] == [
        ("X0001", 1),
        ("Y0001", 1),
        ("X0001", 2),
    ]
    assert [x.rank for x in dear.plan] == [1, 2, 3]
    assert of(dear, "Y0001").value_at_risk_gbp == 1200.00


def test_ranking_budget_goes_to_earlier_short_month_first() -> None:
    """Budget 760: X1 £400, then Y1 (£3 600 at £20) does not fit, X2 £360 does."""
    r = go(
        toy("X0001"),
        toy("Y0001", stock_on_hand=300, unit_cost=20.00),
        budget_gbp=760,
    )
    assert [(x.stock_code, x.order_no, x.funded) for x in r.plan] == [
        ("X0001", 1, True),
        ("Y0001", 1, False),
        ("X0001", 2, True),
    ]
    assert of(r, "Y0001").orders[0].limiting_factor == "budget"
    assert r.plan[1].reason.endswith("Not funded: £360.00 left of budget.")


def test_tie_on_everything_but_code_ranks_by_code_then_order_no() -> None:
    r = go(toy("B0001"), toy("A0001"), budget_gbp=1_000_000)
    assert [(x.stock_code, x.order_no) for x in r.plan] == [
        ("A0001", 1),
        ("B0001", 1),
        ("A0001", 2),
        ("B0001", 2),
    ]


def test_order_one_matches_single_order_run_with_follow_ups() -> None:
    """Order 1 is exactly the DEC-09 order (same reason) whatever max_orders is."""
    one = of(go(toy("T0001"), horizon_months=12, max_orders=1), "T0001")
    four = of(go(toy("T0001"), horizon_months=12), "T0001")
    assert one.orders == [one.order]
    assert one.order is not None and four.order is not None
    assert one.order.model_dump(exclude={"rank"}) == four.order.model_dump(
        exclude={"rank"}
    )


def test_follow_up_after_inbound_and_delay() -> None:
    """Inbound 200 (3 weeks + delay 3 weeks → Feb 2012); T lead 4 + 3 weeks = 2 months; safety 0, H=8.
    Do nothing: Dec 40, Jan short 20 (run-out Jan), Feb 200 → 140, Mar 80, Apr 20, May short 40.
    o1: trigger Jan, order Dec, arrives Feb: available 0 + 200, need 180 − 200 → MOQ 50 → room 200 → 50 units.
    Projection: Feb 190, Mar 130, Apr 70, May 10, Jun short 50 → o2 trigger Jun, order Apr, arrives Jun,
    available 10, need 180 − 10 = 170."""
    r = go(
        toy("D0001", stock_on_hand=100, inbound_qty=200, inbound_weeks=3),
        delay_weeks=3,
        safety_months=0,
        horizon_months=8,
    )
    p = of(r, "D0001")
    assert p.runout_month == "2012-01"
    assert p.inbound_month == "2012-02"
    assert [brief(o)[:4] for o in p.orders] == [
        (1, "2011-12", "2012-02", 50),
        (2, "2012-04", "2012-06", 170),
    ]
    assert p.limiting_factor == "lead time"
    assert p.orders[1].limiting_factor == "stock"
    assert p.orders[1].reason.startswith("Follow-up order 2: runs out Jun 2012")
    # o2 covers Jun, Jul, Aug exactly (170 + 10 = 180)
    assert [x.unmet for x in p.plan_months] == [0, 20, 0, 0, 0, 0, 0, 0]
    assert p.later_shortfall_units == 0
    assert p.stockout is not None and p.stockout.units == 20


# ---------- independent DEC-21 oracle ----------


class Planned(BaseModel):
    code: str
    k: int
    order_t: int
    arrival: int
    trigger: int
    short: int
    qty: int
    cost_pence: int
    reason: str


class Expected(BaseModel):
    runout: int | None
    first_arrival: int | None
    value_at_risk: float
    orders: list[Planned]
    capacity_flag: str | None
    do_nothing_unmet: list[int]
    demand: list[int]


def half_up(x: Fraction) -> int:
    return math.floor(x + Fraction(1, 2))


def lead_of(weeks: int) -> int:
    return math.ceil(weeks * 7 / 30.44)


def simulate(
    stock: int, demand: list[int], arrivals: dict[int, int]
) -> tuple[list[int], list[int], list[int], list[int]]:
    """1-indexed opening, inbound, closing, unmet (index 0 unused)."""
    opening, inbound, closing, unmet = [0], [0], [0], [0]
    for t, d in enumerate(demand, start=1):
        opening.append(stock)
        inbound.append(arrivals.get(t, 0))
        avail = stock + inbound[t]
        ship = min(d, avail)
        unmet.append(d - ship)
        closing.append(avail - ship)
        stock = avail - ship
    return opening, inbound, closing, unmet


def expected_product(
    p: Product, history: list[int], sc: Scenario, max_orders: int
) -> Expected:
    h = sc.horizon_months
    lead = lead_of(p.lead_time_weeks + sc.delay_weeks)
    demand = forecast(history, sc.method, sc.growth_pct, h + lead + 3)
    safety = [half_up(Fraction(str(sc.safety_months)) * d) for d in demand]
    base: dict[int, int] = {}
    if p.inbound_qty:
        base[1 + lead_of(p.inbound_weeks + sc.delay_weeks)] = p.inbound_qty
    _, _, _, dn_unmet = simulate(p.stock_on_hand, demand, base)
    runout = next((t for t in range(1, h + 1) if dn_unmet[t] > 0), None)
    planned = dict(base)
    orders: list[Planned] = []
    prev = 0
    capacity_flag = None
    first_arrival = None
    for k in range(1, max_orders + 1):
        opening, inbound, closing, unmet = simulate(p.stock_on_hand, demand, planned)
        trig = next(
            (
                t
                for t in range(prev + 1, h + 1)
                if closing[t] < safety[t - 1] or unmet[t] > 0
            ),
            None,
        )
        if trig is None:
            break
        short = next((t for t in range(prev + 1, h + 1) if unmet[t] > 0), h + 1)
        order_t = max(1, trig - lead)
        arrival = order_t + lead
        if arrival <= prev:
            break
        if k == 1:
            first_arrival = arrival
        avail = opening[arrival] + inbound[arrival]
        room = p.capacity - avail
        if room < p.moq:
            capacity_flag = (
                f"Capacity blocks order: room {number(room)} < MOQ {number(p.moq)}"
            )
            break
        cover = sum(demand[arrival - 1 : arrival + 2])
        qty = min(max(p.moq, cover + safety[arrival - 1] - avail), room)
        cost = round(qty * p.unit_cost, 2)
        if k == 1:
            opener = (
                f"Runs out {month(month_key(runout))} without an order."
                if runout
                else f"Falls below safety stock in {month(month_key(trig))}."
            )
        elif short <= h:
            opener = f"Follow-up order {k}: runs out {month(month_key(short))} after the earlier order(s)."
        else:
            opener = f"Follow-up order {k}: falls below safety stock in {month(month_key(trig))}."
        reason = (
            f"{opener} Lead time {p.lead_time_weeks} weeks + delay {sc.delay_weeks} weeks = {lead} month(s): "
            f"order {month(month_key(order_t))}, arrives {month(month_key(arrival))}. "
            f"Order {units(qty)} = 3 months demand {number(cover)} + safety {number(safety[arrival - 1])} "
            f"− available {number(avail)} (MOQ {number(p.moq)}, room {number(room)}). Cost {gbp(cost, pence=True)}."
        )
        orders.append(
            Planned(
                code=p.stock_code,
                k=k,
                order_t=order_t,
                arrival=arrival,
                trigger=trig,
                short=short,
                qty=qty,
                cost_pence=round(cost * 100),
                reason=reason,
            )
        )
        planned[arrival] = planned.get(arrival, 0) + qty
        prev = arrival
    return Expected(
        runout=runout,
        first_arrival=first_arrival,
        value_at_risk=round(sum(dn_unmet[1 : h + 1]) * p.unit_cost, 2),
        orders=orders,
        capacity_flag=capacity_flag,
        do_nothing_unmet=dn_unmet[1 : h + 1],
        demand=demand[:h],
    )


def check_against_oracle(
    data: PlannerData, sc: Scenario, result: ScenarioResult, max_orders: int
) -> None:
    h = sc.horizon_months
    exp = {
        p.stock_code: expected_product(p, data.history[p.stock_code], sc, max_orders)
        for p in data.products
    }
    queue = sorted(
        (o for e in exp.values() for o in e.orders),
        key=lambda o: (o.short, -exp[o.code].value_at_risk, o.code, o.k),
    )
    left = round(sc.budget_gbp * 100)
    funded: set[tuple[str, int]] = set()
    want_plan = []
    for rank, o in enumerate(queue, start=1):
        earlier = o.k == 1 or (o.code, o.k - 1) in funded
        ok = earlier and o.cost_pence <= left
        if ok:
            left -= o.cost_pence
            funded.add((o.code, o.k))
            suffix = ""
        elif not earlier:
            suffix = " Not funded: earlier order not funded."
        else:
            suffix = f" Not funded: {gbp(left / 100, pence=True)} left of budget."
        want_plan.append(
            (
                rank,
                o.code,
                o.k,
                month_key(o.order_t),
                month_key(o.arrival),
                o.qty,
                o.cost_pence,
                ok,
                o.reason + suffix,
            )
        )
    got_plan = [
        (
            x.rank,
            x.stock_code,
            x.order_no,
            x.order_month,
            x.arrival_month,
            x.qty,
            round(x.cost_gbp * 100),
            x.funded,
            x.reason,
        )
        for x in result.plan
    ]
    assert got_plan == want_plan

    by_code = {p.stock_code: p for p in data.products}
    for pr in result.products:
        e = exp[pr.stock_code]
        p = by_code[pr.stock_code]
        price = data.prices[p.stock_code]
        assert [r.unmet for r in pr.months] == e.do_nothing_unmet
        assert pr.runout_month == (month_key(e.runout) if e.runout else None)
        if e.runout is None:
            factor = "none"
        elif e.first_arrival is not None and e.first_arrival > e.runout:
            factor = "lead time"
        elif not e.orders:
            factor = "capacity"
        elif (pr.stock_code, 1) not in funded:
            factor = "budget"
        else:
            factor = "stock"
        assert pr.limiting_factor == factor
        assert [o.order_no for o in pr.orders] == [o.k for o in e.orders]
        assert pr.order == (pr.orders[0] if pr.orders else None)
        for got, o in zip(pr.orders, e.orders, strict=True):
            assert got == result.plan[got.rank - 1]
            if o.k == 1:
                want_factor = factor
            elif o.arrival > o.short:
                want_factor = "lead time"
            elif (o.code, o.k) not in funded:
                want_factor = "budget"
            elif o.short == h + 1:
                want_factor = "none"
            else:
                want_factor = "stock"
            assert got.limiting_factor == want_factor, (o.code, o.k)
        if e.capacity_flag:
            assert e.capacity_flag in pr.flags
        else:
            assert not any(f.startswith("Capacity blocks order") for f in pr.flags)
        arrivals: dict[int, int] = {}
        if p.inbound_qty:
            arrivals[1 + lead_of(p.inbound_weeks + sc.delay_weeks)] = p.inbound_qty
        for o in e.orders:
            if (o.code, o.k) in funded and o.arrival <= h:
                arrivals[o.arrival] = arrivals.get(o.arrival, 0) + o.qty
        opening, inbound, closing, unmet = simulate(p.stock_on_hand, e.demand, arrivals)
        assert [r.unmet for r in pr.plan_months] == unmet[1:]
        assert [r.closing for r in pr.plan_months] == closing[1:]
        assert [r.opening for r in pr.plan_months] == opening[1:]
        assert [r.inbound for r in pr.plan_months] == inbound[1:]
        assert pr.lost_sales_after_plan_gbp == round(sum(unmet) * price, 2)
        assert pr.stockout_months == sum(u > 0 for u in unmet)
        assert pr.at_risk_after_plan == any(unmet)
        gap: set[int] = set()
        if factor == "lead time" and e.runout is not None:
            end = (
                min(e.first_arrival - 1, h)
                if e.first_arrival is not None and (pr.stock_code, 1) in funded
                else h
            )
            gap = set(range(e.runout, end + 1))
        first_funded = bool(e.orders) and (pr.stock_code, 1) in funded
        later = [t for t in range(1, h + 1) if t not in gap] if first_funded else []
        later_units = sum(unmet[t] for t in later)
        later_month = next((t for t in later if unmet[t] > 0), None)
        assert pr.later_shortfall_units == later_units
        assert pr.later_shortfall_month == (
            month_key(later_month) if later_month else None
        )
        assert pr.later_shortfall_gbp == round(later_units * price, 2)
        short_flags = [f for f in pr.flags if f.startswith("Short after plan")]
        if later_month:
            assert short_flags == [
                f"Short after plan: {units(later_units)} from {month(month_key(later_month))}"
            ]
        else:
            assert short_flags == []


# ---------- random worlds ----------


def ri(rng: np.random.Generator, low: int, high: int) -> int:
    return int(rng.integers(low, high + 1))


def pick[T](rng: np.random.Generator, options: list[T]) -> T:
    return options[int(rng.integers(len(options)))]


def world(seed: int) -> tuple[PlannerData, Scenario]:
    rng = np.random.default_rng(4000 + seed)
    products = []
    for i in range(ri(rng, 1, 8)):
        inbound = pick(rng, [0, 0, ri(rng, 1, 1500)])
        products.append(
            Product(
                stock_code=f"R{i:03d}",
                description=f"Toy {i}",
                group="Gifts & small goods",
                unit_cost=pick(rng, [2.0, round(float(rng.uniform(0.01, 40)), 2)]),
                stock_on_hand=pick(rng, [0, 1, 100, ri(rng, 0, 3000)]),
                lead_time_weeks=ri(rng, 0, 12),
                moq=pick(rng, [1, 50, ri(rng, 1, 400)]),
                capacity=pick(rng, [1, 400, ri(rng, 1, 3000), 5000]),
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
        delay_weeks=pick(rng, [0, 0, 26, ri(rng, 0, 26)]),
        budget_gbp=pick(rng, [0, 1_000_000, ri(rng, 0, 20000), ri(rng, 0, 2000)]),
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


def check_structure(data: PlannerData, result: ScenarioResult, max_orders: int) -> None:
    sc = result.scenario
    h = sc.horizon_months
    by_code = {p.stock_code: p for p in data.products}
    total = 0
    for pr in result.products:
        p = by_code[pr.stock_code]
        lead = lead_of(p.lead_time_weeks + sc.delay_weeks)
        orders = pr.orders
        assert len(orders) <= max_orders
        assert [o.order_no for o in orders] == list(range(1, len(orders) + 1))
        arrivals = [month_index(o.arrival_month) for o in orders]
        assert all(b > a for a, b in itertools.pairwise(arrivals))
        ranks = [o.rank for o in orders]
        assert ranks == sorted(ranks)
        for o in orders:
            assert o.stock_code == pr.stock_code
            assert month_index(o.arrival_month) == month_index(o.order_month) + lead
            assert o.qty >= p.moq and o.qty > 0
            assert o.cost_gbp == round(o.qty * p.unit_cost, 2)
            if o.order_no > 1:
                # trigger_k > previous arrival ≥ 1 + L, so the order is never pulled to month 1 and lands in the horizon
                assert month_index(o.order_month) >= 2
                assert month_index(o.arrival_month) <= h
                assert o.limiting_factor in ("stock", "budget", "none", "lead time")
                assert o.reason.startswith(f"Follow-up order {o.order_no}: ")
                if o.funded:
                    assert orders[o.order_no - 2].funded
            else:
                assert o.limiting_factor == pr.limiting_factor
        total += len(orders)
        for a, b in zip(pr.plan_months, pr.months, strict=True):
            assert a.unmet <= b.unmet
            assert a.demand == b.demand
        funded_in = sum(
            o.qty for o in orders if o.funded and month_index(o.arrival_month) <= h
        )
        assert (
            sum(r.inbound for r in pr.plan_months)
            == sum(r.inbound for r in pr.months) + funded_in
        )
    assert len(result.plan) == total
    assert [x.rank for x in result.plan] == list(range(1, total + 1))
    k = result.kpis
    funded = [x for x in result.plan if x.funded]
    assert k.funded_spend_gbp == round(sum(x.cost_gbp for x in funded), 2)
    assert k.funded_spend_gbp <= sc.budget_gbp + 1e-6
    assert k.suggested_spend_gbp == round(sum(x.cost_gbp for x in result.plan), 2)
    assert k.unfunded_orders == len(result.plan) - len(funded)
    assert k.unfunded_gbp == round(
        sum(x.cost_gbp for x in result.plan if not x.funded), 2
    )
    prods = result.products
    assert k.products_at_risk == sum(p.at_risk_after_plan for p in prods)
    assert k.stockout_months == sum(p.stockout_months for p in prods)
    assert k.lost_sales_gbp == round(sum(p.lost_sales_gbp for p in prods), 2)
    assert k.lost_sales_after_plan_gbp == round(
        sum(p.lost_sales_after_plan_gbp for p in prods), 2
    )
    assert k.later_shortfall_gbp == round(sum(p.later_shortfall_gbp for p in prods), 2)
    for res in prods:
        price = data.prices[res.stock_code]
        assert res.lost_sales_after_plan_gbp == round(
            sum(r.unmet for r in res.plan_months) * price, 2
        )
        assert res.stockout_months == sum(r.unmet > 0 for r in res.plan_months)
        assert res.later_shortfall_gbp <= res.lost_sales_after_plan_gbp + 1e-9


@pytest.mark.parametrize("seed", range(80))
def test_random_worlds_match_oracle(seed: int) -> None:
    data, sc = world(seed)
    result = run(data, sc)
    check_structure(data, result, MAX_ORDERS)
    check_against_oracle(data, sc, result, MAX_ORDERS)


@pytest.mark.parametrize("max_orders", [1, 2, 3])
@pytest.mark.parametrize("seed", range(25))
def test_random_worlds_smaller_caps(seed: int, max_orders: int) -> None:
    data, sc = world(seed)
    result = run(data, sc, max_orders=max_orders)
    check_structure(data, result, max_orders)
    check_against_oracle(data, sc, result, max_orders)


@pytest.mark.parametrize("seed", range(40))
def test_max_orders_one_is_the_single_order_plan(seed: int) -> None:
    """max_orders=1: one line per product with an order, identical to order 1 of a 4-order run (rank, funding and
    the funding suffix aside), and ranked by (run-out or H + 1, −value at risk, code) as DEC-09."""
    data, sc = world(seed)
    one, four = run(data, sc, max_orders=1), run(data, sc)
    keep = {"rank", "funded", "reason", "limiting_factor"}
    for a, b in zip(one.products, four.products, strict=True):
        assert a.stock_code == b.stock_code
        assert len(a.orders) <= 1
        assert (a.order is None) == (b.order is None)
        if a.order is not None and b.order is not None:
            assert a.order.model_dump(exclude=keep) == b.order.model_dump(exclude=keep)
            base = a.order.reason.split(" Not funded:")[0]
            assert b.order.reason.split(" Not funded:")[0] == base
        assert a.months == b.months
        assert a.runout_month == b.runout_month
        assert a.value_at_risk_gbp == b.value_at_risk_gbp
        assert a.lost_sales_gbp == b.lost_sales_gbp
        assert a.tied_up_gbp == b.tied_up_gbp
    h = sc.horizon_months
    by = {p.stock_code: p for p in one.products}
    keys = [
        (
            month_index(by[x.stock_code].runout_month or month_key(h + 1)),
            -by[x.stock_code].value_at_risk_gbp,
            x.stock_code,
        )
        for x in one.plan
    ]
    assert keys == sorted(keys)
    assert all(x.order_no == 1 for x in one.plan)


@pytest.mark.parametrize("seed", range(30))
def test_full_budget_funds_every_order_and_lowers_unmet(seed: int) -> None:
    data, sc = world(seed)
    rich = run(data, sc.model_copy(update={"budget_gbp": 1_000_000}))
    if rich.kpis.suggested_spend_gbp <= 1_000_000:
        assert all(x.funded for x in rich.plan)
        assert rich.kpis.unfunded_orders == 0
    broke = run(data, sc.model_copy(update={"budget_gbp": 0}))
    assert not any(x.funded for x in broke.plan)
    assert all(p.plan_months == p.months for p in broke.products)
    assert [
        x.model_dump(exclude={"funded", "reason", "limiting_factor"})
        for x in broke.plan
    ] == [
        x.model_dump(exclude={"funded", "reason", "limiting_factor"}) for x in rich.plan
    ]
    if rich.kpis.suggested_spend_gbp <= 1_000_000:
        for a, b in zip(rich.products, broke.products, strict=True):
            for x, y in zip(a.plan_months, b.plan_months, strict=True):
                assert x.unmet <= y.unmet


@pytest.mark.parametrize("seed", range(10))
def test_repeat_run_is_identical_and_pure(seed: int) -> None:
    data, sc = world(seed)
    snapshot = data.model_dump()
    assert run(data, sc) == run(data, sc)
    assert data.model_dump() == snapshot


# ---------- real data per preset ----------


@pytest.fixture(scope="module")
def real() -> PlannerData:
    return load(DATA)


@pytest.fixture(scope="module")
def preset_runs(real: PlannerData) -> dict[str, ScenarioResult]:
    return {name: run(real, s) for name, s in PRESETS.items()}


def test_preset_budgets() -> None:
    assert BASELINE.budget_gbp == 350_000
    assert PRESETS["Baseline"] == BASELINE
    assert PRESETS["Tight budget"].budget_gbp == 175_000
    for name, s in PRESETS.items():
        if name != "Tight budget":
            assert s.budget_gbp == 350_000, name


@pytest.mark.parametrize("name", list(PRESETS))
def test_real_preset_structure_and_oracle(
    name: str, real: PlannerData, preset_runs: dict[str, ScenarioResult]
) -> None:
    result = preset_runs[name]
    check_structure(real, result, MAX_ORDERS)
    check_against_oracle(real, PRESETS[name], result, MAX_ORDERS)
    assert any(len(p.orders) > 1 for p in result.products), name


@pytest.mark.parametrize("name", list(PRESETS))
def test_real_preset_max_orders_one(name: str, real: PlannerData) -> None:
    result = run(real, PRESETS[name], max_orders=1)
    check_structure(real, result, 1)
    check_against_oracle(real, PRESETS[name], result, 1)


def test_real_baseline_84347(preset_runs: dict[str, ScenarioResult]) -> None:
    p = of(preset_runs["Baseline"], "84347")
    assert p.limiting_factor == "lead time"
    assert p.orders[1].arrival_month == "2012-08"
    assert p.orders[1].funded
    assert p.orders[0].funded
    assert f"Short after plan: {units(2948)} from Nov 2012" in p.flags


def test_real_preset_orderings(preset_runs: dict[str, ScenarioResult]) -> None:
    base = preset_runs["Baseline"].kpis
    assert (
        preset_runs["Efficiency"].kpis.lost_sales_after_plan_gbp
        > base.lost_sales_after_plan_gbp
    )
    assert preset_runs["Tight budget"].kpis.products_at_risk > base.products_at_risk
    assert (
        preset_runs["Tight budget"].kpis.lost_sales_after_plan_gbp
        >= base.lost_sales_after_plan_gbp
    )
    for name, r in preset_runs.items():
        assert r.kpis.funded_spend_gbp <= r.kpis.budget_gbp, name
        assert r.kpis.lost_sales_after_plan_gbp <= r.kpis.lost_sales_gbp, name
