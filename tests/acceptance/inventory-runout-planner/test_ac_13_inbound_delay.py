from runout_toy import of, product, toy_run

T0004 = product("T0004", stock_on_hand=70, inbound_qty=200, inbound_weeks=3)


def test_ac_13_inbound_delay() -> None:
    """AC-13: inbound arrives Jan 2012, run-out Apr 2012, order Mar -> Apr, 150 units, stock;
    with +3 weeks delay inbound arrives Feb 2012, run-out Jan 2012, lead 2 months, arrival Feb, lead time."""
    p = of(toy_run(T0004, safety_months=0), "T0004")
    assert p.inbound_month == "2012-01"
    assert p.months[1].inbound == 200
    assert p.runout_month == "2012-04"
    assert p.order is not None
    assert (p.order.order_month, p.order.arrival_month, p.order.qty) == (
        "2012-03",
        "2012-04",
        150,
    )
    assert p.limiting_factor == "stock"

    d = of(toy_run(T0004, safety_months=0, delay_weeks=3), "T0004")
    assert d.inbound_month == "2012-02"
    assert d.months[2].inbound == 200
    assert d.runout_month == "2012-01"
    assert d.lead_months == 2
    assert d.order is not None
    assert d.order.arrival_month == "2012-02"
    assert d.limiting_factor == "lead time"
