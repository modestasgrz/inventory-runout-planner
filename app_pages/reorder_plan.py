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
    "Every order in the plan, most urgent first (#): the month it prevents a shortfall, then value at risk "
    "(unmet units × unit cost). Order 1 is the next order; 2–4 are follow-ups for later dips in the horizon. "
    "Orders are funded in that order while they fit the budget left; a follow-up is funded only if the order "
    "before it is. Unfunded rows are tinted amber."
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

st.dataframe(
    theme.styled(
        pd.DataFrame(
            [
                {
                    "#": line.rank,
                    "Product": line.description.title(),
                    "Code": line.stock_code,
                    "Order": line.order_no,
                    "Order month": month(line.order_month),
                    "Arrives": month(line.arrival_month),
                    "Qty": line.qty,
                    "Cost": line.cost_gbp,
                    "Status": "✓ Funded" if line.funded else "Not funded",
                    "Limiting factor": line.limiting_factor,
                }
                for line in result.plan
            ],
            columns=[
                "#",
                "Product",
                "Code",
                "Order",
                "Order month",
                "Arrives",
                "Qty",
                "Cost",
                "Status",
                "Limiting factor",
            ],
        )
    ).format(
        {
            "Qty": lambda v: number(float(str(v))),
            "Cost": lambda v: gbp(float(str(v))),
        }
    ),
    hide_index=True,
    width="stretch",
    height=35 * 12 + 38,
    column_config={
        "#": st.column_config.NumberColumn(
            width=45, help="Urgency rank: earliest shortfall first, then value at risk"
        ),
        "Product": st.column_config.TextColumn(width=250),
        "Code": st.column_config.TextColumn(width=70),
        "Order": st.column_config.NumberColumn(
            width=60, help="1 = the next order, 2–4 = follow-up orders"
        ),
        "Order month": st.column_config.TextColumn(width=95),
        "Arrives": st.column_config.TextColumn(width=85),
        "Status": st.column_config.TextColumn(width=95),
    },
)

with st.expander("Why each order: the numbers behind every line"):
    for line in result.plan:
        st.markdown(
            f"**{line.rank}. {product_label(line.description, line.stock_code)}, order {line.order_no}** — {line.reason}"
        )

st.subheader("Exports")
st.caption(
    "Raw numbers, ready for a spreadsheet. Stock fields are synthetic and labelled so in products.csv."
)
for column, (name, frame) in zip(
    st.columns(4), tables(data, result).items(), strict=True
):
    column.download_button(
        f"Download {name}",
        frame.to_csv(index=False),
        file_name=name,
        mime="text/csv",
        type="tertiary",
    )
