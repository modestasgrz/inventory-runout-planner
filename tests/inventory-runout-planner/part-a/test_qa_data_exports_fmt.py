import importlib.util
import math
from decimal import Decimal
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from inventory_runout_planner.data import DataError, load
from inventory_runout_planner.exports import tables
from inventory_runout_planner.fmt import gbp, month, number, units
from inventory_runout_planner.models import (
    Kpis,
    MonthRow,
    PlannerData,
    Product,
    ReorderLine,
    Scenario,
)
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from inventory_runout_planner.synthetic import generate, round_up

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "data"
N = " "
PRODUCT_COLS = [
    "stock_code",
    "description",
    "group",
    "unit_cost",
    "stock_on_hand",
    "lead_time_weeks",
    "moq",
    "capacity",
    "inbound_qty",
    "inbound_weeks",
]
PROD_HEADER = ",".join(PRODUCT_COLS)


# ---------- fmt ----------


def ri(rng: np.random.Generator, low: int, high: int) -> int:
    return int(rng.integers(low, high + 1))


def pick[T](rng: np.random.Generator, options: list[T]) -> T:
    return options[int(rng.integers(len(options)))]


def test_number_rounding_and_zero() -> None:
    assert number(0) == "0"
    assert number(0.5) == "1"
    assert number(1.5) == "2"
    assert number(2.5) == "3"
    assert number(0.49) == "0"
    assert number(999.5) == f"1{N}000"
    assert number(999) == "999"
    assert number(1000) == f"1{N}000"
    assert number(100000) == f"100{N}000"


def test_number_large_values_use_no_scientific_notation() -> None:
    assert number(1e15) == f"1{N}000{N}000{N}000{N}000{N}000"
    assert number(1e16) == f"10{N}000{N}000{N}000{N}000{N}000"
    assert number(123456789012) == f"123{N}456{N}789{N}012"
    assert gbp(1e9) == f"£1{N}000{N}000{N}000"


def test_number_small_values() -> None:
    assert number(1e-7) == "0"
    assert gbp(1e-7, pence=True) == "£0.00"


def test_number_negative_values() -> None:
    assert number(-1234) == f"-1{N}234"
    assert number(-0.5) == "-1"
    assert gbp(-5) in ("£-5", "-£5")


def test_number_small_negative_does_not_render_negative_zero() -> None:
    assert number(-0.4) == "0"
    assert gbp(-0.4) == "£0"
    assert gbp(-0.001, pence=True) == "£0.00"


def test_gbp_pence_rounding() -> None:
    assert gbp(0.005, pence=True) == "£0.01"
    assert gbp(1.005, pence=True) == "£1.01"
    assert gbp(2.675, pence=True) == "£2.68"
    assert gbp(0.004, pence=True) == "£0.00"
    assert gbp(0, pence=True) == "£0.00"
    assert gbp(1234.5) == f"£1{N}235"
    assert gbp(1234.4999) == f"£1{N}234"
    assert gbp(999999.995, pence=True) == f"£1{N}000{N}000.00"
    assert gbp(12, pence=True) == "£12.00"
    assert gbp(1234567.891, pence=True) == f"£1{N}234{N}567.89"


def test_gbp_and_units_have_no_ascii_thousands_separators() -> None:
    for text in (gbp(1234567), number(1234567), gbp(5e6, pence=True)):
        assert "," not in text
        assert " " not in text
    assert "," not in units(1234567)
    assert units(1234567).count(" ") == 1


def test_units_singular_is_still_plural() -> None:
    assert units(1) == "1 units"
    assert units(0) == "0 units"
    assert units(1234) == f"1{N}234 units"


def test_month_all_twelve_and_errors() -> None:
    names = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    for i, name in enumerate(names, start=1):
        assert month(f"2012-{i:02d}") == f"{name} 2012"
    assert month("2009-12") == "Dec 2009"
    assert month("2013-01") == "Jan 2013"
    for bad in ("2012-13", "2012-00", "garbage", ""):
        with pytest.raises(ValueError):
            month(bad)


