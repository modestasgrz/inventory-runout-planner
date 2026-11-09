import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.fmt import month
from inventory_runout_planner.models import ScenarioResult
from inventory_runout_planner.planner import month_key
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import product_label

result: ScenarioResult = st.session_state["result"]
k = result.kpis


earliest = next(
    (p for p in result.products if p.stock_code == k.earliest_runout_code), None
)
if earliest is not None and earliest.runout_month:
    color = theme.FACTOR_COLORS[earliest.limiting_factor]
    order = earliest.order
    action = (
        f"Order {month(order.order_month)}, arrives {month(order.arrival_month)} ({'funded' if order.funded else 'not funded'})."
        if order
        else "No order possible (capacity)."
    )
    st.markdown(
        f'<div class="runout-hero" style="border-left-color: {color}">'
        f'<div class="eyebrow">Earliest run-out if nothing is ordered</div>'
        f'<div class="product">{html.escape(product_label(earliest.description, earliest.stock_code))}</div>'
        f'<div class="facts"><span>Runs out <b>{month(earliest.runout_month)}</b></span>'
        f'<span><span class="pill" style="background: {color}">Limiting factor: {earliest.limiting_factor}</span></span>'
        f"<span>Lead time <b>{earliest.lead_months} month(s)</b></span></div>"
        f'<div class="reason">{html.escape(action)}</div></div>',
        unsafe_allow_html=True,
    )
else:
    st.success("No product runs out within the horizon.")

order_now = [p for p in result.products if p.order_now]
st.subheader("Order now")
st.caption(
    "Products that run out within their lead time + 1 month if nothing is ordered, most urgent first."
)
st.dataframe(
    pd.DataFrame(
        [
            {
                "Product": p.description,
                "Code": p.stock_code,
                "Group": p.group,
                "Runs out": month(p.runout_month or ""),
                "Lead time": f"{p.lead_months} mo",
                "Limiting factor": p.limiting_factor,
            }
            for p in order_now
        ],
        columns=[
            "Product",
            "Code",
            "Group",
            "Runs out",
            "Lead time",
            "Limiting factor",
        ],
    ),
    hide_index=True,
    width="stretch",
    height=35 * len(order_now) + 38,
)

st.subheader("Run-outs by month")
st.caption(
    "Do-nothing projection: when each product first runs short, by limiting factor."
)
runouts = pd.DataFrame(
    [
        {"month": p.runout_month, "factor": p.limiting_factor}
        for p in result.products
        if p.runout_month
    ],
    columns=["month", "factor"],
)
figure = go.Figure()
months = [month_key(t) for t in range(1, result.scenario.horizon_months + 1)]
for factor in ["lead time", "budget", "capacity", "stock"]:
    counts = runouts[runouts["factor"] == factor]["month"].value_counts()
    if counts.empty:
        continue
    figure.add_bar(
        x=[month(m) for m in months],
        y=[int(counts.get(m, 0)) for m in months],
        name=factor,
        marker_color=theme.FACTOR_COLORS[factor],
    )
figure.update_layout(
    template=theme.TEMPLATE, barmode="stack", height=300, yaxis_title="Products"
)
st.plotly_chart(figure, width="stretch")

st.subheader("Flags")
st.caption(
    "Everything that needs a buyer's eye: blocked or unfunded orders, overstock, late inbound orders."
)
factor_flags = {
    "lead time": "Lead time: an order placed now arrives after the run-out",
}
flag_rows = [
    {"Product": p.description, "Code": p.stock_code, "Flag": flag}
    for p in result.products
    for flag in (
        [factor_flags[p.limiting_factor]] if p.limiting_factor in factor_flags else []
    )
    + (["Budget: suggested order not funded"] if p.order and not p.order.funded else [])
    + p.flags
]
st.dataframe(
    pd.DataFrame(flag_rows, columns=["Product", "Code", "Flag"]),
    hide_index=True,
    width="stretch",
    height=35 * len(flag_rows) + 38,
    column_config={
        "Product": st.column_config.TextColumn(width="medium"),
        "Flag": st.column_config.TextColumn(width="large"),
    },
)
