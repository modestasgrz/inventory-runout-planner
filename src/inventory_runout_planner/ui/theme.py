"""All design tokens (DEC-17). `.streamlit/config.toml` repeats the five base colors because Streamlit reads them there."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Graphite (DEC-17, Change 5): neutral near-black, hairline transparent cards, neutral UI controls.
BG = "#0A0A0B"
SURFACE = "#111113"
SURFACE_2 = "#1C1C1F"
BORDER = "#26262A"
TEXT = "#EDEDEF"
MUTED = "#8A8A93"
BLUE = "#3B82F6"
GREEN = "#22C55E"
AMBER = "#F59E0B"
RED = "#EF4444"
SLATE = "#9A9AA3"
FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
RADIUS = "6px"
CARD_FILL = "transparent"
TEMPLATE = "runout_dark"

# Colour language (DEC-17, Change 4): red = out of stock / lead time, amber = budget / unfunded, blue = funded / plan,
# grey = neutral (stock, capacity, none).
FACTOR_COLORS = {
    "lead time": RED,
    "budget": AMBER,
    "capacity": SLATE,
    "stock": SLATE,
    "none": MUTED,
}

CSS_FILE = Path(__file__).resolve().parents[3] / "assets" / "style.css"

pio.templates[TEMPLATE] = go.layout.Template(
    layout={
        "paper_bgcolor": BG,
        "plot_bgcolor": BG,
        "font": {"family": FONT, "color": TEXT, "size": 13},
        "colorway": [BLUE, GREEN, AMBER, RED, MUTED],
        "xaxis": {"gridcolor": BORDER, "linecolor": BORDER, "zerolinecolor": BORDER},
        "yaxis": {"gridcolor": BORDER, "linecolor": BORDER, "zerolinecolor": BORDER},
        "legend": {"bgcolor": "rgba(0,0,0,0)", "orientation": "h", "y": -0.2},
        "margin": {"l": 48, "r": 24, "t": 48, "b": 48},
        "hoverlabel": {"bgcolor": SURFACE_2, "font": {"family": FONT, "color": TEXT}},
    }
)


def apply() -> None:
    """Inject the CSS variables from these tokens plus assets/style.css."""
    variables = (
        f":root {{--bg: {BG}; --surface: {SURFACE}; --surface-2: {SURFACE_2}; --border: {BORDER}; "
        f"--text: {TEXT}; --muted: {MUTED}; --blue: {BLUE}; --green: {GREEN}; --amber: {AMBER}; --red: {RED}; --slate: {SLATE}; "
        f"--font: {FONT}; --radius: {RADIUS}; --card-fill: {CARD_FILL};}}"
    )
    st.html(f"<style>{variables}\n{CSS_FILE.read_text()}</style>")


def styled(frame: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Limiting factor as coloured text; unfunded rows amber-tinted with an amber Status, the same on every table."""
    styler = frame.style
    if "Limiting factor" in frame.columns:
        styler = styler.map(
            lambda v: f"color: {FACTOR_COLORS.get(v, TEXT)}; font-weight: 600",
            subset=["Limiting factor"],
        )
    if "Funded" in frame.columns and frame["Funded"].dtype == object:
        styler = styler.map(
            lambda v: (
                f"color: {AMBER}; font-weight: 600"
                if v == "Not funded"
                else f"color: {BLUE}"
            ),
            subset=["Funded"],
        )
    if "Status" in frame.columns:
        styler = styler.map(
            lambda v: (
                f"color: {AMBER}; font-weight: 600"
                if v == "Not funded"
                else f"color: {BLUE}"
            ),
            subset=["Status"],
        ).apply(
            lambda row: (
                [
                    "background-color: rgba(245, 158, 11, 0.12)"
                    if row["Status"] == "Not funded"
                    else ""
                ]
                * len(row)
            ),
            axis=1,
        )
    return styler
