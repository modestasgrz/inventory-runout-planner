import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import ProductResult, ScenarioResult
from inventory_runout_planner.planner import month_key
from inventory_runout_planner.ui import theme

result: ScenarioResult = st.session_state["result"]
k = result.kpis
RIGHT = st.column_config.TextColumn(alignment="right", width="small")

earliest = next(
    (p for p in result.products if p.stock_code == k.earliest_runout_code), None
)
if earliest is not None and earliest.runout_month:
    order = earliest.order
    gap = earliest.stockout
    if gap is not None:
        span = month(gap.start_month) + (
            f"–{month(gap.end_month)}" if gap.months > 1 else ""
        )
        covered = (
            order is not None
            and order.funded
            and order.arrival_month in {r.month for r in earliest.months}
        )
        status = (
            f"Out of stock {span}, covered from {month(order.arrival_month)}"
            if covered and order is not None
            else f"Out of stock from {month(gap.start_month)}, no funded order arrives in the horizon"
        )
        lost = gap.lost_sales_gbp
    else:
        status = f"Runs out {month(earliest.runout_month)} if nothing is ordered"
        lost = earliest.lost_sales_after_plan_gbp
    later = ""
    if earliest.later_shortfall_month:
        later = (
            f'<div class="later">+ {gbp(earliest.later_shortfall_gbp)} short after plan from '
            f"{month(earliest.later_shortfall_month)}</div>"
            if gap is not None
            else f'<div class="later">Short after plan from {month(earliest.later_shortfall_month)}</div>'
        )
    cost = (
        f'<div class="cost">{gbp(lost)} lost sales</div>'
        if lost > 0
        else '<div class="later">No lost sales with the plan</div>'
    )
    if order is None:
        action = next(
            (f for f in earliest.flags if f.startswith("Capacity")),
            "No order possible.",
        )
    elif order.funded and gap is not None:
        action = (
            f"Order {number(order.qty)} units in {month(order.order_month)}, the earliest possible "
            f"with a {earliest.lead_months}-month lead time; they arrive {month(order.arrival_month)}."
        )
    elif order.funded:
        action = (
            f"Order {number(order.qty)} units by {month(order.order_month)}; "
            f"they arrive {month(order.arrival_month)}, before it runs out."
        )
    else:
        action = f"Order {number(order.qty)} units by {month(order.order_month)}: not funded within the budget."
    chip = earliest.limiting_factor.capitalize()
    chip_color = theme.FACTOR_COLORS[earliest.limiting_factor]
    st.markdown(
        '<div class="runout-hero">'
        '<div class="eyebrow">Earliest run-out if nothing is ordered</div>'
        f'<div class="product">{html.escape(earliest.description.title())} ({html.escape(earliest.stock_code)})'
        f' <span class="chip factor-chip" style="color: {chip_color}; border-color: {chip_color}">{chip}</span></div>'
        f'<div class="status">{html.escape(status)}</div>'
        f'<div class="reason">{html.escape(action)}</div>'
        f"{cost}{later}</div>",
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
    theme.styled(
        pd.DataFrame(
            [
                {
                    "Product": p.description.title(),
                    "Code": p.stock_code,
                    "Runs out": month(p.runout_month or ""),
                    "Order by": month(p.order.order_month) if p.order else "no order",
                    "Qty": number(p.order.qty) if p.order else "",
                    "Cost £": number(p.order.cost_gbp) if p.order else "",
                    "Funded": ("✓ Funded" if p.order.funded else "Not funded")
                    if p.order
                    else "",
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
        "Product": st.column_config.TextColumn(width=260),
        "Code": st.column_config.TextColumn(width="small"),
        "Qty": RIGHT,
        "Cost £": RIGHT,
        "Funded": st.column_config.TextColumn(width="small"),
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
            text=[f"<b>{c}</b>" if c else "" for c in counts],
            textfont={"color": theme.BG},
            textposition="inside",
            textangle=0,
            insidetextanchor="middle",
        )
figure.update_layout(
    template=theme.TEMPLATE,
    barmode="stack",
    height=280,
    margin={"t": 10},
    yaxis={"dtick": 2, "title": "products"},
    uniformtext={"minsize": 11, "mode": "show"},
    legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.12},
)
st.plotly_chart(figure, width="stretch")


st.subheader("Flags")
st.caption(
    "Everything that needs a buyer's eye, grouped by type: lead time first (it needs action now), then biggest £ first."
)
groups = {
    "Lead time": "lost sales",
    "Budget not funded": "short",
    "Capacity blocks order": "lost sales",
    "Short after plan": "lost sales",
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
    for line in p.orders:
        if not line.funded:
            built["Budget not funded"].append(
                (
                    p,
                    f"Order {line.order_no}: {number(line.qty)} units by {month(line.order_month)} not funded",
                    line.cost_gbp,
                )
            )
    for flag in p.flags:
        if flag.startswith("Capacity"):
            counted = (p.stockout.lost_sales_gbp if p.stockout else 0.0) + (
                p.later_shortfall_gbp
            )
            built["Capacity blocks order"].append(
                (p, flag, round(max(p.lost_sales_after_plan_gbp - counted, 0.0), 2))
            )
        elif flag.startswith("Short"):
            built["Short after plan"].append((p, flag, p.later_shortfall_gbp))
        elif flag.startswith("Overstocked"):
            built["Overstocked"].append((p, flag, p.tied_up_gbp))
        else:
            built["Inbound arrives after horizon"].append((p, flag, 0.0))
built = {name: sorted(rows, key=lambda r: -r[2]) for name, rows in built.items()}
for name in sorted(
    built, key=lambda n: (n != "Lead time", -sum(r[2] for r in built[n]))
):
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
                        "Product": p.description.title(),
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
                "Product": st.column_config.TextColumn(width=260),
                "Code": st.column_config.TextColumn(width="small"),
                "Flag": st.column_config.TextColumn(width="large"),
                "£": RIGHT,
            },
        )
