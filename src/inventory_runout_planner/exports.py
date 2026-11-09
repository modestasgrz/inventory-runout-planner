import pandas as pd
from inventory_runout_planner.models import (
    MonthRow,
    PlannerData,
    ReorderLine,
    ScenarioResult,
)

AS_OF = "2011-12-01"


def tables(data: PlannerData, result: ScenarioResult) -> dict[str, pd.DataFrame]:
    """DEC-13 export tables, raw numbers."""
    projection = [
        {"stock_code": p.stock_code, "projection": name, **r.model_dump()}
        for p in result.products
        for name, rows in (("do_nothing", p.months), ("with_plan", p.plan_months))
        for r in rows
    ]
    settings = [
        ("as_of", AS_OF),
        *result.scenario.model_dump().items(),
        *result.kpis.model_dump().items(),
    ]
    return {
        "products.csv": pd.DataFrame(
            [p.model_dump() | {"stock_data": "synthetic"} for p in data.products]
        ),
        "monthly_projection.csv": pd.DataFrame(
            projection, columns=["stock_code", "projection", *MonthRow.model_fields]
        ),
        "scenario.csv": pd.DataFrame(settings, columns=["key", "value"]),
        "reorder_plan.csv": pd.DataFrame(
            [line.model_dump() for line in result.plan],
            columns=list(ReorderLine.model_fields),
        ),
    }
