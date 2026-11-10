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
    "Baseline": f"Today's plan: no growth, suppliers on time, {gbp(PRESETS['Baseline'].budget_gbp)} budget for the horizon, 1 month safety stock.",
    "Peak season +25%": "Demand 25 % above last year in every month.",
    "Supplier delay +3 weeks": "Every supplier and every open inbound order arrives 3 weeks later.",
    "Tight budget": "Half the purchase budget.",
    "Efficiency": "Safety stock cut to half a month of demand.",
}

st.caption(
    "Change the inputs in the sidebar, or load a preset there. Every page recalculates from the same scenario; "
    "this table always shows the five presets."
)

st.subheader("Presets side by side")
st.markdown("\n".join(f"- **{name}:** {lever}" for name, lever in LEVERS.items()))
runs = {name: run_scenario(preset, directory) for name, preset in PRESETS.items()}
base = runs["Baseline"].kpis.lost_sales_after_plan_gbp
table = pd.DataFrame(
    [
        {
            "Preset": name,
            "Products at risk": r.kpis.products_at_risk,
            "Lost sales £": half_up(Fraction(str(r.kpis.lost_sales_after_plan_gbp))),
            "vs Baseline £": half_up(
                Fraction(str(r.kpis.lost_sales_after_plan_gbp)) - Fraction(str(base))
            ),
            "Unfunded orders": r.kpis.unfunded_orders,
            "Unfunded £": half_up(Fraction(str(r.kpis.unfunded_gbp))),
            "Earliest run-out": f"{month(r.kpis.earliest_runout_month)} · {r.kpis.earliest_runout_code}"
            if r.kpis.earliest_runout_month
            else "None",
        }
        for name, r in runs.items()
    ]
)


def signed(v: object) -> str:
    """'+£12 345', '−£3 210' or '—' for Baseline's own zero."""
    value = float(str(v))
    if value == 0:
        return "—"
    return ("+" if value > 0 else "−") + gbp(abs(value))


st.dataframe(
    table.style.format(
        {
            "Products at risk": lambda v: number(float(str(v))),
            "Lost sales £": lambda v: gbp(float(str(v))),
            "vs Baseline £": signed,
            "Unfunded orders": lambda v: number(float(str(v))),
            "Unfunded £": lambda v: gbp(float(str(v))),
        }
    ).map(
        lambda v: (
            f"color: {theme.RED}" if float(str(v)) > 0 else f"color: {theme.MUTED}"
        ),
        subset=["vs Baseline £"],
    ),
    hide_index=True,
    width="stretch",
    column_config={
        "Preset": st.column_config.TextColumn(width="medium"),
        "Lost sales £": st.column_config.NumberColumn(
            help="Lost sales = unmet units × median selling price over the whole horizon, with every funded order",
        ),
        "vs Baseline £": st.column_config.NumberColumn(
            help="This preset's lost sales minus Baseline's: + means more sales lost"
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
        line={"color": theme.TEXT, "width": 2, "dash": "dash"},
    )
figure.add_scatter(
    x=[None],
    y=[None],
    mode="lines",
    name="Budget",
    line={"color": theme.TEXT, "width": 2, "dash": "dash"},
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