def test_fmt_roundtrip_property() -> None:
    rng = np.random.default_rng(1)
    for _ in range(300):
        v = ri(rng, -10_000_000, 10_000_000) / pick(rng, [1, 10, 100])
        digits = number(v).replace(N, "")
        assert int(digits) == int(Decimal(str(v)).to_integral_value("ROUND_HALF_UP"))
        pence = gbp(v, pence=True)
        assert pence.startswith("£")
        assert pence[-3] == "."
        assert float(pence[1:].replace(N, "")) == pytest.approx(v, abs=0.0051)


# ---------- data.load ----------


ALL_MONTHS = (
    ["2009-12"]
    + [f"2010-{m:02d}" for m in range(1, 13)]
    + [f"2011-{m:02d}" for m in range(1, 12)]
)
DEMAND_HEAD = "stock_code,description,group,month,units\n"
OK_ROW = "1,A,g,1.0,1,1,1,1,0,0"


def pad(code: str = "PAD") -> str:
    """One row per month so the file covers all 24 months."""
    return "".join(f"{code},P,g,{m},1\n" for m in ALL_MONTHS)


def write_data(tmp: Path, demand: str, products: str) -> Path:
    (tmp / "demand_monthly.csv").write_text(demand)
    (tmp / "products_synthetic.csv").write_text(products)
    codes = [line.split(",")[0] for line in products.splitlines()[1:] if line]
    (tmp / "median_prices.csv").write_text(
        "stock_code,median_price\n" + "".join(f"{c},1.0\n" for c in codes)
    )
    return tmp


def test_load_real_data_shape() -> None:
    d = load(DATA)
    assert len(d.products) == 36
    assert d.history_months == ALL_MONTHS
    assert all(len(v) == 24 for v in d.history.values())
    assert {p.stock_code for p in d.products} == set(d.history)
    assert all(isinstance(c, str) for c in d.history)


def test_load_empty_folder_names_demand_first(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="Data file not found: demand_monthly.csv"):
        load(tmp_path)


def test_load_missing_products_file(tmp_path: Path) -> None:
    (tmp_path / "demand_monthly.csv").write_text(DEMAND_HEAD + pad())
    with pytest.raises(DataError, match="Data file not found: products_synthetic.csv"):
        load(tmp_path)


def test_load_missing_data_dir(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="Data file not found"):
        load(tmp_path / "nope")


def test_load_directory_in_place_of_file(tmp_path: Path) -> None:
    (tmp_path / "demand_monthly.csv").mkdir()
    (tmp_path / "products_synthetic.csv").write_text(PROD_HEADER + "\n")
    with pytest.raises(DataError, match="Data file not found: demand_monthly.csv"):
        load(tmp_path)


def test_load_missing_history_lists_every_code(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD + pad("111"),
        PROD_HEADER
        + "\n111,A,g,1.0,1,1,1,1,0,0\n222,B,g,1.0,1,1,1,1,0,0\n333,C,g,1.0,1,1,1,1,0,0\n",
    )
    with pytest.raises(DataError, match="No demand history for: 222, 333"):
        load(tmp_path)


def test_load_preserves_alphanumeric_and_leading_zero_codes(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD + pad("00123") + pad("85123A"),
        PROD_HEADER + "\n00123,A,g,1.0,1,1,1,1,0,0\n85123A,B,g,1.0,1,1,1,1,0,0\n",
    )
    d = load(tmp_path)
    assert set(d.history) == {"00123", "85123A"}
    assert [p.stock_code for p in d.products] == ["00123", "85123A"]


