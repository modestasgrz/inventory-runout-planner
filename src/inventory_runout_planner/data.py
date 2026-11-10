from pathlib import Path

import pandas as pd
from inventory_runout_planner.models import PlannerData, Product
from loguru import logger
from pydantic import ValidationError

DEMAND_FILE = "demand_monthly.csv"
PRODUCTS_FILE = "products_synthetic.csv"
PRICES_FILE = "median_prices.csv"
DEMAND_COLUMNS = ["stock_code", "description", "group", "month", "units"]
MAX_UNITS = 10_000_000
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
    frames = {}
    for name in (DEMAND_FILE, PRODUCTS_FILE):
        try:
            frames[name] = pd.read_csv(
                data_dir / name, dtype={"stock_code": str, "month": str}
            )
        except (ValueError, pd.errors.ParserError) as e:
            raise DataError(f"{name}: unreadable ({type(e).__name__})") from e
    demand, table = frames[DEMAND_FILE], frames[PRODUCTS_FILE]
    for name, frame, columns in (
        (DEMAND_FILE, demand, DEMAND_COLUMNS),
        (PRODUCTS_FILE, table, list(Product.model_fields)),
    ):
        missing_columns = [c for c in columns if c not in frame.columns]
        if missing_columns:
            raise DataError(f"{name}: missing column {missing_columns[0]}")
    if demand[["stock_code", "month"]].isna().any().any():
        raise DataError(f"{DEMAND_FILE}: blank stock_code or month")
    units = pd.to_numeric(demand["units"], errors="coerce")
    if (
        units.isna().any()
        or (units < 0).any()
        or (units > MAX_UNITS).any()
        or not (units % 1 == 0).all()
    ):
        raise DataError(
            f"{DEMAND_FILE}: units must be whole numbers from 0 to {MAX_UNITS}"
        )
    if demand.duplicated(["stock_code", "month"]).any():
        raise DataError(f"{DEMAND_FILE}: duplicate product + month rows")
    if sorted(demand["month"].unique()) != HISTORY_MONTHS:
        raise DataError(f"{DEMAND_FILE}: months must be exactly 2009-12 to 2011-11")
    if table.empty:
        raise DataError(f"{PRODUCTS_FILE}: no products")
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
    if not (data_dir / PRICES_FILE).is_file():
        raise DataError(f"Data file not found: {PRICES_FILE}")
    try:
        price_table = pd.read_csv(data_dir / PRICES_FILE, dtype={"stock_code": str})
        values = pd.to_numeric(price_table["median_price"], errors="coerce")
        prices = {
            str(c): float(v)
            for c, v in zip(price_table["stock_code"], values, strict=True)
        }
    except (ValueError, KeyError, pd.errors.ParserError) as e:
        raise DataError(f"{PRICES_FILE}: unreadable ({type(e).__name__})") from e
    for p in products:
        if not prices.get(p.stock_code, 0) > 0:
            raise DataError(f"{PRICES_FILE}: no price for {p.stock_code}")
    logger.info(
        "Loaded {} products, {} history months", len(products), len(HISTORY_MONTHS)
    )
    return PlannerData(
        products=products,
        history=history,
        history_months=HISTORY_MONTHS,
        prices=prices,
    )
