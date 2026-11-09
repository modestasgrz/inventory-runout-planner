from pathlib import Path

import pandas as pd
from inventory_runout_planner.models import PlannerData, Product
from loguru import logger

DEMAND_FILE = "demand_monthly.csv"
PRODUCTS_FILE = "products_synthetic.csv"


class DataError(Exception):
    pass


def load(data_dir: Path) -> PlannerData:
    for name in (DEMAND_FILE, PRODUCTS_FILE):
        if not (data_dir / name).is_file():
            raise DataError(f"Data file not found: {name}")
    demand = pd.read_csv(
        data_dir / DEMAND_FILE, dtype={"stock_code": str, "month": str}
    )
    table = pd.read_csv(data_dir / PRODUCTS_FILE, dtype={"stock_code": str})
    months = sorted(demand["month"].unique())
    history = {
        str(code): group.set_index("month")["units"]
        .reindex(months, fill_value=0)
        .astype(int)
        .tolist()
        for code, group in demand.groupby("stock_code")
    }
    products = [Product.model_validate(row) for row in table.to_dict("records")]
    missing = [p.stock_code for p in products if p.stock_code not in history]
    if missing:
        raise DataError(f"No demand history for: {', '.join(missing)}")
    logger.info("Loaded {} products, {} history months", len(products), len(months))
    return PlannerData(products=products, history=history, history_months=months)
