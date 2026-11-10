import html
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from inventory_runout_planner.data import load
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import PRESETS
from inventory_runout_planner.ui import theme
from inventory_runout_planner.ui.state import product_label
from streamlit.testing.v1 import AppTest

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "data"
PAGES = [
    "app_pages/overview.py",
    "app_pages/forecast.py",
    "app_pages/scenarios.py",
    "app_pages/reorder_plan.py",
    "app_pages/methodology.py",
]
KPI_LABELS = ["At risk", "Earliest run-out", "Spend", "Unfunded", "Lost sales"]
BUDGET = "Purchase budget (£, whole horizon)"


def spend_budget(at: AppTest) -> str:
    """The Spend card's sub-line ('of £budget')."""
    return str(next(m for m in at.metric if m.label == "Spend").proto.delta)


NBSP = " "
INVALID = [
    (
        "growth_pct",
        150,
        "Demand growth (%) must be between -50 and 100 — you entered 150.",
    ),
    (
        "growth_pct",
        -60,
        "Demand growth (%) must be between -50 and 100 — you entered -60.",
    ),
    (
        "delay_weeks",
        30,
        "Supplier delay (weeks) must be between 0 and 26 — you entered 30.",
    ),
    (
        "delay_weeks",
        -1,
        "Supplier delay (weeks) must be between 0 and 26 — you entered -1.",
    ),
    (
        "budget_gbp",
        -1,
        f"{BUDGET} must be between 0 and 1 000 000 — you entered -1.",
    ),
    (
        "budget_gbp",
        2_000_000,
        f"{BUDGET} must be between 0 and 1 000 000 — you entered 2 000 000.",
    ),
    (
        "safety_months",
        7,
        "Safety stock (months) must be between 0 and 6 — you entered 7.",
    ),
    (
        "safety_months",
        -0.5,
        "Safety stock (months) must be between 0 and 6 — you entered -0.5.",
    ),
]


def app() -> AppTest:
    return AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()


def kpis(at: AppTest) -> dict[str, tuple[str, str]]:
    """Every DEC-14 card: label -> (value, sub-line)."""
    return {m.label: (str(m.value), str(m.proto.delta)) for m in at.metric}


def errors(at: AppTest) -> list[str]:
    return [html.unescape(str(e.value)) for e in at.error]


def md(at: AppTest) -> str:
    return html.unescape("\n".join(str(m.value) for m in at.markdown))


def expected_kpis(name: str) -> dict[str, tuple[str, str]]:
    r = run(load(DATA), PRESETS[name])
    k = r.kpis
    return {
        "At risk": (
            number(k.products_at_risk),
            f"of {number(len(r.products))} products",
        ),
        "Earliest run-out": (
            month(k.earliest_runout_month)
            if k.earliest_runout_month
            else "None in horizon",
            next(
                (
                    p.description.title()
                    for p in r.products
                    if p.stock_code == k.earliest_runout_code
                ),
                "—",
            ),
        ),
        "Spend": (gbp(k.funded_spend_gbp), f"of {gbp(k.budget_gbp)}"),
        "Unfunded": (
            number(k.unfunded_orders),
            f"{gbp(k.unfunded_gbp)} short" if k.unfunded_orders else "none",
        ),
        "Lost sales": (
            gbp(k.lost_sales_after_plan_gbp),
            f"{gbp(k.lost_sales_gbp)} if nothing ordered",
        ),
    }


def set_input(at: AppTest, key: str, value: Any) -> AppTest:
    return at.number_input(key=key).set_value(value).run()


def pick_preset(at: AppTest, name: str) -> AppTest:
    return at.selectbox(key="preset").select(name).run()


@pytest.mark.parametrize("name", list(PRESETS))
def test_preset_kpis_match_planner_and_identical_on_all_pages(name: str) -> None:
    at = pick_preset(app(), name)
    assert not at.exception
    assert at.selectbox(key="preset").value == name
    expected = expected_kpis(name)
    assert [m.label for m in at.metric] == KPI_LABELS
    assert kpis(at) == expected
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        assert [m.label for m in at.metric] == KPI_LABELS, page
        assert kpis(at) == expected, page
        assert at.selectbox(key="preset").value == name
        assert all(m.help for m in at.metric)


@pytest.mark.parametrize("name", list(PRESETS))
def test_preset_populates_inputs(name: str) -> None:
    at = pick_preset(app(), name)
    s = PRESETS[name]
    assert at.slider(key="horizon_months").value == s.horizon_months
    assert at.number_input(key="growth_pct").value == s.growth_pct
    assert at.number_input(key="delay_weeks").value == s.delay_weeks
    assert at.number_input(key="budget_gbp").value == s.budget_gbp
    assert at.number_input(key="safety_months").value == s.safety_months
    assert at.radio(key="method").value == s.method


