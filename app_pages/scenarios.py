from fractions import Fraction

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import ScenarioResult
from inventory_runout_planner.planner import half_up
from inventory_runout_planner.presets import PRESETS
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import run_scenario

result: ScenarioResult = st.session_state["result"]
directory: str = st.session_state["data_dir"]
LEVERS = {
    "Baseline": "Today's plan: no growth, suppliers on time, £100 000 budget, 1 month safety stock.",
    "Peak season +25%": "Demand 25 % above last year in every month.",
    "Supplier delay +3 weeks": "Every supplier and every open inbound order arrives 3 weeks later.",
    "Tight budget": "Half the purchase budget.",
    "Efficiency": "Safety stock cut to half a month of demand.",
}

st.caption(
    "Change the inputs in the sidebar, or load a preset there. Every page recalculates from the same scenario."
)

s = result.scenario
method = "Seasonal naive" if s.method == "seasonal_naive" else "Trailing 3-month"
st.markdown(
    '<div class="mini-stats">'
    + "".join(
        f'<div><span class="k">{label}</span><span class="v">{value}</span></div>'
        for label, value in [
            ("Horizon", f"{s.horizon_months} months"),
            ("Demand growth", f"{s.growth_pct:g} %"),
            ("Supplier delay", f"{s.delay_weeks} weeks"),
            ("Budget", gbp(s.budget_gbp)),
            ("Safety stock", f"{s.safety_months:g} month(s)"),
            ("Forecast", method),
        ]
    )
    + "</div>",
    unsafe_allow_html=True,
)

st.subheader("Presets side by side")
st.markdown("\n".join(f"- **{name}:** {lever}" for name, lever in LEVERS.items()))
runs = {name: run_scenario(preset, directory) for name, preset in PRESETS.items()}
table = pd.DataFrame(
    [
        {
            "Preset": name,
            "Products at risk": r.kpis.products_at_risk,
            "Unfunded orders": r.kpis.unfunded_orders,
            "Unfunded £": half_up(Fraction(str(r.kpis.unfunded_gbp))),
            "Lost sales £": half_up(Fraction(str(r.kpis.lost_sales_after_plan_gbp))),
            "Stock-out months": r.kpis.stockout_months,
            "Earliest run-out": f"{month(r.kpis.earliest_runout_month)} · {r.kpis.earliest_runout_code}"
            if r.kpis.earliest_runout_month
            else "None",
        }
        for name, r in runs.items()
    ]
)
st.dataframe(
    table.style.format(
        {
            column: (lambda v: gbp(float(str(v))))
            if "£" in column
            else (lambda v: number(float(str(v))))
            for column in [
                "Products at risk",
                "Unfunded orders",
                "Unfunded £",
                "Lost sales £",
                "Stock-out months",
            ]
        }
    ),
    hide_index=True,
    width="stretch",
    column_config={
        "Preset": st.column_config.TextColumn(width="medium"),
        "Unfunded £": st.column_config.NumberColumn(width="small"),
        "Lost sales £": st.column_config.NumberColumn(
            width="small",
            help="Lost sales after plan = unmet units × median selling price, up to the end of each order's 3-month cover",
        ),
        "Stock-out months": st.column_config.NumberColumn(
            help="Σ over products of months with unmet demand after the plan (same window)",
        ),
    },
)

figure = go.Figure()
names = list(runs)
figure.add_bar(
    x=names,
    y=[runs[n].kpis.suggested_spend_gbp for n in names],
    name="Suggested spend",
    marker_color=theme.MUTED,
)
figure.add_bar(
    x=names,
    y=[runs[n].kpis.funded_spend_gbp for n in names],
    name="Funded within budget",
    marker_color=theme.BLUE,
)
for i, n in enumerate(names):
    figure.add_shape(
        type="line",
        x0=i - 0.45,
        x1=i + 0.45,
        y0=runs[n].kpis.budget_gbp,
        y1=runs[n].kpis.budget_gbp,
        line={"color": theme.AMBER, "width": 3},
    )
figure.add_scatter(
    x=[None],
    y=[None],
    mode="lines",
    name="Budget",
    line={"color": theme.AMBER, "width": 3},
)
figure.update_layout(
    template=theme.TEMPLATE,
    barmode="overlay",
    height=340,
    yaxis={"tickprefix": "£"},
    margin={"t": 10},
    legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.1},
)
st.plotly_chart(figure, width="stretch")
