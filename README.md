# Inventory run-out planner

A what-if purchasing planner in Streamlit. It answers the questions a purchasing manager usually works through in a spreadsheet each month: **which products run out, when, what is holding each one back, and what should I reorder within this month's budget?**

Demand is real: monthly units for 36 products of a UK online gift and homeware wholesaler (UCI Online Retail II, Dec 2009 – Nov 2011). Stock on hand, lead times, MOQ, unit cost, warehouse capacity and open inbound orders are **synthetic**, generated with a fixed seed, and labelled as such on every page.

![Overview](docs/screenshots/1440-overview.png)

## What it shows

| Page | What you get |
| --- | --- |
| Overview | KPI cards, the earliest run-out with its limiting factor and, when an order can't arrive in time, how long it is out of stock and the sales lost; last year's forecast error; the products to order now; run-outs by month; flags grouped by type with their £ |
| Forecast | Per product: recent real demand, the forecast, projected stock with and without the next order, and the month-by-month table behind it |
| Scenarios | The current assumptions and all five presets side by side: products at risk, unfunded orders and £, lost sales, stock-out months, earliest run-out, spend against budget |
| Reorder plan | The next order per product by order month, with its urgency rank, budget against spend, the reason behind every line with its numbers, stock value, 4 CSV exports |
| Methodology | Every formula, the data cleaning, the synthetic-data rules, the forecast backtest and the hand-calculated test cases |

The sidebar holds the scenario: horizon (6–12 months), demand growth, supplier delay, purchase budget, safety stock and forecast method. Presets: **Baseline**, **Peak season +25%**, **Supplier delay +3 weeks**, **Tight budget**, **Efficiency**. Editing any input switches the preset to **Custom**; picking a preset reloads its values. **Reset to Baseline** puts everything back. Every page recalculates from the same scenario, so a KPI shows the same value everywhere. Invalid inputs (e.g. a negative budget) show a clear message instead of numbers.

## Results on the real demand data (Baseline: £100 000 budget, 12 months, 1 month safety stock)

| | Baseline | Peak season +25% | Supplier delay +3 weeks | Tight budget (£50 000) | Efficiency (½ month safety) |
| --- | --- | --- | --- | --- | --- |
| Products at risk (still losing sales after the plan) | 7 | 20 | 14 | 26 | 4 |
| Lost sales after plan / if nothing ordered | £69 298 / £560 063 | £251 140 / £767 286 | £103 393 / £560 063 | £337 325 / £560 063 | £32 160 / £560 063 |
| Funded / suggested spend | £99 993 / £124 083 | £99 984 / £162 296 | £99 772 / £127 909 | £49 834 / £124 083 | £94 251 / £111 367 |
| Unfunded orders | 5 (£24 091) | 14 (£62 312) | 8 (£28 137) | 24 (£74 249) | 1 (£17 116) |
| Stock-out months (product-months short after the plan) | 24 | 99 | 46 | 162 | 7 |
| Earliest run-out | Dec 2011 · 84347, lead time | Dec 2011 · 85099B, lead time | Dec 2011 · 84347, lead time | Dec 2011 · 84347, lead time | Dec 2011 · 84347, lead time |

Lost sales are unmet units × the product's real median selling price. "After plan" counts the months up to the end of each funded order's 3-month cover. Shortfalls after that need a further order, which this plan doesn't make; they are flagged separately (£323 895 on Baseline) and not counted.

ROTATING SILVER ANGELS T-LIGHT HLDR (84347) runs out in Dec 2011 and its supplier needs 10 weeks: even an order placed today arrives in March, so it is out of stock for 3 months, 1 006 units, about £2 565 of sales. A +3-week supplier delay pushes the open purchase order for JUMBO BAG RED RETROSPOT (85099B) from January into February, so it runs out in January instead of after April.

**How good is the forecast?** Forecasting Dec 2010–Nov 2011 from the year before and checking it against what actually sold gives a weighted error (WAPE = Σ |actual − forecast| ÷ Σ actual) of 61 % for the seasonal method and 93 % for the 3-month average. The plain average of per-product percentage errors is 171 %. It is inflated by months with almost no sales, where a normal forecast scores hundreds of percent.

![Reorder plan](docs/screenshots/1440-reorder-plan.png)

## How the numbers are made

- **Forecast:** same calendar month last year × (1 + growth %), or the mean of the last 3 months × (1 + growth %). Rounded half up to whole units.
- **Projection:** available = opening + inbound; shipped = min(demand, available); unmet = demand − shipped; closing = available − shipped. Stock never goes negative; a shortfall is unmet demand. Run-out = first month with unmet demand.
- **Lead time:** `ceil((lead time weeks + delay weeks) × 7 / 30.44)` months.
- **Next order:** triggered by the first month below safety stock; ordered early enough to arrive by then; quantity = 3 months of forecast + safety stock − stock available at arrival, at least the MOQ, at most the free warehouse capacity.
- **Ranking and budget:** urgency = run-out month, then value at risk (unmet units × unit cost). Funded in urgency order while each order fits the budget left.
- **Money:** lost sales = unmet units × median selling price; £ tied up = (stock on hand − 6 months of average forecast) × unit cost for overstocked products.
- **Limiting factor:** *lead time* (an order now arrives too late), *capacity*, *budget*, *stock* (ordering now fixes it) or *none*.

Full detail on the Methodology page and in [`specs/inventory-runout-planner.md`](specs/inventory-runout-planner.md).

## Tests

- 48 acceptance tests, one per acceptance criterion in the spec. They include hand-calculated cases, e.g. 100 units in stock, 60 a month, lead time 4 weeks → runs out Jan 2012, order 200 units = 180 + 60 − 40, £400.00, and a 10-week lead time → out of stock Jan–Feb 2012, 80 units, £400 lost sales.
- 511 unit tests on the calculation core. They cover property tests over random products and scenarios (stock is conserved and never negative, spend ≤ budget, ranking order, lost sales and later shortfalls add up), every input boundary, data-file error paths, the backtest and exact half-up rounding.
- 296 more Streamlit `AppTest` checks on top of the acceptance tests. Every page renders under every preset and edge input, and the KPI cards match the core across all pages. Flag groups add up to the KPIs. Presets move the KPIs and Reset restores them. Bad input and missing data files show a clear message.

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
