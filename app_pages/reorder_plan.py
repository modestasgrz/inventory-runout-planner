import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.exports import tables
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import PlannerData, ScenarioResult
from inventory_runout_planner.ui import theme

result: ScenarioResult = st.session_state["result"]
data: PlannerData = st.session_state["data"]
k = result.kpis

st.caption(
    "The next order per product, ranked by run-out month, then value at risk (unmet units × unit cost). "
    "Orders are funded in rank order; one that doesn't fit the budget left is skipped and smaller ones below it can still be funded."
)

st.markdown(
    f"**Funded total: {gbp(k.funded_spend_gbp)}** of {gbp(k.budget_gbp)} budget · suggested {gbp(k.suggested_spend_gbp)} · {number(k.unfunded_orders)} unfunded"
)
figure = go.Figure()
figure.add_bar(
    y=["Spend"],
    x=[k.funded_spend_gbp],
    orientation="h",
    name="Funded",
    marker_color=theme.BLUE,
)
figure.add_bar(
    y=["Spend"],
    x=[k.suggested_spend_gbp - k.funded_spend_gbp],
    orientation="h",
    name="Not funded",
    marker_color=theme.AMBER,
)
figure.add_vline(
    x=k.budget_gbp,
    line={"color": theme.TEXT, "dash": "dash"},
    annotation_text="Budget",
    annotation_position="top",
)
figure.update_layout(
    template=theme.TEMPLATE,
    barmode="stack",
    height=170,
    xaxis={"tickprefix": "£"},
    margin={"t": 30, "b": 40},
)
st.plotly_chart(figure, use_container_width=True)

st.dataframe(
    pd.DataFrame(
        [
            {
                "Rank": line.rank,
                "Product": line.description,
                "Code": line.stock_code,
                "Order month": month(line.order_month),
                "Arrives": month(line.arrival_month),
                "Qty": number(line.qty),
                "Cost": gbp(line.cost_gbp, pence=True),
                "Funded": "Yes" if line.funded else "No",
                "Limiting factor": line.limiting_factor,
                "Reason": line.reason,
            }
            for line in result.plan
        ],
        columns=[
            "Rank",
            "Product",
            "Code",
            "Order month",
            "Arrives",
            "Qty",
            "Cost",
            "Funded",
            "Limiting factor",
            "Reason",
        ],
    ),
    hide_index=True,
    use_container_width=True,
    height=35 * len(result.plan) + 38,
    column_config={
        "Rank": st.column_config.NumberColumn(width="small"),
        "Product": st.column_config.TextColumn(width="medium"),
        "Code": st.column_config.TextColumn(width="small"),
        "Qty": st.column_config.TextColumn(width="small"),
        "Funded": st.column_config.TextColumn(width="small"),
        "Reason": st.column_config.TextColumn(width="medium"),
    },
)

with st.expander("Why each order: the numbers behind every line"):
    for line in result.plan:
        st.markdown(
            f"**{line.rank}. {line.description} ({line.stock_code})** — {line.reason}"
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
        use_container_width=True,
    )
