import html
from fractions import Fraction

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import PlannerData, ProductResult, ScenarioResult
from inventory_runout_planner.planner import backtest, half_up, month_key
from inventory_runout_planner.ui import theme

result: ScenarioResult = st.session_state["result"]
data: PlannerData = st.session_state["data"]
k = result.kpis
RIGHT = st.column_config.TextColumn(alignment="right", width="small")

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
    truth = ""
    if gap := earliest.stockout:
        span = (
            f"{gap.months} month ({month(gap.start_month)})"
            if gap.months == 1
            else f"{gap.months} months ({month(gap.start_month)}–{month(gap.end_month)})"
        )
        truth = (
            f'<div class="truth">Out of stock {span}, {number(gap.units)} units, '
            f"{gbp(gap.lost_sales_gbp)} lost sales. Expedite?</div>"
        )
    st.markdown(
        f'<div class="runout-hero" style="border-left-color: {color}">'
        '<div class="eyebrow">Earliest run-out if nothing is ordered</div>'
        f'<div class="product">{html.escape(earliest.description.title())} ({html.escape(earliest.stock_code)})</div>'
        f'<div class="facts"><span>Runs out <b>{month(earliest.runout_month)}</b></span>'
        f'<span class="factor" style="color: {color}">Limiting factor: {earliest.limiting_factor}</span>'
        f"<span>Lead time <b>{earliest.lead_months} month(s)</b></span></div>"
        f"{truth}"
        f'<div class="reason">{html.escape(action)}</div></div>',
        unsafe_allow_html=True,
    )
else:
    st.success("No product runs out within the horizon.")

error = backtest(data, result.scenario.method).overall_pct
st.caption(
    f"Weighted forecast error (WAPE) last year: {half_up(Fraction(str(error)))}% — this forecast method, "
    "made in Dec 2010 and checked against what actually sold in Dec 2010–Nov 2011. Details on Methodology."
)

order_now = [p for p in result.products if p.order_now]
st.subheader("Order now")
st.caption(
    "Products that run out within their lead time + 1 month if nothing is ordered, most urgent first."
)
st.dataframe(
    theme.styled(
        pd.DataFrame(
            [
                {
                    "Product": p.description,
                    "Code": p.stock_code,
                    "Runs out": month(p.runout_month or ""),
                    "Order by": month(p.order.order_month) if p.order else "no order",
                    "Qty": number(p.order.qty) if p.order else "",
                    "Cost £": number(p.order.cost_gbp) if p.order else "",
                    "Funded": bool(p.order and p.order.funded),
                    "Limiting factor": p.limiting_factor,
                }
                for p in order_now
            ],
            columns=[
                "Product",
                "Code",
                "Runs out",
                "Order by",
                "Qty",
                "Cost £",
                "Funded",
                "Limiting factor",
            ],
        )
    ),
    hide_index=True,
    width="stretch",
    height=35 * len(order_now) + 38,
    column_config={
        "Product": st.column_config.TextColumn(width="medium"),
        "Code": st.column_config.TextColumn(width="small"),
        "Qty": RIGHT,
        "Cost £": RIGHT,
        "Funded": st.column_config.CheckboxColumn(width="small"),
    },
)

st.subheader("Run-outs by month")
st.caption(
    "Do-nothing projection: when each product first runs short, by limiting factor."
)
months = [month_key(t) for t in range(1, result.scenario.horizon_months + 1)]
figure = go.Figure()
for factor in ["lead time", "budget", "capacity", "stock"]:
    counts = [
        sum(
            p.runout_month == m and p.limiting_factor == factor for p in result.products
        )
        for m in months
    ]
    if any(counts):
        figure.add_bar(
            x=[month(m) for m in months],
            y=counts,
            name=factor,
            marker_color=theme.FACTOR_COLORS[factor],
            text=[c or "" for c in counts],
            textposition="inside",
            textangle=0,
            insidetextanchor="middle",
        )
figure.update_layout(
    template=theme.TEMPLATE,
    barmode="stack",
    height=280,
    margin={"t": 10},
    yaxis={"dtick": 2},
    uniformtext={"minsize": 11, "mode": "show"},
    legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.12},
)
st.plotly_chart(figure, width="stretch")


st.subheader("Flags")
st.caption("Everything that needs a buyer's eye, grouped by type, biggest £ first.")
groups = {
    "Lead time": "lost sales",
    "Budget not funded": "short",
    "Capacity blocks order": "lost sales",
    "Later shortfall not covered": "later shortfall",
    "Overstocked": "tied up",
    "Inbound arrives after horizon": "",
}
built: dict[str, list[tuple[ProductResult, str, float]]] = {name: [] for name in groups}
for p in result.products:
    if gap := p.stockout:
        span = month(gap.start_month) + (
            f"–{month(gap.end_month)}" if gap.months > 1 else ""
        )
        built["Lead time"].append(
            (p, f"Out of stock {span}: {number(gap.units)} units", gap.lost_sales_gbp)
        )
    if p.order and not p.order.funded:
        built["Budget not funded"].append(
            (p, f"Order of {number(p.order.qty)} units not funded", p.order.cost_gbp)
        )
    for flag in p.flags:
        if flag.startswith("Capacity"):
            built["Capacity blocks order"].append(
                (p, flag, p.lost_sales_after_plan_gbp)
            )
        elif flag.startswith("Later"):
            built["Later shortfall not covered"].append(
                (p, flag, p.later_shortfall_gbp)
            )
        elif flag.startswith("Overstocked"):
            built["Overstocked"].append((p, flag, p.tied_up_gbp))
        else:
            built["Inbound arrives after horizon"].append((p, flag, 0.0))
built = {name: sorted(rows, key=lambda r: -r[2]) for name, rows in built.items()}
for name in sorted(built, key=lambda n: -sum(r[2] for r in built[n])):
    rows = built[name]
    if not rows:
        continue
    total = sum(r[2] for r in rows)
    label = f"{name} · {len(rows)}" + (
        f" · {gbp(total)} {groups[name]}" if groups[name] else ""
    )
    with st.expander(label, expanded=name == "Lead time"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Product": p.description,
                        "Code": p.stock_code,
                        "Flag": text,
                        "£": number(value),
                    }
                    for p, text, value in rows
                ],
                columns=["Product", "Code", "Flag", "£"],
            ),
            hide_index=True,
            width="stretch",
            height=35 * len(rows) + 38,
            column_config={
                "Product": st.column_config.TextColumn(width="medium"),
                "Code": st.column_config.TextColumn(width="small"),
                "Flag": st.column_config.TextColumn(width="large"),
                "£": RIGHT,
            },
        )
