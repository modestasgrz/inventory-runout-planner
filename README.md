# Inventory run-out planner

A what-if purchasing planner in Streamlit. It answers the questions a purchasing manager usually works through in a spreadsheet each month: **which products run out, when, what is holding each one back, and what should I reorder within this month's budget?**

Demand is real: monthly units for 36 products of a UK online gift and homeware wholesaler (UCI Online Retail II, Dec 2009 – Nov 2011). Stock on hand, lead times, MOQ, unit cost, warehouse capacity and open inbound orders are **synthetic**, generated with a fixed seed, and labelled as such on every page.

![Overview](docs/screenshots/1440-overview.png)

## What it shows

| Page | What you get |
| --- | --- |
| Overview | A three-line summary in plain words (the question, where things stand, what to do first); KPI cards with plain-words help; the earliest run-out as one decision: how long it is out of stock, what was ordered and when it arrives, the sales lost; the products to order now; run-outs by month; flags grouped by type with their £ |
| Forecast | Per product: recent real demand and the forecast with a range from last year's forecast error, stock at month end with the plan and if nothing is ordered, every order and the month-by-month table behind it |
| Scenarios | All five presets side by side: products at risk, lost sales and the change against Baseline, unfunded orders and £, earliest run-out, spend against budget |
| Reorder plan | Every order in the plan, the next one and up to 3 follow-ups per product, by urgency, with its status, budget against spend, the reason behind every line with its numbers, stock value, 4 CSV exports |
| Methodology | Every formula, the data cleaning, the synthetic-data rules, the forecast backtest and the hand-calculated test cases |

The sidebar holds the scenario: horizon (6–12 months), demand growth, supplier delay, purchase budget for the whole horizon, safety stock and forecast method. Presets: **Baseline**, **Peak season +25%**, **Supplier delay +3 weeks**, **Tight budget**, **Efficiency**. Editing any input switches the preset to **Custom**; picking a preset reloads its values. **Reset to Baseline** puts everything back. Every page recalculates from the same scenario, so a KPI shows the same value everywhere. Invalid inputs (e.g. a negative budget) show a clear message instead of numbers.

## Results on the real demand data (Baseline: £350 000 budget for 12 months, 1 month safety stock)

| | Baseline | Peak season +25% | Supplier delay +3 weeks | Tight budget (£175 000) | Efficiency (½ month safety) |
| --- | --- | --- | --- | --- | --- |
| Lost sales with the plan (12 months) | £29 145 | £193 215 | £36 912 | £269 499 | £31 545 |
| vs Baseline | — | +£164 069 | +£7 767 | +£240 354 | +£2 400 |
| Lost sales if nothing is ordered | £560 063 | £767 286 | £560 063 | £560 063 | £560 063 |
| Products at risk (still short in some month with the plan) | 10 | 30 | 13 | 32 | 18 |
| Funded / suggested spend | £349 968 / £424 587 | £349 902 / £544 581 | £349 968 / £419 600 | £174 779 / £424 587 | £349 969 / £401 082 |
| Orders in the plan / unfunded | 118 / 24 (£74 620) | 129 / 45 (£194 679) | 117 / 23 (£69 632) | 118 / 65 (£249 808) | 114 / 20 (£51 113) |
| Earliest run-out | Dec 2011 · 84347, lead time | Dec 2011 · 85099B, lead time | Dec 2011 · 84347, lead time | Dec 2011 · 84347, lead time | Dec 2011 · 84347, lead time |

Lost sales are unmet units × the product's real median selling price, over the whole horizon, with every funded order. Each product gets its next order plus up to 3 follow-ups (about one a quarter), each placed one lead time before stock dips again. All orders compete for the same budget by urgency, and a follow-up is funded only if the order before it is. Cutting safety stock (Efficiency) frees budget for more orders but still loses more sales than Baseline.

ROTATING SILVER ANGELS T-LIGHT HLDR (84347) runs out in Dec 2011 and its supplier needs 10 weeks: even an order placed today arrives in March, so it is out of stock Dec 2011–Feb 2012, about £2 565 of sales. Its follow-up arriving in August covers the autumn peak until November, when 2 948 units (about £7 517) are still short because the next follow-up doesn't fit the budget. A +3-week supplier delay pushes the open purchase order for JUMBO BAG RED RETROSPOT (85099B) from January into February, so it runs out in January instead of after April.