def test_load_fills_missing_months_with_zero(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD
        + pad("PAD")
        + "1,A,g,2011-09,5\n1,A,g,2011-11,8\n2,B,g,2011-10,3\n",
        PROD_HEADER + "\n1,A,g,1.0,1,1,1,1,0,0\n2,B,g,1.0,1,1,1,1,0,0\n",
    )
    d = load(tmp_path)
    assert d.history["1"] == [0] * 21 + [5, 0, 8]
    assert d.history["2"] == [0] * 22 + [3, 0]
    assert d.history_months == ALL_MONTHS


def test_load_unsorted_rows_are_sorted_by_month(tmp_path: Path) -> None:
    rows = [f"1,A,g,{m},{i}\n" for i, m in enumerate(ALL_MONTHS)]
    rows = [rows[i] for i in np.random.default_rng(3).permutation(len(rows))]
    write_data(
        tmp_path,
        DEMAND_HEAD + "".join(rows),
        PROD_HEADER + "\n" + OK_ROW + "\n",
    )
    assert load(tmp_path).history["1"] == list(range(24))


def good_dir(tmp: Path, product_row: str = OK_ROW) -> Path:
    return write_data(
        tmp, DEMAND_HEAD + pad("1"), PROD_HEADER + "\n" + product_row + "\n"
    )


def test_load_good_minimal_dir(tmp_path: Path) -> None:
    d = load(good_dir(tmp_path))
    assert d.history["1"] == [1] * 24


@pytest.mark.parametrize(
    ("row", "field"),
    [
        ("1,A,g,0,1,1,1,1,0,0", "unit_cost"),
        ("1,A,g,1.0,-1,1,1,1,0,0", "stock_on_hand"),
        ("1,A,g,1.0,1,13,1,1,0,0", "lead_time_weeks"),
        ("1,A,g,1.0,1,1,0,1,0,0", "moq"),
        ("1,A,g,1.0,1,1,1,0,0,0", "capacity"),
        ("1,A,g,1.0,1.5,1,1,1,0,0", "stock_on_hand"),
        ("1,A,g,1.0,1,1,1,1,-1,0", "inbound_qty"),
        ("1,A,g,1.0,1,1,1,1,0,-2", "inbound_weeks"),
    ],
)
def test_load_invalid_product_row_is_data_error(
    tmp_path: Path, row: str, field: str
) -> None:
    with pytest.raises(DataError, match=f"products_synthetic.csv: invalid {field}"):
        load(good_dir(tmp_path, row))


def test_load_missing_column_in_products_is_data_error(tmp_path: Path) -> None:
    write_data(tmp_path, DEMAND_HEAD + pad("1"), "stock_code,description\n1,A\n")
    with pytest.raises(DataError, match="products_synthetic.csv: missing column"):
        load(tmp_path)


def test_load_duplicate_product_codes(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD + pad("1"),
        PROD_HEADER + "\n" + OK_ROW + "\n" + OK_ROW + "\n",
    )
    with pytest.raises(
        DataError, match="products_synthetic.csv: duplicate stock codes"
    ):
        load(tmp_path)


def test_load_duplicate_demand_rows(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD + pad("1") + "1,A,g,2011-11,9\n",
        PROD_HEADER + "\n" + OK_ROW + "\n",
    )
    with pytest.raises(
        DataError, match="demand_monthly.csv: duplicate product \\+ month rows"
    ):
        load(tmp_path)


@pytest.mark.parametrize("bad", ["-1", "1.5", "", "abc", "nan"])
def test_load_bad_units(tmp_path: Path, bad: str) -> None:
    rows = pad("1").replace("2011-11,1", f"2011-11,{bad}")
    write_data(tmp_path, DEMAND_HEAD + rows, PROD_HEADER + "\n" + OK_ROW + "\n")
    with pytest.raises(
        DataError,
        match="demand_monthly.csv: units must be whole numbers from 0 to 10000000",
    ):
        load(tmp_path)


