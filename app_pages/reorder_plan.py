import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.exports import tables
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import PlannerData, ScenarioResult
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import product_label

result: ScenarioResult = st.session_state["result"]
data: PlannerData = st.session_state["data"]
k = result.kpis

st.caption(
    "The next order per product, listed by order month. Urgency rank = run-out month, then value at risk "
    "(unmet units × unit cost); orders are funded in urgency order, and one that doesn't fit the budget left is skipped "
    "so smaller ones below it can still be funded. Unfunded rows are tinted amber."
)

st.markdown(
    f"**Funded total: {gbp(k.funded_spend_gbp)}** of {gbp(k.budget_gbp)} budget · suggested {gbp(k.suggested_spend_gbp)} · "
    f"{number(k.unfunded_orders)} unfunded ({gbp(k.unfunded_gbp)}) · Stock value: {gbp(k.stock_value_gbp)} (stock on hand × unit cost)"
)
figure = go.Figure()
for name, value, color in [
    ("Funded", k.funded_spend_gbp, theme.BLUE),
    ("Not funded", k.unfunded_gbp, theme.AMBER),
]:
    figure.add_bar(
        y=["Spend"],
        x=[value],
        orientation="h",
        name=name,
        marker_color=color,
        text=[f"{name} {gbp(value)}"],
        textposition="inside",
        insidetextanchor="middle",
    )
figure.add_vline(x=k.budget_gbp, line={"color": theme.TEXT, "dash": "dash"})
figure.update_layout(
    template=theme.TEMPLATE,
    barmode="stack",
    height=90,
    showlegend=False,
    xaxis={"tickprefix": "£"},
    yaxis={"visible": False},
    margin={"t": 4, "b": 24, "l": 8, "r": 8},
)
st.plotly_chart(figure, width="stretch")
st.caption(
    "Dashed line = budget. Limiting factor *none* means the product doesn't run out in the horizon: the order only "
    "tops stock back up to safety stock before it would dip below it."
)

ordered = sorted(result.plan, key=lambda line: (line.order_month, line.rank))
st.dataframe(
    theme.styled(
        pd.DataFrame(
            [
                {
                    "Urgency rank": line.rank,
                    "Product": line.description,
                    "Code": line.stock_code,
                    "Order month": month(line.order_month),
                    "Arrives": month(line.arrival_month),
                    "Qty": number(line.qty),
                    "Cost": gbp(line.cost_gbp),
                    "Funded": line.funded,
                    "Limiting factor": line.limiting_factor,
                }
                for line in ordered
            ],
            columns=[
                "Urgency rank",
                "Product",
                "Code",
                "Order month",
                "Arrives",
                "Qty",
                "Cost",
                "Funded",
                "Limiting factor",
            ],
        )
    ),
    hide_index=True,
    width="stretch",
    height=35 * len(ordered) + 38,
    column_config={
        "Urgency rank": st.column_config.NumberColumn(
            width="small",
            help="1 = most urgent: earliest run-out, then highest value at risk",
        ),
        "Product": st.column_config.TextColumn(width=240),
        "Order month": st.column_config.TextColumn(width=95),
        "Arrives": st.column_config.TextColumn(width="small"),
        "Limiting factor": st.column_config.TextColumn(width=100),
        "Code": st.column_config.TextColumn(width="small"),
        "Qty": st.column_config.TextColumn(width="small", alignment="right"),
        "Cost": st.column_config.TextColumn(width="small", alignment="right"),
        "Funded": st.column_config.CheckboxColumn(width="small"),
    },
)

with st.expander("Why each order: the numbers behind every line"):
    for line in result.plan:
        st.markdown(
            f"**{line.rank}. {product_label(line.description, line.stock_code)}** — {line.reason}"
        )

st.subheader("Exports")
st.caption(
    "Raw numbers, ready for a spreadsheet. Stock fields are synthetic and labelled so in products.csv."
)
columns = st.columns(2) * 2
for column, (name, frame) in zip(columns, tables(data, result).items(), strict=True):
    column.download_button(
        f"Download {name}",
        frame.to_csv(index=False),
        file_name=name,
        mime="text/csv",
        width="stretch",
    )
