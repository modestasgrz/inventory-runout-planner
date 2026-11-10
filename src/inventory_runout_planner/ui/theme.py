"""All design tokens (DEC-17). `.streamlit/config.toml` repeats the five base colors because Streamlit reads them there."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

BG = "#0B1730"
SURFACE = "#13223F"
SURFACE_2 = "#1A2D52"
BORDER = "#26406E"
TEXT = "#E6ECF5"
MUTED = "#9DB0CC"
BLUE = "#3B82F6"
GREEN = "#22C55E"
AMBER = "#F59E0B"
RED = "#EF4444"
SLATE = "#94A3B8"
FONT = '"Inter", "Avenir Next", "Helvetica Neue", Arial, sans-serif'
TEMPLATE = "runout_dark"

# Colour language (DEC-17, Change 3): blue = funded / OK, slate = stock run-out, amber = budget, red = lead time.
FACTOR_COLORS = {
    "lead time": RED,
    "budget": AMBER,
    "capacity": AMBER,
    "stock": SLATE,
    "none": BLUE,
}

CSS_FILE = Path(__file__).resolve().parents[3] / "assets" / "style.css"

pio.templates[TEMPLATE] = go.layout.Template(
    layout={
        "paper_bgcolor": SURFACE,
        "plot_bgcolor": SURFACE,
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
        f"--font: {FONT};}}"
    )
    st.html(f"<style>{variables}\n{CSS_FILE.read_text()}</style>")


def styled(frame: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Limiting factor as coloured text and unfunded rows amber-tinted, the same on every table."""
    styler = frame.style
    if "Limiting factor" in frame.columns:
        styler = styler.map(
            lambda v: f"color: {FACTOR_COLORS.get(v, TEXT)}; font-weight: 600",
            subset=["Limiting factor"],
        )
    if "Funded" in frame.columns:
        styler = styler.apply(
            lambda row: (
                [
                    "background-color: rgba(245, 158, 11, 0.12)"
                    if not row["Funded"]
                    else ""
                ]
                * len(row)
            ),
            axis=1,
        )
    return styler
