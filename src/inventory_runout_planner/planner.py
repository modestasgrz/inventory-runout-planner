import math
from decimal import ROUND_HALF_UP, Decimal

from inventory_runout_planner.fmt import gbp, month, number, units
from inventory_runout_planner.models import (
    Kpis,
    LimitingFactor,
    MonthRow,
    PlannerData,
    Product,
    ProductResult,
    ReorderLine,
    Scenario,
    ScenarioResult,
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

    def rank_key(self, horizon: int) -> tuple[int, float, str]:
        return (
            self.runout or horizon + 1,
            -self.value_at_risk,
            self.product.stock_code,
        )


def half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal(1), ROUND_HALF_UP))


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
    factor = 1 + growth_pct / 100
    if method == "seasonal_naive":
        base = [float(history[-12 + (t % 12)]) for t in range(months)]
    else:
        base = [sum(history[-3:]) / 3] * months
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
        safety = [half_up(scenario.safety_months * d) for d in demand]
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
            flags.append(f"Overstocked: {cover:.1f} months of cover")
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

    drafts.sort(key=lambda d: d.rank_key(horizon))
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
                flags=d.flags,
                value_at_risk_gbp=d.value_at_risk,
                cover_months=d.cover,
            )
        )

    at_risk = [r for r in products if r.runout_month]
    earliest = at_risk[0] if at_risk else None
    kpis = Kpis(
        products_at_risk=len(at_risk),
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
    )
    return ScenarioResult(scenario=scenario, products=products, plan=plan, kpis=kpis)
