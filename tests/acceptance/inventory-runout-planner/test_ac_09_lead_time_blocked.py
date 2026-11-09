from runout_toy import of, product, toy_run


def test_ac_09_lead_time_blocked() -> None:
    """AC-09: T0002 (lead 10 weeks) -> 3 lead months, order Dec 2011 arrives Mar 2012, 240 units, 480.00, lead time."""
    p = of(toy_run(product("T0002", lead_time_weeks=10)), "T0002")
    assert p.lead_months == 3
    assert p.order is not None
    assert (p.order.order_month, p.order.arrival_month, p.order.qty) == (
        "2011-12",
        "2012-03",
        240,
    )
    assert p.order.cost_gbp == 480.00
    assert p.runout_month == "2012-01"
    assert p.limiting_factor == "lead time"
