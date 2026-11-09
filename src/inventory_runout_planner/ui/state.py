import os
from pathlib import Path

import streamlit as st
from inventory_runout_planner.data import load
from inventory_runout_planner.models import PlannerData, Scenario, ScenarioResult
from inventory_runout_planner.planner import run

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def data_dir() -> str:
    return os.environ.get("RUNOUT_DATA_DIR", str(DEFAULT_DATA_DIR))


@st.cache_data(show_spinner=False)
def load_data(directory: str) -> PlannerData:
    return load(Path(directory))


@st.cache_data(show_spinner=False)
def run_scenario(
    scenario: Scenario, directory: str = str(DEFAULT_DATA_DIR)
) -> ScenarioResult:
    return run(load_data(directory), scenario)


def product_label(description: str, code: str) -> str:
    """DEC-18: plain description first, code second."""
    return f"{description} ({code})"
