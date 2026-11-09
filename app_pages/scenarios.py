import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import ScenarioResult
from inventory_runout_planner.presets import PRESETS
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import run_scenario

result: ScenarioResult = st.session_state["result"]
directory: str = st.session_state["data_dir"]
LEVERS = {
    "Baseline": "Today's plan: no growth, suppliers on time, £100 000 budget, 1 month safety stock.",
    "Peak season +25%": "Demand 25 % above last year in every month.",
    "Supplier delay +3 weeks": "Every supplier and every open inbound order arrives 3 weeks later.",
    "Tight budget": "Half the purchase budget.",
    "Efficiency": "Safety stock cut to half a month of demand.",
}

st.caption(
    "Change the inputs in the sidebar, or load a preset there. Every page recalculates from the same scenario."
)

s = result.scenario
st.subheader("Current assumptions")
st.dataframe(
    pd.DataFrame(
        [
            ["Horizon", f"{s.horizon_months} months"],
            ["Demand growth", f"{s.growth_pct:g} %"],
            ["Supplier delay", f"{s.delay_weeks} weeks"],
            ["Budget", gbp(s.budget_gbp)],
            ["Safety stock", f"{s.safety_months:g} month(s) of demand"],
            [
                "Forecast method",
                "Seasonal naive"
                if s.method == "seasonal_naive"
                else "Trailing 3-month average",
            ],
        ],
        columns=["Input", "Value"],
    ),
    hide_index=True,
    use_container_width=True,
)

st.subheader("Presets side by side")
st.markdown("\n".join(f"- **{name}:** {lever}" for name, lever in LEVERS.items()))
runs = {name: run_scenario(preset, directory) for name, preset in PRESETS.items()}
rows = []
for name, r in runs.items():
    k = r.kpis
    rows.append(
        {
            "Preset": name,
            "Products at risk": number(k.products_at_risk),
            "Earliest run-out": f"{month(k.earliest_runout_month)} · {k.earliest_runout_code}"
            if k.earliest_runout_month
            else "None",
            "Funded": gbp(k.funded_spend_gbp),
            "Suggested": gbp(k.suggested_spend_gbp),
            "Unfunded orders": number(k.unfunded_orders),
        }
    )
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

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
figure.add_scatter(
    x=names,
    y=[runs[n].kpis.budget_gbp for n in names],
    name="Budget",
    mode="markers",
    marker={
        "color": theme.AMBER,
        "size": 14,
        "symbol": "line-ew-open",
        "line": {"width": 4},
    },
)
figure.update_layout(
    template=theme.TEMPLATE,
    barmode="overlay",
    height=360,
    yaxis={"tickprefix": "£"},
    title="Spend by preset",
)
st.plotly_chart(figure, use_container_width=True)
