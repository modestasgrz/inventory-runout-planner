"""Inventory run-out planner: entry file with the shared sidebar, notices and KPI strip (DEC-14, DEC-15)."""

import os
from fractions import Fraction

import streamlit as st
from inventory_runout_planner.data import DataError
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import Scenario, scenario_errors
from inventory_runout_planner.planner import backtest, half_up
from inventory_runout_planner.presets import PRESETS
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
        "Purchase budget (£, whole horizon)",
        key="budget_gbp",
        step=1000.0,
        format="%.0f",
        on_change=on_edit,
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
    st.caption("Planning as of 1 Dec 2011 · money in GBP")
    st.caption("Demand: UCI Online Retail II (CC BY 4.0) · stock data synthetic")

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
wape = half_up(Fraction(str(backtest(data, scenario.method).overall_pct)))
st.markdown(
    f'<div class="page-head"><h1>{navigation.title}</h1>'
    '<span class="synthetic-badge">Synthetic stock data — demonstration only</span>'
    '<span class="as-of">Data as of Dec 2011</span>'
    f'<span class="chip" title="Weighted forecast error (WAPE) of this forecast method last year: forecast made in '
    f'Dec 2010 vs what sold in Dec 2010–Nov 2011. Details on Methodology.">Forecast error {wape}% ⓘ</span></div>',
    unsafe_allow_html=True,
)
cards = [
    (
        "At risk",
        number(k.products_at_risk),
        f"of {number(len(result.products))} products",
        (
            "At risk = products that still have unmet demand in some month of the horizon with the plan "
            "(lead time, unfunded orders, capacity, or more than 4 orders needed)."
        ),
    ),
    (
        "Earliest run-out",
        month(k.earliest_runout_month)
        if k.earliest_runout_month
        else "None in horizon",
        k.earliest_runout_code or "—",
        (
            "Earliest run-out = first month where forecast demand > opening stock + inbound, if nothing is ordered "
            "(ties: higher value at risk first)."
        ),
    ),
    (
        "Spend",
        gbp(k.funded_spend_gbp),
        f"of {gbp(k.budget_gbp)}",
        (
            "Spend = Σ (qty × unit cost) of funded orders; orders are funded in urgency order while they fit "
            f"the remaining budget. Suggested in total: {gbp(k.suggested_spend_gbp)}."
        ),
    ),
    (
        "Unfunded",
        number(k.unfunded_orders),
        f"{gbp(k.unfunded_gbp)} short" if k.unfunded_orders else "none",
        (
            "Unfunded = suggested orders whose cost > budget left when their turn came, "
            "or follow-ups whose earlier order wasn't funded."
        ),
    ),
    (
        "Lost sales",
        gbp(k.lost_sales_after_plan_gbp),
        f"{gbp(k.lost_sales_gbp)} if nothing ordered",
        (
            "Lost sales = unmet units × median selling price (real UCI prices), over the whole horizon, "
            f"with every funded order. If nothing is ordered: {gbp(k.lost_sales_gbp)}."
        ),
    ),
]
for column, (label, value, sub, help_text) in zip(
    st.columns(len(cards)), cards, strict=True
):
    warn = label == "Unfunded" and k.unfunded_orders > 0
    (column.container(key="kpi-warn") if warn else column).metric(
        label,
        value,
        delta=sub,
        delta_color="off",
        delta_arrow="off",
        help=help_text,
    )

navigation.run()
