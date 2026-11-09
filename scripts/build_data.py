"""Build the committed data files: real monthly demand (UCI Online Retail II, CC BY 4.0) + seeded synthetic stock data.

Usage: uv run python scripts/build_data.py
"""

import hashlib
import io
import re
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
from inventory_runout_planner.synthetic import generate
from loguru import logger

SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
RAW_NAME = "online_retail_II.xlsx"
DATA = Path(__file__).resolve().parents[1] / "data"
FIRST, LAST = "2009-12", "2011-11"
MIN_MONTHS, TOP_N, SEED = 22, 36, 42
GROUP_RULES = [
    (("BAG", "SHOPPER"), "Bags & storage"),
    (("T-LIGHT", "LIGHT"), "Candles & lights"),
    (
        ("CAKE CASES", "NAPKINS", "BUNTING", "POPCORN", "PAPER CHAIN", "PLACE SETTING"),
        "Baking & party",
    ),
]


def group_of(description: str) -> str:
    return next(
        (group for words, group in GROUP_RULES if any(w in description for w in words)),
        "Gifts & small goods",
    )


def raw_file() -> Path:
    target = DATA / "raw" / RAW_NAME
    if target.is_file():
        return target
    logger.info("Downloading UCI Online Retail II")
    with urllib.request.urlopen(
        "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip",
        timeout=120,
    ) as response:
        payload: bytes = response.read()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("UCI archive checksum mismatch")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        target.write_bytes(archive.read(RAW_NAME))
    return target


def main() -> None:
    sheets = pd.read_excel(
        raw_file(), sheet_name=None, dtype={"Invoice": str, "StockCode": str}
    )
    df = pd.concat(sheets.values(), ignore_index=True).drop_duplicates()
    df = df[
        ~df["Invoice"].str.startswith(("C", "A"))
        & df["StockCode"].str.match(re.compile(r"^\d{5}[A-Za-z]*$"))
        & (df["Quantity"] > 0)
        & (df["Price"] > 0)
    ].copy()
    df["month"] = pd.to_datetime(df["InvoiceDate"]).dt.strftime("%Y-%m")
    df = df[(df["month"] >= FIRST) & (df["month"] <= LAST)]
    df["Description"] = df["Description"].fillna("").astype(str).str.strip()
    months = sorted(df["month"].unique())
    units = (
        df.groupby(["StockCode", "month"])["Quantity"]
        .sum()
        .unstack(fill_value=0)
        .reindex(columns=months, fill_value=0)
    )
    eligible = units[(units > 0).sum(axis=1) >= MIN_MONTHS]
    totals = (
        eligible.sum(axis=1)
        .rename("total")
        .reset_index()
        .sort_values(["total", "StockCode"], ascending=[False, True])
    )
    codes = totals["StockCode"].head(TOP_N).tolist()
    kept = df[df["StockCode"].isin(codes)]
    descriptions = kept.groupby("StockCode")["Description"].agg(lambda s: min(s.mode()))
    prices = kept.groupby("StockCode")["Price"].median()

    demand = (
        units.loc[codes]
        .rename_axis(columns=None)
        .reset_index()
        .melt(id_vars="StockCode", var_name="month", value_name="units")
        .rename(columns={"StockCode": "stock_code"})
    )
    demand.insert(1, "description", demand["stock_code"].map(descriptions))
    demand.insert(2, "group", demand["description"].map(group_of))
    demand = demand[
        ["stock_code", "description", "group", "month", "units"]
    ].sort_values(["stock_code", "month"])
    demand.to_csv(DATA / "demand_monthly.csv", index=False)
    pd.DataFrame(
        {"stock_code": codes, "median_price": [float(prices[c]) for c in codes]}
    ).sort_values("stock_code").to_csv(DATA / "median_prices.csv", index=False)

    history = {c: [int(v) for v in units.loc[c]] for c in codes}
    names = {c: (str(descriptions[c]), group_of(str(descriptions[c]))) for c in codes}
    products = generate(history, {c: float(prices[c]) for c in codes}, names, seed=SEED)
    pd.DataFrame([p.model_dump() for p in products]).to_csv(
        DATA / "products_synthetic.csv", index=False
    )
    logger.info("Wrote {} products × {} months", len(codes), len(months))


if __name__ == "__main__":
    main()