def test_edit_switches_to_custom_changes_kpis_reset_restores() -> None:
    at = app()
    base = kpis(at)
    at = set_input(at, "growth_pct", 10)
    assert not at.exception
    assert at.selectbox(key="preset").value == "Custom"
    assert kpis(at) != base
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception
    at.button(key="reset").click().run()
    assert at.number_input(key="growth_pct").value == 0
    assert kpis(at) == base


def test_reset_after_other_preset_and_edits() -> None:
    at = pick_preset(app(), "Tight budget")
    at = set_input(at, "safety_months", 3)
    at.button(key="reset").click().run()
    assert at.selectbox(key="preset").value == "Baseline"
    assert kpis(at) == expected_kpis("Baseline")


@pytest.mark.parametrize(("key", "value", "message"), INVALID)
def test_invalid_input_message_on_every_page(
    key: str, value: float, message: str
) -> None:
    message = message.replace("entered 2 000 000", f"entered 2{NBSP}000{NBSP}000")
    at = set_input(app(), key, value)
    assert not at.exception
    assert errors(at) == [message]
    assert len(at.metric) == 0
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        assert errors(at) == [message], page
        assert len(at.metric) == 0, page


def test_multiple_invalid_inputs_list_all_in_order() -> None:
    at = app()
    for key, value in [
        ("safety_months", 9),
        ("budget_gbp", -5),
        ("delay_weeks", 40),
        ("growth_pct", 500),
    ]:
        at = set_input(at, key, value)
    msgs = errors(at)
    assert [m.split(" must")[0] for m in msgs] == [
        "Demand growth (%)",
        "Supplier delay (weeks)",
        BUDGET,
        "Safety stock (months)",
    ]
    assert len(at.metric) == 0


@pytest.mark.parametrize(("key", "value", "_m"), INVALID[:3])
def test_recovery_from_invalid_input(key: str, value: float, _m: str) -> None:
    at = app()
    base = kpis(at)
    at = set_input(at, key, value)
    assert len(at.metric) == 0
    at.button(key="reset").click().run()
    assert not at.exception
    assert errors(at) == []
    assert kpis(at) == base


def test_recovery_by_correcting_value_on_other_page() -> None:
    at = app()
    at.switch_page("app_pages/reorder_plan.py").run()
    at = set_input(at, "budget_gbp", -1)
    assert len(at.metric) == 0
    at = set_input(at, "budget_gbp", 50000)
    assert not at.exception
    assert errors(at) == []
    assert spend_budget(at) == f"of {gbp(50000)}"
    assert len(at.dataframe) >= 1


@pytest.mark.parametrize("name", list(PRESETS)[1:])
def test_invalid_input_then_preset_switch_recovers(name: str) -> None:
    at = set_input(app(), "growth_pct", 150)
    at = pick_preset(at, name)
    assert errors(at) == []
    assert kpis(at) == expected_kpis(name)


BOUNDARIES = [
    {"horizon_months": 6, "delay_weeks": 26},
    {"budget_gbp": 0},
    {"growth_pct": -50},
    {"growth_pct": 100},
    {"safety_months": 6},
    {"safety_months": 0},
    {"delay_weeks": 26, "budget_gbp": 1_000_000},
    {"budget_gbp": 1_000_000, "growth_pct": 100, "safety_months": 6},
    {"horizon_months": 6, "method": "trailing_3m"},
    {"horizon_months": 12, "method": "trailing_3m", "growth_pct": -50, "budget_gbp": 0},
]


@pytest.mark.parametrize("combo", BOUNDARIES, ids=[str(c) for c in BOUNDARIES])
def test_boundary_combos_render_all_pages(combo: dict[str, Any]) -> None:
    at = app()
    for key, value in combo.items():
        if key == "horizon_months":
            at.slider(key=key).set_value(value)
        elif key == "method":
            at.radio(key=key).set_value(value)
        else:
            at.number_input(key=key).set_value(value)
    at.run()
    for page in ["app_pages/overview.py", *PAGES[1:]]:
        at.switch_page(page).run()
        assert not at.exception, (combo, page)
        assert errors(at) == [], (combo, page)
        assert [m.label for m in at.metric] == KPI_LABELS


def test_budget_zero_everything_unfunded() -> None:
    at = set_input(app(), "budget_gbp", 0)
    k = kpis(at)
    assert k["Spend"] == (gbp(0), f"of {gbp(0)}")
    assert spend_budget(at) == f"of {gbp(0)}"
    assert int(k["Unfunded"][0].replace(NBSP, "")) >= 1
    assert k["Unfunded"][1].endswith(" short")
    at.switch_page("app_pages/reorder_plan.py").run()
    assert f"Funded total: {gbp(0)}" in md(at)
    assert set(at.dataframe[0].value["Status"]) == {"Not funded"}


