import pandas as pd
import streamlit as st
from inventory_runout_planner.presets import ATTRIBUTION

st.caption(
    "Every number in the app comes from these rules. The calculation core is plain Python with unit tests; nothing is estimated by hand."
)

st.markdown(
    """
### Data
- **Demand (real):** monthly units sold for 36 products from the public UCI Online Retail II dataset (a UK online gift and homeware wholesaler), Dec 2009 – Nov 2011.
  Cleaning: exact duplicate rows removed; cancelled (`C…`) and adjustment (`A…`) invoices removed; product codes only (5 digits + optional letters); quantity and price > 0.
  The 36 products are the top sellers by units among products that sold in at least 22 of the 24 months.
- **Groups:** assigned from the product description: `BAG` / `SHOPPER` → Bags & storage; `T-LIGHT` / `LIGHT` → Candles & lights;
  `CAKE CASES`, `NAPKINS`, `BUNTING`, `POPCORN`, `PAPER CHAIN`, `PLACE SETTING` → Baking & party; everything else → Gifts & small goods.
- **Stock data (synthetic):** stock on hand, supplier lead time, MOQ, warehouse capacity, open inbound order and unit cost (60 % of the product's real median selling price)
  come from a seeded generator (seed 42). A few products are set on purpose to show typical situations: one blocked by lead time, one to order now, one overstocked, one with an inbound order, one fine.

### Forecast (month 1 = Dec 2011)
- **Seasonal naive (default):** forecast = units sold in the same calendar month last year × (1 + growth %), rounded half up.
- **Trailing 3-month average:** forecast = mean(Sep, Oct, Nov 2011) × (1 + growth %), the same every month.

### Projection if nothing is ordered
- Lead months = `ceil((lead time weeks + delay weeks) × 7 / 30.44)`; an order placed at the start of month *m* arrives at the start of month *m* + lead months.
  An open inbound order arrives at month `1 + ceil((inbound weeks + delay weeks) × 7 / 30.44)`.
- Each month: available = opening + inbound · shipped = min(demand, available) · unmet = demand − shipped · closing = available − shipped. Stock never goes negative; a shortfall is unmet demand.
- **Run-out month** = the first month with unmet demand. **Value at risk** = unmet units over the horizon × unit cost.

### Next order per product
- Safety stock (units) = safety months × that month's forecast, rounded half up.
- Trigger = first month where closing stock < safety stock, or demand is unmet. Order month = max(Dec 2011, trigger − lead months); it arrives lead months later.
- Quantity = forecast of the 3 months from arrival + safety stock at arrival − stock available at arrival, at least the MOQ, at most the free warehouse capacity
  (capacity − available). If the free capacity is below the MOQ, no order is possible.
- **Ranking:** run-out month (earliest first; no run-out last) → value at risk (highest first) → product code.
- **Budget:** orders are funded in rank order while their cost fits the budget left; an order that doesn't fit is skipped and the next one is tried.
- **Limiting factor:** no run-out → *none*; the order would arrive after the run-out → *lead time*; no order fits the warehouse → *capacity*;
  the order isn't funded → *budget*; otherwise *stock* (ordering now prevents the run-out).

### KPIs
- **Products at risk** = products that run out within their lead time + 1 month if nothing is ordered (order now).
- **Earliest run-out** = the product with the earliest run-out month (ties: higher value at risk).
- **Purchase spend** = Σ cost of funded orders, shown against the budget. **Unfunded orders** = suggested orders not funded. **Stock value** = Σ stock on hand × unit cost.
- **Overstocked** flag = stock on hand > 6 months of average forecast demand.
"""
)

st.subheader("Hand-calculated test cases")
st.caption(
    "Toy products, 60 units of demand every month, horizon 6 months, budget £1 000, safety 1 month, lead 4 weeks, MOQ 50, capacity 400, unit cost £2.00 unless stated. Each row is an automated acceptance test."
)
st.dataframe(
    pd.DataFrame(
        [
            [
                "AC-07",
                "100 in stock",
                "Dec: 100 → 40 · Jan: 40 shipped, 20 unmet → run-out Jan 2012; value at risk 260 × £2 = £520.00; cover 100 / 60 = 1.67 months",
            ],
            [
                "AC-08",
                "Same product",
                "Order Dec 2011, arrives Jan 2012: 200 units = 180 (3 months) + 60 safety − 40 available; £400.00; limiting factor stock",
            ],
            [
                "AC-09",
                "Lead time 10 weeks",
                "ceil(70 / 30.44) = 3 months → arrives Mar 2012 after the Jan run-out → lead time; 240 units, £480.00",
            ],
            [
                "AC-10",
                "3 products, budget £650",
                "Ranks 1–3; £400 funded, £480 skipped (only £250 left), £200 funded → £600.00 funded of £1 080.00",
            ],
            ["AC-11", "Budget £300", "£400 order not funded → limiting factor budget"],
            [
                "AC-12",
                "Capacity 200 / MOQ 400",
                "Capacity 200: room 160 → 160 units · MOQ 400 > room 360 → no order, capacity",
            ],
            [
                "AC-13",
                "70 in stock + 200 inbound in 3 weeks",
                "Inbound Jan → run-out Apr 2012, order Mar for Apr, 150 units · +3 weeks delay: inbound Feb, run-out Jan → lead time",
            ],
            [
                "AC-14",
                "1 000 in stock, 12 months",
                "No run-out, no order; 1 000 / 60 = 16.7 months of cover → Overstocked",
            ],
        ],
        columns=["Test", "Setup", "Expected result"],
    ),
    hide_index=True,
    width="stretch",
)

st.subheader("Sources")
st.markdown(ATTRIBUTION)
