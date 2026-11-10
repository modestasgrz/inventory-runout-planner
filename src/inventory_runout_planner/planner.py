import math
from fractions import Fraction

from inventory_runout_planner.fmt import gbp, month, number, units
from inventory_runout_planner.models import (
    Backtest,
    BacktestRow,
    Kpis,
    LimitingFactor,
    Method,
    MonthRow,
    PlannerData,
    Product,
    ProductResult,
    ReorderLine,
    Scenario,
    ScenarioResult,
    Stockout,
)
from pydantic import BaseModel

DAYS_PER_MONTH = 30.44
FIRST_MONTH = 2011 * 12 + 11  # Dec 2011 as a month count
OVERSTOCK_MONTHS = 6.0
COVER_MONTHS = 3


class Draft(BaseModel):
    """One product before ranking and funding."""

    product: Product
    rows: list[MonthRow]
    arrivals: dict[int, int]
    runout: int | None
    lead: int
    inbound_t: int | None
    arrival: int | None
    line: ReorderLine | None
    flags: list[str]
    value_at_risk: float
    cover: float


def half_up(value: Fraction) -> int:
    """Exact half-up rounding; callers build value from str() of the inputs so float ties stay ties."""
    return math.floor(value + Fraction(1, 2))


def month_key(t: int) -> str:
    """Month index t (1 = Dec 2011) as 'YYYY-MM'."""
    count = FIRST_MONTH + t - 1
    return f"{count // 12}-{count % 12 + 1:02d}"


def lead_months(weeks: int) -> int:
    return math.ceil(weeks * 7 / DAYS_PER_MONTH)


def forecast(
    history: list[int], method: str, growth_pct: float, months: int
) -> list[int]:
    """DEC-07: months 1..months; history is the 24 values oldest first, so history[-12] is Dec 2010."""
    factor = 1 + Fraction(str(growth_pct)) / 100
    if method == "seasonal_naive":
        base = [Fraction(history[-12 + (t % 12)]) for t in range(months)]
    else:
        base = [Fraction(sum(history[-3:]), 3)] * months
    return [half_up(b * factor) for b in base]


def project(stock: int, demand: list[int], arrivals: dict[int, int]) -> list[MonthRow]:
    rows = []
    opening = stock
    for t, wanted in enumerate(demand, start=1):
        inbound = arrivals.get(t, 0)
        available = opening + inbound
        shipped = min(wanted, available)
        rows.append(
            MonthRow(
                month=month_key(t),
                demand=wanted,
                opening=opening,
                inbound=inbound,
                shipped=shipped,
                unmet=wanted - shipped,
                closing=available - shipped,
            )
        )
        opening = available - shipped
    return rows