def test_load_whole_number_float_units_accepted(tmp_path: Path) -> None:
    rows = pad("1").replace("2011-11,1", "2011-11,7.0")
    write_data(tmp_path, DEMAND_HEAD + rows, PROD_HEADER + "\n" + OK_ROW + "\n")
    assert load(tmp_path).history["1"][-1] == 7


def test_load_units_zero_is_valid(tmp_path: Path) -> None:
    rows = pad("1").replace("2011-11,1", "2011-11,0")
    write_data(tmp_path, DEMAND_HEAD + rows, PROD_HEADER + "\n" + OK_ROW + "\n")
    assert load(tmp_path).history["1"][-1] == 0


def test_load_missing_month_in_whole_file(tmp_path: Path) -> None:
    rows = "".join(f"1,A,g,{m},1\n" for m in ALL_MONTHS[:-1])
    write_data(tmp_path, DEMAND_HEAD + rows, PROD_HEADER + "\n" + OK_ROW + "\n")
    with pytest.raises(DataError, match="months must be exactly 2009-12 to 2011-11"):
        load(tmp_path)


def test_load_extra_month_in_file(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD + pad("1") + "1,A,g,2011-12,1\n",
        PROD_HEADER + "\n" + OK_ROW + "\n",
    )
    with pytest.raises(DataError, match="months must be exactly 2009-12 to 2011-11"):
        load(tmp_path)


def test_load_header_only_demand_file(tmp_path: Path) -> None:
    write_data(tmp_path, DEMAND_HEAD, PROD_HEADER + "\n" + OK_ROW + "\n")
    with pytest.raises(DataError):
        load(tmp_path)


def test_load_missing_units_column_is_unreadable(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        "stock_code,description,group,month\n1,A,g,2011-11\n",
        PROD_HEADER + "\n" + OK_ROW + "\n",
    )
    with pytest.raises(DataError, match="demand_monthly.csv: missing column units"):
        load(tmp_path)


def test_load_empty_demand_file_is_data_error(tmp_path: Path) -> None:
    write_data(tmp_path, "", PROD_HEADER + "\n" + OK_ROW + "\n")
    with pytest.raises(DataError):
        load(tmp_path)


def test_load_empty_products_file_is_data_error(tmp_path: Path) -> None:
    write_data(tmp_path, DEMAND_HEAD + pad("1"), PROD_HEADER + "\n")
    with pytest.raises(DataError, match="products_synthetic.csv: no products"):
        load(tmp_path)


def test_load_unicode_description(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD + pad("1"),
        PROD_HEADER + '\n1,"CAFÉ ☕ MUG, BLUE",g,1.0,1,1,1,1,0,0\n',
    )
    assert load(tmp_path).products[0].description == "CAFÉ ☕ MUG, BLUE"


# ---------- exports on real data ----------


@pytest.fixture(scope="module")
def real() -> PlannerData:
    return load(DATA)


@pytest.mark.parametrize("preset", list(PRESETS))
def test_exports_shape_for_every_preset(real: PlannerData, preset: str) -> None:
    sc = PRESETS[preset]
    res = run(real, sc)
    out = tables(real, res)
    assert list(out) == [
        "products.csv",
        "monthly_projection.csv",
        "scenario.csv",
        "reorder_plan.csv",
    ]
    prod = out["products.csv"]
    assert list(prod.columns) == [*PRODUCT_COLS, "stock_data"]
    assert len(prod) == 36
    assert set(prod["stock_data"]) == {"synthetic"}
    proj = out["monthly_projection.csv"]
    assert list(proj.columns) == [
        "stock_code",
        "projection",
        *MonthRow.model_fields,
    ]
    assert len(proj) == 36 * 2 * sc.horizon_months
    assert set(proj["projection"]) == {"do_nothing", "with_plan"}
    assert (
        proj.groupby(["stock_code", "projection"]).size() == sc.horizon_months
    ).all()
    for col in ("demand", "opening", "inbound", "shipped", "unmet", "closing"):
        assert (proj[col] >= 0).all()
    scen = out["scenario.csv"]
    assert list(scen.columns) == ["key", "value"]
    assert scen["key"].tolist() == [
        "as_of",
        *Scenario.model_fields,
        *Kpis.model_fields,
    ]
    assert len(scen) == 1 + 6 + len(Kpis.model_fields)
    assert scen.set_index("key").loc["as_of", "value"] == "2011-12-01"
    plan = out["reorder_plan.csv"]
    assert list(plan.columns) == list(ReorderLine.model_fields)
    assert len(plan) == len(res.plan)
    assert plan["rank"].tolist() == list(range(1, len(plan) + 1))
    assert plan.loc[plan["funded"], "cost_gbp"].sum() == pytest.approx(
        res.kpis.funded_spend_gbp
    )
    assert plan["cost_gbp"].sum() == pytest.approx(res.kpis.suggested_spend_gbp)


