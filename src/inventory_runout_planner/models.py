from typing import Literal

from inventory_runout_planner.fmt import number
from pydantic import BaseModel, Field

Method = Literal["seasonal_naive", "trailing_3m"]
LimitingFactor = Literal["stock", "lead time", "budget", "capacity", "none"]

INPUT_RULES = [
    ("growth_pct", "Demand growth (%) must be between -50 and 100", -50, 100),
    ("delay_weeks", "Supplier delay (weeks) must be between 0 and 26", 0, 26),
    ("budget_gbp", "Budget (£) must be between 0 and 1 000 000", 0, 1_000_000),
    ("safety_months", "Safety stock (months) must be between 0 and 6", 0, 6),
]


class Product(BaseModel):
    stock_code: str
    description: str
    group: str
    unit_cost: float = Field(gt=0)
    stock_on_hand: int = Field(ge=0)
    lead_time_weeks: int = Field(ge=0, le=12)
    moq: int = Field(ge=1)
    capacity: int = Field(ge=1)
    inbound_qty: int = Field(ge=0)
    inbound_weeks: int = Field(ge=0)


class PlannerData(BaseModel):
    products: list[Product]
    history: dict[str, list[int]]
    history_months: list[str]


class Scenario(BaseModel):
    horizon_months: int = Field(ge=6, le=12)
    growth_pct: float = Field(ge=-50, le=100)
    delay_weeks: int = Field(ge=0, le=26)
    budget_gbp: float = Field(ge=0, le=1_000_000)
    safety_months: float = Field(ge=0, le=6)
    method: Method


class MonthRow(BaseModel):
    month: str
    demand: int
    opening: int
    inbound: int
    shipped: int
    unmet: int
    closing: int


class ReorderLine(BaseModel):
    rank: int
    stock_code: str
    description: str
    order_month: str
    arrival_month: str
    qty: int
    unit_cost: float
    cost_gbp: float
    funded: bool
    limiting_factor: str
    reason: str


class ProductResult(BaseModel):
    stock_code: str
    description: str
    group: str
    months: list[MonthRow]
    plan_months: list[MonthRow]
    runout_month: str | None
    lead_months: int
    inbound_month: str | None
    order: ReorderLine | None
    limiting_factor: LimitingFactor
    flags: list[str]
    value_at_risk_gbp: float
    cover_months: float
    order_now: bool


class Kpis(BaseModel):
    products_at_risk: int
    earliest_runout_code: str | None
    earliest_runout_month: str | None
    earliest_limiting_factor: str | None
    funded_spend_gbp: float
    suggested_spend_gbp: float
    budget_gbp: float
    unfunded_orders: int
    stock_value_gbp: float


class ScenarioResult(BaseModel):
    scenario: Scenario
    products: list[ProductResult]
    plan: list[ReorderLine]
    kpis: Kpis


def scenario_errors(raw: dict[str, float | int | str]) -> list[str]:
    """DEC-10 messages for the four typed inputs, in field order (horizon and method come from bounded widgets)."""
    errors = []
    for key, message, low, high in INPUT_RULES:
        try:
            value = float(raw[key])
        except ValueError:
            errors.append(f"{message} — you entered {raw[key]}.")
            continue
        fractional_delay = key == "delay_weeks" and not value.is_integer()
        if not low <= value <= high or fractional_delay:
            entered = number(value) if value.is_integer() else f"{value:g}"
            errors.append(f"{message} — you entered {entered}.")
    return errors