**How good is the forecast?** Forecasting Dec 2010–Nov 2011 from the year before and checking it against what actually sold gives a weighted error (WAPE = Σ |actual − forecast| ÷ Σ actual) of 61 % for the seasonal method and 93 % for the 3-month average. The Forecast page draws that as a range around each forecast. The plain average of per-product percentage errors is 171 %. It is inflated by months with almost no sales, where a normal forecast scores hundreds of percent.

![Reorder plan](docs/screenshots/1440-reorder-plan.png)

## How the numbers are made

- **Forecast:** same calendar month last year × (1 + growth %), or the mean of the last 3 months × (1 + growth %). Rounded half up to whole units.
- **Projection:** available = opening + inbound; shipped = min(demand, available); unmet = demand − shipped; closing = available − shipped. Stock never goes negative; a shortfall is unmet demand. Run-out = first month with unmet demand.
- **Lead time:** `ceil((lead time weeks + delay weeks) × 7 / 30.44)` months.
- **Orders:** the next order is triggered by the first month below safety stock and placed early enough to arrive by then; quantity = 3 months of forecast + safety stock − stock available at arrival, at least the MOQ, at most the free warehouse capacity. Up to 3 follow-ups per product are planned the same way on the projection that includes the earlier orders.
- **Ranking and budget:** urgency = the month an order prevents a shortfall, then value at risk (unmet units × unit cost). Funded in urgency order while each order fits the budget left; a follow-up only if the order before it is funded.
- **Money:** lost sales = unmet units × median selling price; £ tied up = (stock on hand − 6 months of average forecast) × unit cost for overstocked products.
- **Limiting factor:** *lead time* (an order now arrives too late), *capacity*, *budget*, *stock* (ordering now fixes it) or *none*.

Full detail on the Methodology page and in [`specs/inventory-runout-planner.md`](specs/inventory-runout-planner.md).

## Tests

- 51 acceptance tests, one per acceptance criterion in the spec. They include hand-calculated cases, e.g. 100 units in stock, 60 a month, lead time 4 weeks → runs out Jan 2012, order 200 units = 180 + 60 − 40, £400.00, then a follow-up of 180 units arriving Apr 2012 so nothing is lost.
- 781 unit tests on the calculation core. They cover property tests over random products and scenarios (stock is conserved and never negative, spend ≤ budget, ranking order, a funded follow-up always has its earlier order funded, lost sales add up), an independent re-implementation of the follow-up rules, every input boundary, data-file error paths, the backtest and exact half-up rounding.
- 319 more Streamlit `AppTest` checks on top of the acceptance tests. Every page renders under every preset and edge input, and the KPI cards match the core across all pages. Flag groups add up to the KPIs. The run-out card, reorder table and scenario comparison match the core. Presets move the KPIs and Reset restores them. Bad input and missing data files show a clear message.

## Run it yourself

```bash
uv sync
make run                       # http://127.0.0.1:8786
make test                      # unit tests
uv run pytest tests/acceptance # acceptance tests
```

The committed `data/` files are enough to run the app. To rebuild them from the original dataset (downloads ~45 MB, checks its SHA-256):

```bash
uv run python scripts/build_data.py
```

Screenshots: start the app, then `uv run python tools/screenshots.py` (needs `uv run playwright install chromium` once).

Stack: Python 3.12, Streamlit 1.67 (pinned), Plotly, pandas, Pydantic. The calculation core in `src/inventory_runout_planner/` has no Streamlit imports; the app in `app.py` + `app_pages/` only displays its results. `requirements.txt` is exported from `uv.lock` for Streamlit Community Cloud.

## Data and licence

Demand data: Chen, D. (2012). *Online Retail II*. UCI Machine Learning Repository. CC BY 4.0. https://doi.org/10.24432/C5CG6D

Only product-level monthly aggregates are committed (no customer ids, invoices or countries). Stock, lead times, MOQ, unit cost (60 % of the real median selling price), capacity and inbound orders are synthetic and for demonstration only.
