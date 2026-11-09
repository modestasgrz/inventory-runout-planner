import pandas as pd
from inventory_runout_planner.models import Product
from inventory_runout_planner.synthetic import generate
from runout_toy import DATA_DIR


def test_ac_03_synthetic_csv() -> None:
    """AC-03: products_synthetic.csv has the Product columns, one row per demand code, every row validates,
    and synthetic.generate(history, prices, seed=42) reproduces it exactly."""
    products = pd.read_csv(
        DATA_DIR / "products_synthetic.csv", dtype={"stock_code": str}
    )
    demand = pd.read_csv(
        DATA_DIR / "demand_monthly.csv", dtype={"stock_code": str, "month": str}
    )
    prices = pd.read_csv(DATA_DIR / "median_prices.csv", dtype={"stock_code": str})
    assert list(products.columns) == list(Product.model_fields)
    assert sorted(products["stock_code"]) == sorted(set(demand["stock_code"]))
    rows = [Product.model_validate(r) for r in products.to_dict("records")]
    history = {
        code: g.sort_values("month")["units"].astype(int).tolist()
        for code, g in demand.groupby("stock_code")
    }
    price_map = dict(
        zip(prices["stock_code"], prices["median_price"].astype(float), strict=True)
    )
    regenerated = generate(history, price_map, seed=42)
    assert sorted(regenerated, key=lambda p: p.stock_code) == sorted(
        rows, key=lambda p: p.stock_code
    )
