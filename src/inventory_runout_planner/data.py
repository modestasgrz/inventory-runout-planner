from pathlib import Path

import pandas as pd
from inventory_runout_planner.models import PlannerData, Product
from loguru import logger
from pydantic import ValidationError

DEMAND_FILE = "demand_monthly.csv"
PRODUCTS_FILE = "products_synthetic.csv"
HISTORY_MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)


class DataError(Exception):
    pass


def load(data_dir: Path) -> PlannerData:
    """Read and check both data files; every problem becomes a DataError with a one-line message."""
    for name in (DEMAND_FILE, PRODUCTS_FILE):
        if not (data_dir / name).is_file():
            raise DataError(f"Data file not found: {name}")
    try:
        demand = pd.read_csv(
            data_dir / DEMAND_FILE, dtype={"stock_code": str, "month": str}
        )
        table = pd.read_csv(data_dir / PRODUCTS_FILE, dtype={"stock_code": str})
        units = pd.to_numeric(demand["units"], errors="raise")
    except (ValueError, KeyError, pd.errors.ParserError) as e:
        raise DataError(f"Data file unreadable: {type(e).__name__}") from e
    if units.isna().any() or (units < 0).any() or not (units % 1 == 0).all():
        raise DataError(f"{DEMAND_FILE}: units must be whole numbers ≥ 0")
    if demand.duplicated(["stock_code", "month"]).any():
        raise DataError(f"{DEMAND_FILE}: duplicate product + month rows")
    if sorted(demand["month"].unique()) != HISTORY_MONTHS:
        raise DataError(f"{DEMAND_FILE}: months must be exactly 2009-12 to 2011-11")
    if table["stock_code"].duplicated().any():
        raise DataError(f"{PRODUCTS_FILE}: duplicate stock codes")
    demand["units"] = units.astype(int)
    history = {
        str(code): group.set_index("month")["units"]
        .reindex(HISTORY_MONTHS, fill_value=0)
        .tolist()
        for code, group in demand.groupby("stock_code")
    }
    try:
        products = [Product.model_validate(row) for row in table.to_dict("records")]
    except ValidationError as e:
        bad = e.errors()[0]
        raise DataError(f"{PRODUCTS_FILE}: invalid {bad['loc'][0]}") from e
    missing = [p.stock_code for p in products if p.stock_code not in history]
    if missing:
        raise DataError(f"No demand history for: {', '.join(missing)}")
    logger.info(
        "Loaded {} products, {} history months", len(products), len(HISTORY_MONTHS)
    )
    return PlannerData(
        products=products, history=history, history_months=HISTORY_MONTHS
    )
