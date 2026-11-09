from runout_toy import of, product, row, toy_run


def test_ac_08_order() -> None:
    """AC-08: T0001 order Dec 2011 -> Jan 2012, 200 units, 400.00, funded, limiting factor stock; with-plan rows."""
    p = of(toy_run(product("T0001")), "T0001")
    assert p.order is not None
    assert (p.order.order_month, p.order.arrival_month, p.order.qty) == (
        "2011-12",
        "2012-01",
        200,
    )
    assert p.order.cost_gbp == 400.00
    assert p.order.funded is True
    assert p.limiting_factor == "stock"
    assert [row(r) for r in p.plan_months] == [
        ("2011-12", 100, 0, 60, 60, 0, 40),
        ("2012-01", 40, 200, 60, 60, 0, 180),
        ("2012-02", 180, 0, 60, 60, 0, 120),
        ("2012-03", 120, 0, 60, 60, 0, 60),
        ("2012-04", 60, 0, 60, 60, 0, 0),
        ("2012-05", 0, 0, 60, 0, 60, 0),
    ]
