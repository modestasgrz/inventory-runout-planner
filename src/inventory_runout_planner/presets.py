from inventory_runout_planner.models import Scenario

BASELINE_BUDGET_GBP = 100_000

BASELINE = Scenario(
    horizon_months=12,
    growth_pct=0,
    delay_weeks=0,
    budget_gbp=BASELINE_BUDGET_GBP,
    safety_months=1.0,
    method="seasonal_naive",
)
PRESETS: dict[str, Scenario] = {
    "Baseline": BASELINE,
    "Peak season +25%": BASELINE.model_copy(update={"growth_pct": 25}),
    "Supplier delay +3 weeks": BASELINE.model_copy(update={"delay_weeks": 3}),
    "Tight budget": BASELINE.model_copy(update={"budget_gbp": BASELINE_BUDGET_GBP / 2}),
    "Efficiency": BASELINE.model_copy(update={"safety_months": 0.5}),
}
ATTRIBUTION = (
    "Demand data: Online Retail II, Chen, D. (2012), UCI Machine Learning Repository, CC BY 4.0, "
    "https://doi.org/10.24432/C5CG6D. Stock, lead times, MOQ, unit cost, capacity and inbound orders are synthetic."
)