def run(data: PlannerData, scenario: Scenario) -> ScenarioResult:
    horizon = scenario.horizon_months
    drafts = []
    for p in data.products:
        lead = lead_months(p.lead_time_weeks + scenario.delay_weeks)
        span = horizon + lead + COVER_MONTHS
        demand = forecast(
            data.history[p.stock_code], scenario.method, scenario.growth_pct, span
        )
        inbound_t = (
            1 + lead_months(p.inbound_weeks + scenario.delay_weeks)
            if p.inbound_qty
            else None
        )
        arrivals = {inbound_t: p.inbound_qty} if inbound_t else {}
        extended = project(p.stock_on_hand, demand, arrivals)
        rows = extended[:horizon]
        safety = [half_up(Fraction(str(scenario.safety_months)) * d) for d in demand]
        runout = next((t for t, r in enumerate(rows, start=1) if r.unmet > 0), None)
        trigger = next(
            (
                t
                for t, r in enumerate(rows, start=1)
                if r.closing < safety[t - 1] or r.unmet > 0
            ),
            None,
        )
        flags = []
        if inbound_t and inbound_t > horizon:
            flags.append("Inbound arrives after horizon")
        mean_demand = sum(demand[:horizon]) / horizon
        cover = (
            p.stock_on_hand / mean_demand
            if mean_demand
            else (math.inf if p.stock_on_hand else 0.0)
        )
        if cover > OVERSTOCK_MONTHS:
            flags.append(
                f"Overstocked: {cover:.1f} months of cover"
                if math.isfinite(cover)
                else "Overstocked: no forecast demand"
            )
        line = None
        arrival = None
        if trigger:
            order_t = max(1, trigger - lead)
            arrival = order_t + lead
            at_arrival = extended[arrival - 1]
            available = at_arrival.opening + at_arrival.inbound
            cover_demand = sum(demand[arrival - 1 : arrival - 1 + COVER_MONTHS])
            room = p.capacity - available
            if room < p.moq:
                flags.append(
                    f"Capacity blocks order: room {number(room)} < MOQ {number(p.moq)}"
                )
            else:
                qty = min(
                    max(p.moq, cover_demand + safety[arrival - 1] - available), room
                )
                cost = round(qty * p.unit_cost, 2)
                opening_sentence = (
                    f"Runs out {month(month_key(runout))} without an order."
                    if runout
                    else f"Falls below safety stock in {month(month_key(trigger))}."
                )
                line = ReorderLine(
                    rank=0,
                    stock_code=p.stock_code,
                    description=p.description,
                    order_month=month_key(order_t),
                    arrival_month=month_key(arrival),
                    qty=qty,
                    unit_cost=p.unit_cost,
                    cost_gbp=cost,
                    funded=False,
                    limiting_factor="",
                    reason=(
                        f"{opening_sentence} Lead time {p.lead_time_weeks} weeks + delay {scenario.delay_weeks} weeks"
                        f" = {lead} month(s): order {month(month_key(order_t))}, arrives {month(month_key(arrival))}."
                        f" Order {units(qty)} = 3 months demand {number(cover_demand)} + safety {number(safety[arrival - 1])}"
                        f" − available {number(available)} (MOQ {number(p.moq)}, room {number(room)})."
                        f" Cost {gbp(cost, pence=True)}."
                    ),
                )
        drafts.append(
            Draft(
                product=p,
                rows=rows,
                arrivals=arrivals,
                runout=runout,
                lead=lead,
                inbound_t=inbound_t,
                arrival=arrival,
                line=line,
                flags=flags,
                value_at_risk=round(sum(r.unmet for r in rows) * p.unit_cost, 2),
                cover=cover,
            )
        )

    drafts.sort(
        key=lambda d: (d.runout or horizon + 1, -d.value_at_risk, d.product.stock_code)
    )
    remaining = scenario.budget_gbp
    ranked_lines: dict[str, ReorderLine] = {}
    plan: list[ReorderLine] = []
    for d in drafts:
        if d.line is None:
            continue
        funded = d.line.cost_gbp <= remaining + 1e-9
        suffix = (
            ""
            if funded
            else f" Not funded: {gbp(remaining, pence=True)} left of budget."
        )
        if funded:
            remaining = round(remaining - d.line.cost_gbp, 2)
        ranked = d.line.model_copy(
            update={
                "rank": len(plan) + 1,
                "funded": funded,
                "reason": d.line.reason + suffix,
            }
        )
        plan.append(ranked)
        ranked_lines[d.product.stock_code] = ranked

    products = []
    for d in drafts:
        p, rows, runout, arrival = d.product, d.rows, d.runout, d.arrival
        ranked_line = ranked_lines.get(p.stock_code)
        factor: LimitingFactor
        if runout is None:
            factor = "none"
        elif arrival is not None and arrival > runout:
            factor = "lead time"
        elif ranked_line is None:
            factor = "capacity"
        elif not ranked_line.funded:
            factor = "budget"
        else:
            factor = "stock"
        if ranked_line is not None:
            ranked_line = ranked_line.model_copy(update={"limiting_factor": factor})
            plan[ranked_line.rank - 1] = ranked_line
        plan_rows = rows
        if (
            ranked_line is not None
            and ranked_line.funded
            and arrival is not None
            and arrival <= horizon
        ):
            plan_arrivals = dict(d.arrivals)
            plan_arrivals[arrival] = plan_arrivals.get(arrival, 0) + ranked_line.qty
            plan_rows = project(
                p.stock_on_hand, [r.demand for r in rows], plan_arrivals
            )
        sell_price = data.prices[p.stock_code]
        cover_end = (
            min(horizon, arrival + COVER_MONTHS - 1)
            if ranked_line is not None
            and ranked_line.funded
            and arrival is not None
            and arrival <= horizon
            else horizon
        )
        window, later = plan_rows[:cover_end], plan_rows[cover_end:]
        later_units = sum(r.unmet for r in later)
        later_month = next((r.month for r in later if r.unmet), None)
        flags = list(d.flags)
        if later_month:
            flags.append(
                f"Later shortfall not covered: {units(later_units)} from {month(later_month)}"
            )
        stockout = None
        if factor == "lead time" and runout is not None and arrival is not None:
            gap = rows[runout - 1 : min(arrival - 1, horizon)]
            gap_units = sum(r.unmet for r in gap)
            stockout = Stockout(
                start_month=gap[0].month,
                end_month=gap[-1].month,
                months=len(gap),
                units=gap_units,
                lost_sales_gbp=round(gap_units * sell_price, 2),
            )
        tied_up = 0.0
        if any(f.startswith("Overstocked") for f in d.flags):
            normal = half_up(
                Fraction(int(OVERSTOCK_MONTHS) * sum(r.demand for r in rows), horizon)
            )
            tied_up = round(max(p.stock_on_hand - normal, 0) * p.unit_cost, 2)
        stockout_months = sum(r.unmet > 0 for r in window)
        products.append(
            ProductResult(
                stock_code=p.stock_code,
                description=p.description,
                group=p.group,
                months=rows,
                plan_months=plan_rows,
                runout_month=month_key(runout) if runout else None,
                lead_months=d.lead,
                inbound_month=month_key(d.inbound_t) if d.inbound_t else None,
                order=ranked_line,
                limiting_factor=factor,
                flags=flags,
                value_at_risk_gbp=d.value_at_risk,
                cover_months=d.cover,
                order_now=runout is not None and runout <= d.lead + 1,
                sell_price=sell_price,
                lost_sales_gbp=round(sum(r.unmet for r in rows) * sell_price, 2),
                lost_sales_after_plan_gbp=round(
                    sum(r.unmet for r in window) * sell_price, 2
                ),
                later_shortfall_units=later_units,
                later_shortfall_month=later_month,
                later_shortfall_gbp=round(later_units * sell_price, 2),
                stockout=stockout,
                stockout_months=stockout_months,
                at_risk_after_plan=stockout_months > 0,
                tied_up_gbp=tied_up,
            )
        )

    with_runout = [r for r in products if r.runout_month]
    earliest = with_runout[0] if with_runout else None
    kpis = Kpis(
        products_at_risk=sum(r.at_risk_after_plan for r in products),
        earliest_runout_code=earliest.stock_code if earliest else None,
        earliest_runout_month=earliest.runout_month if earliest else None,
        earliest_limiting_factor=earliest.limiting_factor if earliest else None,
        funded_spend_gbp=round(sum(line.cost_gbp for line in plan if line.funded), 2),
        suggested_spend_gbp=round(sum(line.cost_gbp for line in plan), 2),
        budget_gbp=scenario.budget_gbp,
        unfunded_orders=sum(not line.funded for line in plan),
        stock_value_gbp=round(
            sum(p.stock_on_hand * p.unit_cost for p in data.products), 2
        ),
        unfunded_gbp=round(sum(line.cost_gbp for line in plan if not line.funded), 2),
        lost_sales_gbp=round(sum(r.lost_sales_gbp for r in products), 2),
        lost_sales_after_plan_gbp=round(
            sum(r.lost_sales_after_plan_gbp for r in products), 2
        ),
        later_shortfall_gbp=round(sum(r.later_shortfall_gbp for r in products), 2),
        tied_up_gbp=round(sum(r.tied_up_gbp for r in products), 2),
        stockout_months=sum(r.stockout_months for r in products),
    )
    return ScenarioResult(scenario=scenario, products=products, plan=plan, kpis=kpis)


def backtest(data: PlannerData, method: Method) -> Backtest:
    """DEC-19: forecast Dec 2010–Nov 2011 from the first 12 history months (growth 0) against the actual units."""
    rows = []
    for p in data.products:
        history = data.history[p.stock_code]
        predicted = forecast(history[:12], method, 0, 12)
        actual = history[12:]
        errors = [abs(a - f) for a, f in zip(actual, predicted, strict=True)]
        ratios = [Fraction(e, a) for e, a in zip(errors, actual, strict=True) if a]
        rows.append(
            BacktestRow(
                stock_code=p.stock_code,
                description=p.description,
                mape_pct=float(sum(ratios) / len(ratios) * 100) if ratios else None,
                abs_error_units=sum(errors),
                actual_units=sum(actual),
            )
        )
    total = sum(r.actual_units for r in rows)
    overall = (
        Fraction(sum(r.abs_error_units for r in rows) * 100, total) if total else 0
    )
    return Backtest(
        method=method, as_of="2010-12", rows=rows, overall_pct=round(float(overall), 2)
    )