def test_exports_csv_roundtrip_has_no_nan_or_inf_in_projection(
    real: PlannerData,
) -> None:
    out = tables(real, run(real, BASELINE))
    for name in ("monthly_projection.csv", "reorder_plan.csv", "products.csv"):
        text = out[name].to_csv(index=False)
        assert "nan" not in text.lower().split(",")
        assert "inf" not in text.lower()
    assert len(
        pd.read_csv(StringIO(out["reorder_plan.csv"].to_csv(index=False)))
    ) == len(out["reorder_plan.csv"])


def test_exports_with_empty_plan_keep_columns() -> None:
    p = Product(
        stock_code="X",
        description="X",
        group="g",
        unit_cost=1.0,
        stock_on_hand=100000,
        lead_time_weeks=4,
        moq=1,
        capacity=200000,
        inbound_qty=0,
        inbound_weeks=0,
    )
    data = PlannerData(
        products=[p],
        history={"X": [10] * 24},
        history_months=[f"m{i}" for i in range(24)],
        prices={"X": 5.0},
    )
    res = run(data, BASELINE)
    out = tables(data, res)
    assert len(out["reorder_plan.csv"]) == 0
    assert list(out["reorder_plan.csv"].columns) == list(ReorderLine.model_fields)
    assert len(out["monthly_projection.csv"]) == 24
    assert out["scenario.csv"].shape == (1 + 6 + len(Kpis.model_fields), 2)


def test_exports_do_not_mutate_inputs(real: PlannerData) -> None:
    res = run(real, BASELINE)
    before = res.model_dump()
    tables(real, res)
    assert res.model_dump() == before


# ---------- presets / real data properties ----------


def test_preset_budget_is_multiple_of_1000_and_names() -> None:
    assert list(PRESETS) == [
        "Baseline",
        "Peak season +25%",
        "Supplier delay +3 weeks",
        "Tight budget",
        "Efficiency",
    ]
    assert BASELINE.budget_gbp % 1000 == 0
    base = PRESETS["Baseline"]
    for name, s in PRESETS.items():
        diff = {k for k, v in s.model_dump().items() if v != base.model_dump()[k]}
        expected = {
            "Baseline": set(),
            "Peak season +25%": {"growth_pct"},
            "Supplier delay +3 weeks": {"delay_weeks"},
            "Tight budget": {"budget_gbp"},
            "Efficiency": {"safety_months"},
        }[name]
        assert diff == expected, name


@pytest.mark.parametrize("preset", list(PRESETS))
def test_real_data_no_early_runout_except_story_product(
    real: PlannerData, preset: str
) -> None:
    res = run(real, PRESETS[preset])
    if preset in ("Supplier delay +3 weeks", "Peak season +25%"):
        return
    for p in res.products:
        if p.stock_code in ("84347",):
            continue
        assert p.runout_month is None or p.runout_month >= "2012-01", p.stock_code


