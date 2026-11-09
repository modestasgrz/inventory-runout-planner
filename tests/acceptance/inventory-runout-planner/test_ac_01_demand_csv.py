import pandas as pd
from runout_toy import DATA_DIR, MONTHS

# Top 36 codes by units with units > 0 in >= 22 of 24 months (DEC-03), computed from the real file on 2026-11-09.
EXPECTED_CODES = {
    "84077",
    "85099B",
    "21212",
    "85123A",
    "22197",
    "84879",
    "17003",
    "21977",
    "84991",
    "15036",
    "84755",
    "21213",
    "20725",
    "22178",
    "22386",
    "21232",
    "84568",
    "85099F",
    "84946",
    "21915",
    "84992",
    "22086",
    "71459",
    "21982",
    "20724",
    "21980",
    "21975",
    "21080",
    "22355",
    "84347",
    "85099C",
    "16014",
    "21931",
    "21731",
    "47566",
    "22151",
}


def test_ac_01_demand_csv() -> None:
    """AC-01: demand_monthly.csv has the exact columns, 36 codes x 24 months = 864 rows, integer units >= 0,
    every product sold in >= 22 months, and the codes are the DEC-03 top 36."""
    df = pd.read_csv(
        DATA_DIR / "demand_monthly.csv", dtype={"stock_code": str, "month": str}
    )
    assert list(df.columns) == ["stock_code", "description", "group", "month", "units"]
    assert len(df) == 864
    assert set(df["stock_code"]) == EXPECTED_CODES
    assert sorted(set(df["month"])) == MONTHS
    assert df.groupby("stock_code")["month"].nunique().eq(24).all()
    assert pd.api.types.is_integer_dtype(df["units"])
    assert (df["units"] >= 0).all()
    assert (df[df["units"] > 0].groupby("stock_code")["month"].nunique() >= 22).all()
