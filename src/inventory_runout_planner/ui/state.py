from pathlib import Path

import streamlit as st
from inventory_runout_planner.data import load
from inventory_runout_planner.models import PlannerData, Scenario, ScenarioResult
from inventory_runout_planner.planner import run
from loguru import logger

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@st.cache_data(show_spinner=False, max_entries=8)
def load_data(directory: str) -> PlannerData:
    return load(Path(directory))


@st.cache_data(show_spinner=False, max_entries=64)
def run_scenario(scenario: Scenario, directory: str) -> ScenarioResult:
    logger.info(
        "Scenario run: horizon {} months, budget £{:,.0f}",
        scenario.horizon_months,
        scenario.budget_gbp,
    )
    return run(load_data(directory), scenario)


def product_label(description: str, code: str) -> str:
    """DEC-18: plain description first, code second."""
    return f"{description} ({code})"
