from runout_toy import of, product, row, toy_run


def test_ac_07_projection() -> None:
    """AC-07: T0001 do-nothing projection, run-out Jan 2012, lead 1 month, value at risk 520.00, cover 1.67."""
    p = of(toy_run(product("T0001")), "T0001")
    assert [row(r) for r in p.months] == [
        ("2011-12", 100, 0, 60, 60, 0, 40),
        ("2012-01", 40, 0, 60, 40, 20, 0),
        ("2012-02", 0, 0, 60, 0, 60, 0),
        ("2012-03", 0, 0, 60, 0, 60, 0),
        ("2012-04", 0, 0, 60, 0, 60, 0),
        ("2012-05", 0, 0, 60, 0, 60, 0),
    ]
    assert p.runout_month == "2012-01"
    assert p.lead_months == 1
    assert p.value_at_risk_gbp == 520.00
    assert round(p.cover_months, 2) == 1.67
