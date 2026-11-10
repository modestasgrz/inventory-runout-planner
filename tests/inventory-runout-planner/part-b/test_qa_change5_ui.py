"""QA for Change 5 UI (DEC-14, DEC-17, DEC-23, AC-34, AC-52): reading strip, plain-words help, product name
under Earliest run-out, Funded as text, `products` y-axis and Graphite tokens, across presets and edge scenarios."""

import html
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import streamlit as st
from inventory_runout_planner.data import HISTORY_MONTHS, load
from inventory_runout_planner.fmt import gbp, month, number
from inventory_runout_planner.models import PlannerData, Scenario, ScenarioResult
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE, PRESETS
from inventory_runout_planner.ui import theme
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
EDGES: dict[str, dict[str, Any]] = {
    "budget 0": {"budget_gbp": 0},
    "horizon 6": {"horizon_months": 6},
    "growth -50": {"growth_pct": -50},
    "growth 100": {"growth_pct": 100},
    "delay 26": {"delay_weeks": 26},
    "trailing_3m": {"method": "trailing_3m"},
}
CASES: dict[str, Scenario] = {
    **PRESETS,
    **{name: BASELINE.model_copy(update=combo) for name, combo in EDGES.items()},
}
LABELS = ["The question", "Right now", "Do this"]
KPI_LABELS = ["At risk", "Earliest run-out", "Spend", "Unfunded", "Lost sales"]
FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
TOY_DEFAULTS: dict[str, Any] = {
    "group": "Gifts & small goods",
    "unit_cost": 2.0,
    "stock_on_hand": 100,
    "lead_time_weeks": 4,
    "moq": 50,
    "capacity": 400,
    "inbound_qty": 0,
    "inbound_weeks": 0,
}
NO_RUNOUT = {"stock_on_hand": 5000, "capacity": 20000}


@pytest.fixture(scope="module")
def real() -> PlannerData:
    return load(DATA)


def set_inputs(at: AppTest, inputs: dict[str, Any]) -> AppTest:
    for key, value in inputs.items():
        if key == "horizon_months":
            at.slider(key=key).set_value(value)
        elif key == "method":
            at.radio(key=key).set_value(value)
        else:
            at.number_input(key=key).set_value(value)
    return at.run()


def start(case: str) -> AppTest:
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    at = (
        at.selectbox(key="preset").select(case).run()
        if case in PRESETS
        else set_inputs(at, EDGES[case])
    )
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def write_toy(directory: Path, products: dict[str, dict[str, Any]]) -> None:
    """Flat demand 60 every month, sell price £5.00; `description` defaults to TOY ITEM <code>."""
    rows = {
        code: {"stock_code": code, "description": f"TOY ITEM {code}"} | TOY_DEFAULTS | o
        for code, o in products.items()
    }
    pd.DataFrame(
        [
            {
                "stock_code": code,
                "description": row["description"],
                "group": row["group"],
                "month": m,
                "units": 60,
            }
            for code, row in rows.items()
            for m in HISTORY_MONTHS
        ]
    ).to_csv(directory / "demand_monthly.csv", index=False)
    pd.DataFrame(list(rows.values())).to_csv(
        directory / "products_synthetic.csv", index=False
    )
    pd.DataFrame(
        [{"stock_code": code, "median_price": 5.0} for code in products]
    ).to_csv(directory / "median_prices.csv", index=False)


def toy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    products: dict[str, dict[str, Any]],
) -> tuple[AppTest, ScenarioResult]:
    write_toy(tmp_path, products)
    monkeypatch.setenv("RUNOUT_DATA_DIR", str(tmp_path))
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    return at, run(load(tmp_path), BASELINE)


def strip_raw(at: AppTest) -> str:
    found = [str(m.value) for m in at.main.markdown if "how-to-read" in str(m.value)]
    assert len(found) == 1, found
    return found[0]


def strip_lines(at: AppTest) -> list[tuple[str, str]]:
    """The strip as (label, visible text), tags removed and entities decoded."""
    pairs = re.findall(r"<div><b>(.*?)</b><span>(.*?)</span></div>", strip_raw(at))
    return [
        (html.unescape(label), html.unescape(re.sub(r"<[^>]+>", "", text)))
        for label, text in pairs
    ]


def in_order(text: str, fragments: list[str]) -> None:
    at = 0
    for fragment in fragments:
        found = text.find(fragment, at)
        assert found >= 0, (fragment, text[at:])
        at = found + len(fragment)