def test_forecast_picker_lists_all_products_and_each_renders() -> None:
    data = load(DATA)
    labels = {product_label(p.description, p.stock_code) for p in data.products}
    assert len(labels) == 36
    at = app()
    at.switch_page("app_pages/forecast.py").run()
    picker = at.selectbox(key="product")
    assert len(picker.options) == 36
    assert set(picker.options) == labels
    for option in list(picker.options):
        at.selectbox(key="product").select(option).run()
        assert not at.exception, option
        assert len(at.dataframe) >= 1
        spec = json.loads(at.get("plotly_chart")[0].proto.spec)
        assert spec["layout"]["title"]["text"].startswith(option)


def test_forecast_table_rows_follow_horizon() -> None:
    at = app()
    at.slider(key="horizon_months").set_value(6).run()
    at.switch_page("app_pages/forecast.py").run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 6
    assert list(at.dataframe[0].value.columns) == [
        "Month",
        "Demand",
        "Opening",
        "Inbound",
        "Shipped",
        "Unmet",
        "Closing",
    ]


def test_forecast_picker_survives_scenario_change() -> None:
    at = app()
    at.switch_page("app_pages/forecast.py").run()
    chosen = at.selectbox(key="product").options[5]
    at.selectbox(key="product").select(chosen).run()
    at = pick_preset(at, "Peak season +25%")
    assert not at.exception


@pytest.mark.parametrize("name", list(PRESETS))
def test_reorder_table_matches_plan(name: str) -> None:
    result = run(load(DATA), PRESETS[name])
    at = pick_preset(app(), name)
    at.switch_page("app_pages/reorder_plan.py").run()
    assert not at.exception
    df = at.dataframe[0].value
    assert len(df) == len(result.plan)
    ordered = sorted(result.plan, key=lambda line: line.rank)
    assert list(df["#"]) == list(range(1, len(result.plan) + 1))
    assert list(df.columns).index("Product") < list(df.columns).index("Code")
    assert list(df["Code"]) == [line.stock_code for line in ordered]
    assert list(df["Order"]) == [line.order_no for line in ordered]
    assert list(df["Product"]) == [line.description.title() for line in ordered]
    assert f"Funded total: {gbp(result.kpis.funded_spend_gbp)}" in md(at)
    assert len(at.get("download_button")) == 4
    assert sorted(b.proto.label for b in at.get("download_button")) == sorted(
        [
            "Download products.csv",
            "Download monthly_projection.csv",
            "Download scenario.csv",
            "Download reorder_plan.csv",
        ]
    )


def test_funded_total_matches_kpi_prefix() -> None:
    at = app()
    at.switch_page("app_pages/reorder_plan.py").run()
    funded = md(at).split("Funded total: ")[1].split("**")[0]
    assert kpis(at)["Spend"][0] == funded


@pytest.mark.parametrize("name", list(PRESETS))
def test_scenarios_table_has_five_presets(name: str) -> None:
    at = pick_preset(app(), name)
    at.switch_page("app_pages/scenarios.py").run()
    assert not at.exception
    frames = [d.value for d in at.dataframe]
    side = next(f for f in frames if "Preset" in f.columns)
    assert list(side["Preset"]) == list(PRESETS)


def test_overview_flags_include_every_core_flag() -> None:
    result = run(load(DATA), PRESETS["Baseline"])
    at = app()
    tables = [d.value for d in at.dataframe if "Flag" in d.value.columns]
    assert all(
        list(t.columns).index("Product") < list(t.columns).index("Code") for t in tables
    )
    shown = {(r.Code, r.Flag) for t in tables for r in t.itertuples()}
    for p in result.products:
        for flag in p.flags:
            assert (p.stock_code, flag) in shown, flag
    labels = [e.label for e in at.expander]
    assert any(label.startswith("Lead time · ") for label in labels)


def test_overview_hero_matches_kpi() -> None:
    at = app()
    r = run(load(DATA), PRESETS["Baseline"])
    k = r.kpis
    first = next(p for p in r.products if p.stock_code == k.earliest_runout_code)
    card = (month(k.earliest_runout_month or ""), first.description.title())
    assert first.stock_code not in card[1]
    assert kpis(at)["Earliest run-out"] == card
    assert f"({k.earliest_runout_code})" in md(at)
    at.switch_page("app_pages/forecast.py").run()
    assert kpis(at)["Earliest run-out"] == card


