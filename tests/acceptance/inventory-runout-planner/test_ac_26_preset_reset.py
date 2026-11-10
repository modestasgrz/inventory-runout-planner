from runout_toy import app, kpis

INPUTS = ["growth_pct", "delay_weeks", "budget_gbp", "safety_months"]


def test_ac_26_preset_reset() -> None:
    """AC-26: Peak season +25% sets growth 25 and moves a KPI; Reset to Baseline restores every input and KPI."""
    at = app().run()
    base_kpis = kpis(at)
    base_inputs = {k: at.number_input(key=k).value for k in INPUTS}
    base_horizon = at.slider(key="horizon_months").value
    base_method = at.radio(key="method").value

    at.selectbox(key="preset").select("Peak season +25%").run()
    assert at.number_input(key="growth_pct").value == 25
    peak = kpis(at)
    assert (
        peak["At risk"] != base_kpis["At risk"] or peak["Spend"] != base_kpis["Spend"]
    )

    at.button(key="reset").click().run()
    assert not at.exception
    assert at.button(key="reset").label == "Reset to Baseline"
    assert {k: at.number_input(key=k).value for k in INPUTS} == base_inputs
    assert at.slider(key="horizon_months").value == base_horizon
    assert at.radio(key="method").value == base_method
    assert kpis(at) == base_kpis