def earliest_title(r: ScenarioResult) -> str | None:
    return next(
        (
            p.description.title()
            for p in r.products
            if p.stock_code == r.kpis.earliest_runout_code
        ),
        None,
    )


def check_strip(at: AppTest, r: ScenarioResult) -> None:
    k = r.kpis
    lines = strip_lines(at)
    assert [label for label, _ in lines] == LABELS
    question, now, do = (text for _, text in lines)
    in_order(
        question,
        [f"next {r.scenario.horizon_months} months", f"{gbp(k.budget_gbp)} budget"],
    )
    first = earliest_title(r)
    named = first is not None and bool(k.earliest_runout_month)
    short, count, unfunded = k.products_at_risk, len(r.products), k.unfunded_orders
    runs_out = month(k.earliest_runout_month) if k.earliest_runout_month else ""
    if short:
        head = [
            f"{number(short)} of {number(count)} products {'runs' if short == 1 else 'run'} short"
        ]
        head += [f"The first, {first}", f"runs out {runs_out}"] if named else []
    else:
        head = [f"0 of {number(count)} products run short with the plan"]
        head += (
            [f"without it, {first} would run out first, in {runs_out}"] if named else []
        )
    tail = [f"uses {gbp(k.funded_spend_gbp)}"]
    tail.append(
        f"{number(unfunded)} {'order doesn' if unfunded == 1 else 'orders don'}'t fit ({gbp(k.unfunded_gbp)})"
        if unfunded
        else "every order fits"
    )
    tail.append(
        f"so {gbp(k.lost_sales_after_plan_gbp)} of sales are still lost"
        if k.lost_sales_after_plan_gbp
        else "and no sales are lost"
    )
    in_order(now, head + tail)
    if not named:
        assert "first" not in now.lower() and "run out" not in now, now
    if short and named:
        in_order(do, ["red-outlined", "Order now", "Reorder plan"])
    elif named:
        in_order(do, ["Check the red-outlined product", "Reorder plan"])
    else:
        in_order(do, ["Nothing is urgent", "Reorder plan"])


def helps(at: AppTest) -> dict[str, str]:
    return {m.label: str(m.proto.help) for m in at.metric}


def overview_charts(at: AppTest) -> list[dict[str, Any]]:
    charts: Any = at.main.get("plotly_chart")
    return [json.loads(c.proto.spec) for c in charts]