def test_notice_and_attribution_on_all_pages() -> None:
    at = app()
    for page in PAGES:
        at.switch_page(page).run()
        assert "Synthetic stock data — demonstration only" in md(at)
        assert "Data as of Dec 2011" in md(at)
        main = html.unescape(" ".join(str(m.value) for m in at.main.markdown))
        assert "Planning as of" not in main
        side = " ".join(str(c.value) for c in at.sidebar.caption)
        assert "Planning as of 1 Dec 2011" in side
        assert "CC BY 4.0" in side
        assert "doi.org" not in side


def _copy_data(dest: Path) -> Path:
    shutil.copytree(DATA, dest, ignore=shutil.ignore_patterns("raw"))
    return dest


def run_with_dir(monkeypatch: pytest.MonkeyPatch, path: Path) -> AppTest:
    monkeypatch.setenv("RUNOUT_DATA_DIR", str(path))
    return app()


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("demand_monthly.csv", "garbage\n\x00\x01", None),
        ("demand_monthly.csv", "", None),
        (
            "demand_monthly.csv",
            "stock_code,month\n1,2010-01\n",
            "demand_monthly.csv: missing column",
        ),
        (
            "products_synthetic.csv",
            "stock_code\n",
            "products_synthetic.csv: missing column",
        ),
        ("products_synthetic.csv", "", None),
    ],
)
def test_corrupt_csv_shows_data_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content: str,
    expected: str | None,
) -> None:
    d = _copy_data(tmp_path / "d")
    (d / filename).write_text(content)
    at = run_with_dir(monkeypatch, d)
    assert not at.exception
    assert len(at.metric) == 0
    msgs = errors(at)
    assert len(msgs) == 1
    assert filename in msgs[0]
    assert "Traceback" not in msgs[0]
    if expected:
        assert expected in msgs[0]


def test_missing_products_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _copy_data(tmp_path / "d")
    (d / "products_synthetic.csv").unlink()
    at = run_with_dir(monkeypatch, d)
    assert not at.exception
    assert errors(at) == ["Data file not found: products_synthetic.csv"]


def test_truncated_months_shows_data_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _copy_data(tmp_path / "d")
    lines = (d / "demand_monthly.csv").read_text().splitlines()
    kept = [ln for ln in lines if ",2011-11," not in ln]
    assert len(kept) < len(lines)
    (d / "demand_monthly.csv").write_text("\n".join(kept) + "\n")
    at = run_with_dir(monkeypatch, d)
    assert not at.exception
    assert len(at.metric) == 0
    assert len(errors(at)) == 1


def test_data_error_on_every_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNOUT_DATA_DIR", str(tmp_path))
    at = app()
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        assert errors(at) == ["Data file not found: demand_monthly.csv"], page


def test_nonexistent_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at = run_with_dir(monkeypatch, tmp_path / "nope")
    assert not at.exception
    assert errors(at) == ["Data file not found: demand_monthly.csv"]


def test_theme_template_registered() -> None:
    import plotly.io as pio

    assert theme.TEMPLATE == "runout_dark"
    assert "runout_dark" in pio.templates
    t = pio.templates["runout_dark"]
    assert t.layout.paper_bgcolor == theme.BG
    assert t.layout.plot_bgcolor == theme.BG
    assert t.layout.font.color == theme.TEXT


def test_theme_css_exists_and_hides_steppers() -> None:
    assert theme.CSS_FILE.is_file()
    css = theme.CSS_FILE.read_text()
    for tid in ("stNumberInputStepUp", "stNumberInputStepDown"):
        line = next(ln for ln in css.splitlines() if tid in ln)
        assert "display: none" in line


def test_theme_tokens_match_dec17() -> None:
    assert (theme.BLUE, theme.GREEN, theme.AMBER, theme.RED) == (
        "#3B82F6",
        "#22C55E",
        "#F59E0B",
        "#EF4444",
    )
    assert (theme.BG, theme.SURFACE, theme.TEXT) == ("#0A0A0B", "#111113", "#EDEDEF")
    assert set(theme.FACTOR_COLORS) == {
        "lead time",
        "budget",
        "capacity",
        "stock",
        "none",
    }


@pytest.mark.parametrize(
    ("desc", "code", "expected"),
    [
        (
            "WHITE HANGING HEART T-LIGHT HOLDER",
            "85123A",
            "WHITE HANGING HEART T-LIGHT HOLDER (85123A)",
        ),
        ("", "1", " (1)"),
        ("Crème brûlée 🍮 (set)", "X9", "Crème brûlée 🍮 (set) (X9)"),
        ("  padded  ", "00001", "  padded   (00001)"),
    ],
)
def test_product_label(desc: str, code: str, expected: str) -> None:
    assert product_label(desc, code) == expected
