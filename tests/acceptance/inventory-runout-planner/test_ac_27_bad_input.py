from runout_toy import app


def test_ac_27_bad_input() -> None:
    """AC-27: Budget -100 shows the exact DEC-10 error, no KPI metric, no exception."""
    at = app().run()
    at.number_input(key="budget_gbp").set_value(-100).run()
    assert not at.exception
    assert "Budget (£) must be between 0 and 1 000 000 — you entered -100." in [
        e.value for e in at.error
    ]
    assert len(at.metric) == 0
