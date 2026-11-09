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
    product_label,
    run_scenario,
)

st.set_page_config(
    page_title="Inventory run-out planner", page_icon="📦", layout="wide"
)
theme.apply()

INPUT_KEYS = list(Scenario.model_fields)
METHOD_LABELS = {
    "seasonal_naive": "Seasonal naive (same month last year)",
    "trailing_3m": "Trailing 3-month average",
}


def load_preset(name: str) -> None:
    for key, value in PRESETS[name].model_dump().items():
        st.session_state[key] = value


def on_preset() -> None:
    load_preset(st.session_state["preset"])


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
    st.selectbox("Preset", list(PRESETS), key="preset", on_change=on_preset)
    st.slider("Horizon (months)", min_value=6, max_value=12, key="horizon_months")
    st.number_input("Demand growth (%)", key="growth_pct", step=5.0, format="%g")
    st.number_input("Supplier delay (weeks)", key="delay_weeks", step=1)
    st.number_input("Budget (£)", key="budget_gbp", step=1000.0, format="%.0f")
    st.number_input("Safety stock (months)", key="safety_months", step=0.5, format="%g")
    st.radio(
        "Forecast method",
        list(METHOD_LABELS),
        key="method",
        format_func=METHOD_LABELS.__getitem__,
    )
    if {key: st.session_state[key] for key in INPUT_KEYS} != PRESETS[
        st.session_state["preset"]
    ].model_dump():
        st.caption(
            f"Edited: the inputs no longer match the {st.session_state['preset']} preset. Use Reset or pick another preset."
        )
    st.button("Reset to Baseline", key="reset", on_click=on_reset, width="stretch")
    st.divider()
    st.caption(ATTRIBUTION)

st.title(navigation.title)
st.markdown(
    '<div class="notice-row"><span class="synthetic-badge">Synthetic stock data — demonstration only</span>'
    "<span>Planning as of 1 Dec 2011 · demand is real (UCI Online Retail II, last full month Nov 2011); stock on hand, "
    "lead times, MOQ, unit cost, capacity and inbound orders are synthetic · money in GBP</span></div>",
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
descriptions = {p.stock_code: p.description for p in result.products}
earliest = (
    f"{month(k.earliest_runout_month)} · {product_label(descriptions[k.earliest_runout_code], k.earliest_runout_code)}"
    if k.earliest_runout_code and k.earliest_runout_month
    else "None in horizon"
)
cards = [
    (
        "Products at risk",
        number(k.products_at_risk),
        "Products at risk = products whose stock runs out within their lead time + 1 month if nothing is ordered, so the order must be placed now.",
    ),
    (
        "Earliest run-out",
        earliest,
        "Earliest run-out = first month where forecast demand > opening stock + inbound, if nothing is ordered (ties: higher value at risk first).",
    ),
    (
        "Purchase spend",
        f"{gbp(k.funded_spend_gbp)} of {gbp(k.budget_gbp)}",
        "Purchase spend = Σ (qty × unit cost) of funded orders; orders are funded in rank order while they fit the remaining budget.",
    ),
    (
        "Unfunded orders",
        number(k.unfunded_orders),
        "Unfunded orders = suggested orders whose cost > budget left when their turn in the ranking came.",
    ),
    (
        "Stock value",
        gbp(k.stock_value_gbp),
        "Stock value = Σ stock on hand × unit cost (synthetic stock and cost).",
    ),
]
for column, (label, value, help_text) in zip(
    st.columns([1.15, 2.2, 1.6, 1.1, 1.2]), cards, strict=True
):
    column.metric(label, value, help=help_text)

navigation.run()
