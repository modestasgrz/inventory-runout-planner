from runout_toy import of, product, toy_run


def test_ac_10_budget_ranking() -> None:
    """AC-10: ranking T0001, T0002, T0003; budget 650 funds T0001 + T0003 (skip, not stop); KPIs 600 / 1080 / 1."""
    result = toy_run(
        product("T0001"),
        product("T0002", lead_time_weeks=10),
        product("T0003", unit_cost=1.00),
        budget_gbp=650,
    )
    assert [(line.rank, line.stock_code, line.funded) for line in result.plan] == [
        (1, "T0001", True),
        (2, "T0002", False),
        (3, "T0003", True),
    ]
    assert [line.cost_gbp for line in result.plan] == [400.00, 480.00, 200.00]
    assert result.kpis.funded_spend_gbp == 600.00
    assert result.kpis.suggested_spend_gbp == 1080.00
    assert result.kpis.unfunded_orders == 1
    assert of(result, "T0002").limiting_factor == "lead time"
