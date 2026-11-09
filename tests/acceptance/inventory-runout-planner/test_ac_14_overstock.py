from runout_toy import of, product, toy_run


def test_ac_14_overstock() -> None:
    """AC-14: 1000 units vs 60/month over 12 months -> no run-out, no order, limiting factor none, Overstocked 16.7 months."""
    p = of(toy_run(product("T0005", stock_on_hand=1000), horizon_months=12), "T0005")
    assert p.runout_month is None
    assert p.order is None
    assert p.limiting_factor == "none"
    assert "Overstocked: 16.7 months of cover" in p.flags
