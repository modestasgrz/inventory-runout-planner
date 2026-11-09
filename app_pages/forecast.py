import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import MonthRow, PlannerData, ScenarioResult
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import product_label

result: ScenarioResult = st.session_state["result"]
data: PlannerData = st.session_state["data"]
COLUMNS = ["Month", "Demand", "Opening", "Inbound", "Shipped", "Unmet", "Closing"]


labels = {product_label(p.description, p.stock_code): p for p in result.products}
choice = st.selectbox("Product (most urgent first)", list(labels), key="product")
p = labels[choice]
product = next(x for x in data.products if x.stock_code == p.stock_code)

inbound = (
    f"{number(product.inbound_qty)} units arriving {month(p.inbound_month)}"
    if p.inbound_month
    else "none"
)
st.markdown(
    f"Stock on hand **{number(product.stock_on_hand)}** · lead time **{product.lead_time_weeks} weeks** · "
    f"MOQ **{number(product.moq)}** · capacity **{number(product.capacity)}** · "
    f"unit cost **{gbp(product.unit_cost, pence=True)}** · inbound order **{inbound}**"
)
st.caption(
    "Stock, lead time, MOQ, capacity, unit cost and inbound order are synthetic; demand history is real."
)

history = data.history[p.stock_code]
figure = go.Figure()
figure.add_bar(
    x=[f"{m}-01" for m in data.history_months],
    y=history,
    name="Actual demand (UCI)",
    marker_color=theme.MUTED,
    opacity=0.55,
)
forecast_x = [f"{r.month}-01" for r in p.months]
figure.add_scatter(
    x=forecast_x,
    y=[r.demand for r in p.months],
    name="Forecast demand",
    line={"color": theme.BLUE, "dash": "dash"},
)
figure.add_scatter(
    x=forecast_x,
    y=[r.closing for r in p.months],
    name="Stock, do nothing",
    line={"color": theme.RED},
)
figure.add_scatter(
    x=forecast_x,
    y=[r.closing for r in p.plan_months],
    name="Stock, with next order",
    line={"color": theme.GREEN},
)
if p.runout_month:
    figure.add_vline(x=f"{p.runout_month}-01", line={"color": theme.RED, "dash": "dot"})
figure.update_layout(
    template=theme.TEMPLATE,
    height=420,
    yaxis_title="Units",
    xaxis={"dtick": "M3", "tickformat": "%b %Y"},
    title=f"{p.description} ({p.stock_code}) · monthly units",
)
st.plotly_chart(figure, use_container_width=True)

if p.order:
    st.markdown(f"**Next order** · {p.order.reason}")
else:
    st.markdown(
        f"**No order suggested** · limiting factor: {p.limiting_factor}. {' '.join(p.flags)}"
    )


def table(rows: list[MonthRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            [
                month(r.month),
                number(r.demand),
                number(r.opening),
                number(r.inbound),
                number(r.shipped),
                number(r.unmet),
                number(r.closing),
            ]
            for r in rows
        ],
        columns=COLUMNS,
    )


st.subheader("Projection if nothing is ordered")
st.caption(
    "Available = opening + inbound · shipped = min(demand, available) · unmet = demand − shipped · closing = available − shipped."
)
st.dataframe(
    table(p.months),
    hide_index=True,
    use_container_width=True,
    height=35 * len(p.months) + 38,
)
with st.expander("Projection with the suggested order (if funded)"):
    st.dataframe(
        table(p.plan_months),
        hide_index=True,
        use_container_width=True,
        height=35 * len(p.plan_months) + 38,
    )