@pytest.mark.parametrize("preset", list(PRESETS))
def test_real_data_order_constraints(real: PlannerData, preset: str) -> None:
    res = run(real, PRESETS[preset])
    prods = {p.stock_code: p for p in real.products}
    for line in res.plan:
        p = prods[line.stock_code]
        assert line.qty >= p.moq
        assert line.qty <= p.capacity
        assert line.cost_gbp == pytest.approx(line.qty * p.unit_cost, abs=0.005)
    for r in res.products:
        assert not math.isnan(r.cover_months)
        if r.cover_months > 6.0:
            assert any(f.startswith("Overstocked") for f in r.flags)
        else:
            assert not any(f.startswith("Overstocked") for f in r.flags)


@pytest.mark.parametrize("method", ["seasonal_naive", "trailing_3m"])
@pytest.mark.parametrize("horizon", [6, 12])
def test_real_data_scenario_extremes(
    real: PlannerData, method: str, horizon: int
) -> None:
    for growth, delay, safety, budget in [(-50, 0, 0, 0), (100, 26, 6, 1_000_000)]:
        sc = Scenario(
            horizon_months=horizon,
            growth_pct=growth,
            delay_weeks=delay,
            budget_gbp=budget,
            safety_months=safety,
            method="trailing_3m" if method == "trailing_3m" else "seasonal_naive",
        )
        res = run(real, sc)
        assert res.kpis.funded_spend_gbp <= budget
        assert all(len(p.months) == horizon for p in res.products)


# ---------- synthetic ----------


def synth_inputs() -> tuple[
    dict[str, list[int]], dict[str, float], dict[str, tuple[str, str]]
]:
    d = load(DATA)
    csv = pd.read_csv(DATA / "demand_monthly.csv", dtype={"stock_code": str})
    names = {
        str(c): (g["description"].iloc[0], g["group"].iloc[0])
        for c, g in csv.groupby("stock_code")
    }
    prices = pd.read_csv(DATA / "median_prices.csv", dtype={"stock_code": str})
    return (
        d.history,
        dict(zip(prices["stock_code"], prices["median_price"], strict=True)),
        names,
    )


def test_synthetic_deterministic_and_seed_sensitive() -> None:
    h, pr, nm = synth_inputs()
    a = generate(h, pr, nm, seed=42)
    assert a == generate(h, pr, nm, seed=42)
    b = generate(h, pr, nm, seed=43)
    assert a != b
    assert [p.stock_code for p in a] == sorted(h)
    assert any(
        x.lead_time_weeks != y.lead_time_weeks for x, y in zip(a, b, strict=True)
    )


def test_synthetic_is_independent_of_dict_order() -> None:
    h, pr, nm = synth_inputs()
    rev = dict(reversed(list(h.items())))
    assert generate(h, pr, nm, seed=42) == generate(rev, pr, nm, seed=42)


def test_synthetic_matches_committed_csv() -> None:
    h, pr, nm = synth_inputs()
    got = pd.DataFrame([p.model_dump() for p in generate(h, pr, nm, seed=42)])
    want = pd.read_csv(DATA / "products_synthetic.csv", dtype={"stock_code": str})
    pd.testing.assert_frame_equal(got, want, check_dtype=False)


@pytest.mark.parametrize("seed", range(0, 200, 25))
def test_synthetic_fields_in_range_for_any_seed(seed: int) -> None:
    h, pr, nm = synth_inputs()
    for p in generate(h, pr, nm, seed=seed):
        assert p.unit_cost > 0
        assert p.lead_time_weeks in (4, 6, 8, 10, 12)
        assert p.moq % 50 == 0
        assert p.capacity % 100 == 0
        assert p.capacity >= p.stock_on_hand + p.inbound_qty
        assert p.stock_on_hand >= 0
        assert (p.inbound_qty == 0) == (p.inbound_weeks == 0)