@pytest.mark.parametrize("case", list(CASES))
def test_strip_live_values_every_case(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    check_strip(at, r)
    kinds = [type(n).__name__ for n in at.main]
    values = [str(getattr(n, "value", "")) for n in at.main]
    head = next(i for i, v in enumerate(values) if 'class="page-head"' in v)
    strip = next(i for i, v in enumerate(values) if 'class="how-to-read"' in v)
    first_metric = kinds.index("Metric")
    assert head < strip < first_metric, "strip sits between header and KPI cards"


@pytest.mark.parametrize("case", list(CASES))
def test_kpi_help_and_earliest_subline_every_case(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    k = r.kpis
    at = start(case)
    shown = helps(at)
    assert list(shown) == KPI_LABELS
    for label, text in shown.items():
        assert text.startswith("In plain words: "), label
        plain, _, formula = text.partition(f"{label} = ")
        assert formula, f"{label}: formula '{label} = …' missing"
        assert "=" not in plain, f"{label}: plain sentence must come before the formula"
        assert len(plain) > len("In plain words: ") + 10, label
    assert gbp(k.suggested_spend_gbp) in shown["Spend"]
    assert gbp(k.lost_sales_gbp) in shown["Lost sales"]
    earliest = next(m for m in at.metric if m.label == "Earliest run-out")
    assert str(earliest.proto.delta) == (earliest_title(r) or "—")
    if r.kpis.earliest_runout_code:
        assert r.kpis.earliest_runout_code not in str(earliest.proto.delta)


@pytest.mark.parametrize("case", list(CASES))
def test_order_now_funded_text_every_case(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    table = next(d.value for d in at.dataframe if "Runs out" in d.value.columns)
    wanted = [
        ("✓ Funded" if p.order.funded else "Not funded") if p.order else ""
        for p in r.products
        if p.order_now
    ]
    assert list(table["Funded"]) == wanted
    assert set(table["Funded"]) <= {"✓ Funded", "Not funded", ""}
    assert all(isinstance(v, str) for v in table["Funded"])
    if CASES[case].budget_gbp == 0:
        assert "✓ Funded" not in set(table["Funded"])


@pytest.mark.parametrize("case", list(CASES))
def test_runouts_chart_y_axis_products_every_case(case: str) -> None:
    at = start(case)
    specs = overview_charts(at)
    stacked = [s for s in specs if s["layout"].get("barmode") == "stack"]
    assert len(stacked) == 1, [s["layout"].get("barmode") for s in specs]
    assert stacked[0]["layout"]["yaxis"]["title"]["text"] == "products"


def test_charts_on_every_page_use_template_on_page_background() -> None:
    at = start("Baseline")
    seen = 0
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        for spec in overview_charts(at):
            layout = spec["layout"]
            base = layout["template"]["layout"]
            assert layout.get("paper_bgcolor", base["paper_bgcolor"]) == theme.BG, page
            assert layout.get("plot_bgcolor", base["plot_bgcolor"]) == theme.BG, page
            seen += 1
    assert seen >= 2


@pytest.mark.parametrize("case", ["Baseline", "growth 100", "budget 0"])
def test_strip_only_on_overview(case: str, real: PlannerData) -> None:
    r = run(real, CASES[case])
    at = start(case)
    for page in PAGES[1:]:
        at.switch_page(page).run()
        assert not at.exception, page
        text = "\n".join(str(m.value) for m in at.main.markdown)
        assert "how-to-read" not in text, page
        for label in LABELS:
            assert label not in text, (page, label)
        assert helps(at) == helps(start(case)), page
    at.switch_page(PAGES[0]).run()
    check_strip(at, r)


def test_strip_stable_on_rerun_and_follows_preset_switch(real: PlannerData) -> None:
    at = start("Baseline")
    before = strip_raw(at)
    assert strip_raw(at.run()) == before
    at.selectbox(key="preset").select("Tight budget").run()
    check_strip(at, run(real, PRESETS["Tight budget"]))
    assert strip_raw(at) != before
    at.button(key="reset").click().run()
    assert strip_raw(at) == before


def test_toy_no_runout_omits_first_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, r = toy(tmp_path, monkeypatch, {"T0001": NO_RUNOUT, "T0002": NO_RUNOUT})
    assert r.kpis.earliest_runout_code is None
    check_strip(at, r)
    now = dict(strip_lines(at))["Right now"]
    assert now.startswith("0 of 2 products run short with the plan")
    assert "Toy Item" not in now
    earliest = next(m for m in at.metric if m.label == "Earliest run-out")
    assert (str(earliest.value), str(earliest.proto.delta)) == ("None in horizon", "—")
    chart = next(
        s for s in overview_charts(at) if s["layout"].get("barmode") == "stack"
    )
    assert chart["layout"]["yaxis"]["title"]["text"] == "products"
    for page in PAGES[1:]:
        at.switch_page(page).run()
        assert not at.exception, page
        assert "how-to-read" not in "".join(str(m.value) for m in at.main.markdown)


def test_toy_runout_names_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at, r = toy(tmp_path, monkeypatch, {"T0001": NO_RUNOUT, "T0002": {}})
    assert r.kpis.earliest_runout_code == "T0002"
    check_strip(at, r)
    in_order(dict(strip_lines(at))["Right now"], ["Toy Item T0002", "Jan 2012"])


@pytest.mark.parametrize(
    "description",
    [
        "MUG <B> & SAUCER",
        'BOX </SPAN><SCRIPT>ALERT("X")</SCRIPT> & CO',
        "CRÈME BRÛLÉE 🍮 SET, \"LARGE\" & 'SMALL'",
        "LONG " + "VERY " * 80 + "NAME",
    ],
)
def test_strip_escapes_product_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, description: str
) -> None:
    at, r = toy(
        tmp_path,
        monkeypatch,
        {"T0001": NO_RUNOUT, "T0002": {"description": description}},
    )
    title = description.title()
    raw = strip_raw(at)
    assert html.escape(title) in raw
    for tag in re.findall(r"<[^>]+>", title):
        assert tag not in raw, tag
    assert raw.count("<span>") == raw.count("</span>") == 3
    now = dict(strip_lines(at))["Right now"]
    assert now.count(title) == 1, now
    assert "&amp;" not in now and "&lt;" not in now
    earliest = next(m for m in at.metric if m.label == "Earliest run-out")
    assert str(earliest.proto.delta) == title
    check_strip(at, r)


def test_funded_styling_blue_and_amber() -> None:
    frame = pd.DataFrame({"Funded": ["✓ Funded", "Not funded", "✓ Funded"]})
    page = theme.styled(frame).to_html()
    colours: dict[str, str] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", page):
        colour = re.search(r"(?<![-\w])color: (#[0-9A-Fa-f]{6})", body)
        for row in re.findall(r"_row(\d+)_col0\b", selectors):
            if colour:
                colours[row] = colour.group(1)
    assert [colours.get(str(i)) for i in range(3)] == [
        theme.BLUE,
        theme.AMBER,
        theme.BLUE,
    ]


def test_config_toml_matches_dec17() -> None:
    config = tomllib.loads((REPO / ".streamlit" / "config.toml").read_text())["theme"]
    assert config == {
        "base": "dark",
        "backgroundColor": "#0A0A0B",
        "secondaryBackgroundColor": "#111113",
        "textColor": "#EDEDEF",
        "primaryColor": "#EDEDEF",
        "font": FONT,
    }
    assert (
        config["backgroundColor"],
        config["secondaryBackgroundColor"],
        config["textColor"],
        config["font"],
    ) == (theme.BG, theme.SURFACE, theme.TEXT, theme.FONT)


def test_theme_tokens_match_dec17() -> None:
    assert {
        "BG": theme.BG,
        "SURFACE": theme.SURFACE,
        "SURFACE_2": theme.SURFACE_2,
        "BORDER": theme.BORDER,
        "TEXT": theme.TEXT,
        "MUTED": theme.MUTED,
        "BLUE": theme.BLUE,
        "GREEN": theme.GREEN,
        "AMBER": theme.AMBER,
        "RED": theme.RED,
        "SLATE": theme.SLATE,
        "FONT": theme.FONT,
        "RADIUS": theme.RADIUS,
        "CARD_FILL": theme.CARD_FILL,
    } == {
        "BG": "#0A0A0B",
        "SURFACE": "#111113",
        "SURFACE_2": "#1C1C1F",
        "BORDER": "#26262A",
        "TEXT": "#EDEDEF",
        "MUTED": "#8A8A93",
        "BLUE": "#3B82F6",
        "GREEN": "#22C55E",
        "AMBER": "#F59E0B",
        "RED": "#EF4444",
        "SLATE": "#9A9AA3",
        "FONT": FONT,
        "RADIUS": "6px",
        "CARD_FILL": "transparent",
    }
    colours = theme.FACTOR_COLORS
    assert colours["lead time"] == theme.RED
    assert colours["budget"] == theme.AMBER
    assert {colours["stock"], colours["none"]} <= {theme.SLATE, theme.MUTED}
    assert colours["capacity"] not in {theme.RED, theme.AMBER, theme.BLUE}


def test_apply_injects_graphite_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    injected: list[str] = []
    monkeypatch.setattr(st, "html", injected.append)
    theme.apply()
    assert len(injected) == 1
    for name, value in [
        ("bg", "#0A0A0B"),
        ("surface", "#111113"),
        ("surface-2", "#1C1C1F"),
        ("border", "#26262A"),
        ("text", "#EDEDEF"),
        ("muted", "#8A8A93"),
        ("radius", "6px"),
        ("card-fill", "transparent"),
    ]:
        assert f"--{name}: {value};" in injected[0], name


def test_tokens_only_in_theme_py_and_chip_muted_pill() -> None:
    hexes = re.compile(r"#[0-9A-Fa-f]{6}\b")
    for path in [
        REPO / "app.py",
        *sorted((REPO / "app_pages").glob("*.py")),
        theme.CSS_FILE,
    ]:
        assert not hexes.findall(path.read_text()), path
    css = theme.CSS_FILE.read_text()
    chip = re.search(r"\n\.chip \{([^}]*)\}", css)
    assert chip is not None
    rules = {
        k.strip(): v.strip()
        for k, _, v in (r.partition(":") for r in chip.group(1).split(";"))
        if k.strip()
    }
    assert rules["color"] == "var(--muted)"
    assert rules["border"] == "1px solid var(--border)"
    assert rules["background"] == "none"
    assert rules["border-radius"] == "999px"
