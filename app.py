"""Inventory run-out planner: entry file with the shared sidebar, notices and KPI strip (DEC-14, DEC-15)."""

import os

import streamlit as st
from inventory_runout_planner.data import DataError
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import Scenario, scenario_errors
from inventory_runout_planner.presets import ATTRIBUTION, PRESETS
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import (
    DEFAULT_DATA_DIR,
    load_data,
    run_scenario,
)

st.set_page_config(
    page_title="Inventory run-out planner", page_icon="📦", layout="wide"
)
theme.apply()

INPUT_KEYS = list(Scenario.model_fields)
CUSTOM = "Custom"
METHOD_LABELS = {
    "seasonal_naive": "Seasonal naive (same month last year)",
    "trailing_3m": "Trailing 3-month average",
}


def load_preset(name: str) -> None:
    for key, value in PRESETS[name].model_dump().items():
        st.session_state[key] = value


def on_preset() -> None:
    if st.session_state["preset"] != CUSTOM:
        load_preset(st.session_state["preset"])


def on_edit() -> None:
    st.session_state["preset"] = CUSTOM


def on_reset() -> None:
    st.session_state["preset"] = "Baseline"
    load_preset("Baseline")


if "preset" not in st.session_state:
    on_reset()
if "product" in st.session_state:
    st.session_state["product"] = st.session_state[
        "product"
    ]  # keep the Forecast pick across pages

navigation = st.navigation(
    [
        st.Page(
            "app_pages/overview.py",
            title="Overview",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            "app_pages/forecast.py", title="Forecast", icon=":material/show_chart:"
        ),
        st.Page("app_pages/scenarios.py", title="Scenarios", icon=":material/tune:"),
        st.Page(
            "app_pages/reorder_plan.py",
            title="Reorder plan",
            icon=":material/shopping_cart:",
        ),
        st.Page(
            "app_pages/methodology.py", title="Methodology", icon=":material/functions:"
        ),
    ]
)

with st.sidebar:
    st.markdown("### Scenario")
    st.selectbox("Preset", [*PRESETS, CUSTOM], key="preset", on_change=on_preset)
    st.slider(
        "Horizon (months)",
        min_value=6,
        max_value=12,
        key="horizon_months",
        on_change=on_edit,
    )
    st.number_input(
        "Demand growth (%)", key="growth_pct", step=5.0, format="%g", on_change=on_edit
    )
    st.number_input(
        "Supplier delay (weeks)", key="delay_weeks", step=1, on_change=on_edit
    )
    st.number_input(
        "Budget (£)", key="budget_gbp", step=1000.0, format="%.0f", on_change=on_edit
    )
    st.number_input(
        "Safety stock (months)",
        key="safety_months",
        step=0.5,
        format="%g",
        on_change=on_edit,
    )
    st.radio(
        "Forecast method",
        list(METHOD_LABELS),
        key="method",
        format_func=METHOD_LABELS.__getitem__,
        on_change=on_edit,
    )
    st.button("Reset to Baseline", key="reset", on_click=on_reset, width="stretch")
    st.divider()
    st.caption(
        "Planning as of 1 Dec 2011 · demand is real (UCI Online Retail II, last full month Nov 2011); stock on hand, "
        "lead times, MOQ, unit cost, capacity and inbound orders are synthetic · money in GBP"
    )
    st.caption(ATTRIBUTION)

st.markdown(
    f'<div class="page-head"><h1>{navigation.title}</h1>'
    '<span class="synthetic-badge">Synthetic stock data — demonstration only</span>'
    '<span class="as-of">Data as of Dec 2011</span></div>',
    unsafe_allow_html=True,
)

directory = os.environ.get("RUNOUT_DATA_DIR", str(DEFAULT_DATA_DIR))
try:
    data = load_data(directory)
except DataError as e:
    st.error(str(e))
    st.stop()

raw = {key: st.session_state[key] for key in INPUT_KEYS}
errors = scenario_errors(raw)
if errors:
    for message in errors:
        st.error(message)
    st.stop()

scenario = Scenario.model_validate(raw)
result = run_scenario(scenario, directory)
st.session_state["data"] = data
st.session_state["result"] = result
st.session_state["data_dir"] = directory

k = result.kpis
cards = [
    (
        "Products at risk",
        number(k.products_at_risk),
        None,
        (
            "Products at risk = products that still lose sales after the plan, before the next order's 3-month cover ends "
            "(unfunded, lead-time blocked, capacity-blocked or too small an order)."
        ),
    ),
    (
        "Earliest run-out",
        month(k.earliest_runout_month)
        if k.earliest_runout_month
        else "None in horizon",
        k.earliest_runout_code,
        (
            "Earliest run-out = first month where forecast demand > opening stock + inbound, if nothing is ordered "
            "(ties: higher value at risk first)."
        ),
    ),
    (
        "Purchase spend",
        gbp(k.funded_spend_gbp),
        f"of {gbp(k.budget_gbp)}",
        (
            "Purchase spend = Σ (qty × unit cost) of funded orders; orders are funded in rank order while they fit "
            f"the remaining budget. Suggested in total: {gbp(k.suggested_spend_gbp)}."
        ),
    ),
    (
        "Unfunded orders",
        number(k.unfunded_orders),
        f"{gbp(k.unfunded_gbp)} short" if k.unfunded_orders else None,
        "Unfunded orders = suggested orders whose cost > budget left when their turn in the ranking came.",
    ),
    (
        "Lost sales after plan",
        gbp(k.lost_sales_after_plan_gbp),
        f"{gbp(k.lost_sales_gbp)} if nothing ordered",
        (
            "Lost sales = unmet units × median selling price (real UCI prices). After plan = with the funded orders, "
            f"up to the end of each order's 3-month cover; if nothing is ordered = whole horizon. "
            f"Later shortfalls (need a further order): {gbp(k.later_shortfall_gbp)}, not included."
        ),
    ),
]
if navigation.title == "Overview":
    cards.pop(1)
for column, (label, value, sub, help_text) in zip(
    st.columns(len(cards)), cards, strict=True
):
    warn = label == "Unfunded orders" and k.unfunded_orders > 0
    (column.container(key="kpi-warn") if warn else column).metric(
        label,
        value,
        delta=sub,
        delta_color="off",
        delta_arrow="off",
        help=help_text,
    )

navigation.run()
