"""All design tokens (DEC-17). `.streamlit/config.toml` repeats the five base colors because Streamlit reads them there."""

from pathlib import Path

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
FONT = '"Inter", "Avenir Next", "Helvetica Neue", Arial, sans-serif'
TEMPLATE = "runout_dark"

FACTOR_COLORS = {
    "lead time": RED,
    "budget": AMBER,
    "capacity": AMBER,
    "stock": BLUE,
    "none": GREEN,
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
        f"--text: {TEXT}; --muted: {MUTED}; --blue: {BLUE}; --green: {GREEN}; --amber: {AMBER}; --red: {RED}; "
        f"--font: {FONT};}}"
    )
    st.html(f"<style>{variables}\n{CSS_FILE.read_text()}</style>")
