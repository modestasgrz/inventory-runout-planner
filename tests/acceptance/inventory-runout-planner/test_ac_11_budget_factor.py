from runout_toy import of, product, toy_run


def test_ac_11_budget_factor() -> None:
    """AC-11: T0001 with budget 300 -> not funded, limiting factor budget, funded spend 0, plan rows = do-nothing rows."""
    result = toy_run(product("T0001"), budget_gbp=300)
    p = of(result, "T0001")
    assert p.order is not None
    assert p.order.funded is False
    assert p.limiting_factor == "budget"
    assert result.kpis.funded_spend_gbp == 0.00
    assert p.plan_months == p.months
