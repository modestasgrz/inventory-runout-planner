import pandas as pd
from runout_toy import DATA_DIR

RULES = [
    (("BAG", "SHOPPER"), "Bags & storage"),
    (("T-LIGHT", "LIGHT"), "Candles & lights"),
    (
        ("CAKE CASES", "NAPKINS", "BUNTING", "POPCORN", "PAPER CHAIN", "PLACE SETTING"),
        "Baking & party",
    ),
]


def expected_group(description: str) -> str:
    return next(
        (group for words, group in RULES if any(w in description for w in words)),
        "Gifts & small goods",
    )


def test_ac_02_groups() -> None:
    """AC-02: every group is one of the 4 DEC-04 groups, assigned by the keyword rule from the description."""
    df = pd.read_csv(DATA_DIR / "demand_monthly.csv", dtype={"stock_code": str})
    assert set(df["group"]) <= {
        "Bags & storage",
        "Candles & lights",
        "Baking & party",
        "Gifts & small goods",
    }
    for description, group in (
        df[["description", "group"]].drop_duplicates().itertuples(index=False)
    ):
        assert group == expected_group(description), description
