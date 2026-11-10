import pandas as pd
import streamlit as st
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import MonthRow, PlannerData, ScenarioResult
from inventory_runout_planner.planner import backtest, month_key
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import product_label
from plotly.subplots import make_subplots

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
    f"Stock on hand **{number(product.stock_on_hand)}** · lead time **{product.lead_time_weeks} weeks + delay {result.scenario.delay_weeks} weeks = {p.lead_months} month(s)** · "
    f"MOQ **{number(product.moq)}** · capacity **{number(product.capacity)}** · "
    f"unit cost **{gbp(product.unit_cost, pence=True)}** · inbound order **{inbound}**"
)
st.caption(
    "Stock, lead time, MOQ, capacity, unit cost and inbound order are synthetic; demand history is real."
)

history = data.history[p.stock_code]
error = backtest(data, result.scenario.method).overall_pct / 100
forecast_x = [f"{r.month}-01" for r in p.months]
month_end_x = [f"{month_key(t + 2)}-01" for t in range(len(p.months))]
figure = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.08,
    row_heights=[0.55, 0.45],
    subplot_titles=["Demand (units)", "Stock at month end (units)"],
)
figure.add_bar(
    x=[f"{m}-01" for m in data.history_months],
    y=history,
    name="Actual demand (UCI)",
    marker_color=theme.MUTED,
    opacity=0.55,
    row=1,
    col=1,
)
figure.add_scatter(
    x=forecast_x + forecast_x[::-1],
    y=[r.demand * (1 + error) for r in p.months]
    + [max(0.0, r.demand * (1 - error)) for r in p.months][::-1],
    fill="toself",
    fillcolor="rgba(230, 236, 245, 0.10)",
    line={"width": 0},
    hoverinfo="skip",
    name=f"Range from last year's forecast error (±{error:.0%})",
    row=1,
    col=1,
)
figure.add_scatter(
    x=forecast_x,
    y=[r.demand for r in p.months],
    name="Forecast demand",
    line={"color": theme.TEXT, "dash": "dot", "width": 1.5},
    row=1,
    col=1,
)
figure.add_scatter(
    x=month_end_x,
    y=[r.closing for r in p.months],
    name="Stock, do nothing",
    line={"color": theme.RED, "dash": "dash", "width": 2},
    row=2,
    col=1,
)
figure.add_scatter(
    x=month_end_x,
    y=[r.closing for r in p.plan_months],
    name="Stock, with the plan",
    line={"color": theme.BLUE, "width": 3},
    row=2,
    col=1,
)
for start, end, r in zip(forecast_x, month_end_x, p.plan_months, strict=True):
    if r.unmet:
        figure.add_vrect(
            x0=start,
            x1=end,
            fillcolor=theme.RED,
            opacity=0.12,
            line_width=0,
            row=2,
            col=1,
        )
figure.add_vline(
    x=f"{p.months[0].month}-01", line={"color": theme.MUTED, "dash": "dot"}
)
figure.add_annotation(
    x=f"{p.months[0].month}-01",
    y=1.02,
    yref="paper",
    text="Today (1 Dec 2011)",
    showarrow=False,
    font={"color": theme.MUTED, "size": 11},
)
visible = [*history[-6:], *(r.demand * (1 + error) for r in p.months), 1]
figure.update_layout(
    template=theme.TEMPLATE,
    height=560,
    legend={"orientation": "h", "x": 0, "y": -0.08},
    margin={"t": 70},
    title=f"{product_label(p.description, p.stock_code)}",
)
figure.update_yaxes(range=[0, 1.1 * max(visible)], row=1, col=1)
figure.update_yaxes(rangemode="tozero", row=2, col=1)
figure.update_xaxes(
    dtick="M2",
    tickformat="%b %Y",
    range=[f"{data.history_months[-6]}-01", month_end_x[-1]],
)
st.plotly_chart(figure, width="stretch")
st.caption(
    f"Shaded band = forecast × (1 ± {error:.0%}), the weighted forecast error (WAPE) of this method last year, "
    "floored at 0. Stock is shown at the end of each month; red months below = unmet demand even with the plan."
)

if p.orders:
    for line in p.orders:
        status = "funded" if line.funded else "not funded"
        st.markdown(f"**Order {line.order_no}** ({status}) · {line.reason}")
else:
    st.markdown(
        f"**No order suggested** · limiting factor: {p.limiting_factor}. {' '.join(p.flags)}"
    )


NUMBERS = {
    column: st.column_config.TextColumn(alignment="right") for column in COLUMNS[1:]
}


def table(rows: list[MonthRow]) -> "pd.io.formats.style.Styler":
    """Month-by-month rows; zeros greyed so the numbers that matter stand out."""
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
    ).style.map(lambda v: f"color: {theme.MUTED}" if v == "0" else "")


st.subheader("Projection if nothing is ordered")
st.caption(
    "Available = opening + inbound · shipped = min(demand, available) · unmet = demand − shipped · closing = available − shipped."
)
st.dataframe(
    table(p.months),
    hide_index=True,
    width="stretch",
    height=35 * len(p.months) + 38,
    column_config=NUMBERS,
)
if p.plan_months != p.months:
    with st.expander("Projection with the plan (every funded order)"):
        st.dataframe(
            table(p.plan_months),
            hide_index=True,
            width="stretch",
            height=35 * len(p.plan_months) + 38,
            column_config=NUMBERS,
        )
elif p.orders:
    st.caption(
        "No funded order arrives inside the horizon, so the projection with the plan is the same as above."
    )
