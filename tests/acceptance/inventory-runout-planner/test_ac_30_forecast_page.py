from runout_toy import app, real_data

COLUMNS = ["Month", "Demand", "Opening", "Inbound", "Shipped", "Unmet", "Closing"]


def test_ac_30_forecast_page() -> None:
    """AC-30: picking '<description> (85123A)' shows a Plotly chart and the 12-row do-nothing table for 85123A."""
    description = next(
        p.description for p in real_data().products if p.stock_code == "85123A"
    )
    at = app().run()
    at.switch_page("app_pages/forecast.py").run()
    at.selectbox(key="product").select(f"{description} (85123A)").run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 1
    table = next(d.value for d in at.dataframe if list(d.value.columns) == COLUMNS)
    assert len(table) == 12