def test_synthetic_tiny_price_and_zero_history() -> None:
    out = generate(
        {"A": [0] * 24, "B": [1] * 24},
        {"A": 0.001, "B": 0.0},
        {"A": ("a", "g"), "B": ("b", "g")},
        seed=1,
    )
    assert [p.unit_cost for p in out] == [0.01, 0.01]
    assert all(p.moq >= 50 and p.capacity >= 100 for p in out)


def test_synthetic_empty_history() -> None:
    assert generate({}, {}, {}, seed=1) == []


def test_synthetic_missing_price_or_name_raises() -> None:
    h = {"A": [5] * 24}
    with pytest.raises(KeyError):
        generate(h, {}, {"A": ("a", "g")}, seed=1)
    with pytest.raises(KeyError):
        generate(h, {"A": 1.0}, {}, seed=1)


def test_round_up() -> None:
    assert round_up(0, 50) == 50
    assert round_up(0.1, 50) == 50
    assert round_up(50, 50) == 50
    assert round_up(50.01, 50) == 100
    assert round_up(1234, 100) == 1300


# ---------- build_data.group_of (DEC-04) ----------


def group_of(description: str) -> str:
    spec = importlib.util.spec_from_file_location(
        "qa_build_data", REPO / "scripts" / "build_data.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result: str = mod.group_of(description)
    return result


@pytest.mark.parametrize(
    ("desc", "grp"),
    [
        ("JUMBO BAG RED RETROSPOT", "Bags & storage"),
        ("RECYCLING SHOPPER", "Bags & storage"),
        ("WHITE HANGING HEART T-LIGHT HOLDER", "Candles & lights"),
        ("FAIRY LIGHT STRING", "Candles & lights"),
        ("PAPER BAG LIGHT", "Bags & storage"),  # first match wins
        ("PACK OF 72 CAKE CASES", "Baking & party"),
        ("PAPER CHAIN KIT 50'S", "Baking & party"),
        ("RED PLACE SETTING", "Baking & party"),
        ("BUNTING LIGHT", "Candles & lights"),
        ("POPCORN HOLDER", "Baking & party"),
        ("ASSORTED COLOURS SILK FAN", "Gifts & small goods"),
        ("", "Gifts & small goods"),
    ],
)
def test_group_rule_first_match_wins(desc: str, grp: str) -> None:
    assert group_of(desc) == grp


def test_number_non_finite_is_infinity_sign() -> None:
    assert number(float("inf")) == "∞"
    assert number(float("-inf")) == "∞"


@pytest.mark.parametrize(
    ("demand", "message"),
    [
        (DEMAND_HEAD + pad("1") + "1,A,g,,1\n", "blank stock_code or month"),
        (DEMAND_HEAD + pad("1") + ",A,g,2011-11,1\n", "blank stock_code or month"),
        (
            "stock_code,description,group,mnth,units\n1,A,g,2011-11,1\n",
            "missing column month",
        ),
        (
            DEMAND_HEAD + pad("1").replace(",1\n", ",10000000000000000000\n", 1),
            "units must be whole numbers from 0 to 10000000",
        ),
    ],
)
def test_load_round2_demand_holes_are_data_errors(
    tmp_path: Path, demand: str, message: str
) -> None:
    write_data(tmp_path, demand, PROD_HEADER + "\n" + OK_ROW + "\n")
    with pytest.raises(DataError, match=message):
        load(tmp_path)


def test_load_products_without_stock_code_column(tmp_path: Path) -> None:
    write_data(
        tmp_path,
        DEMAND_HEAD + pad("1"),
        PROD_HEADER.replace("stock_code", "code") + "\n" + OK_ROW + "\n",
    )
    with pytest.raises(
        DataError, match="products_synthetic.csv: missing column stock_code"
    ):
        load(tmp_path)


def test_load_unreadable_file_is_named(tmp_path: Path) -> None:
    write_data(tmp_path, DEMAND_HEAD + pad("1"), "")
    with pytest.raises(DataError, match="products_synthetic.csv: unreadable"):
        load(tmp_path)
