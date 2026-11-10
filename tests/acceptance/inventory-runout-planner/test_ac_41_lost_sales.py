from runout_toy import of, product, toy_run


def test_ac_41_lost_sales() -> None:
    """AC-41: lost sales if nothing ordered / with the plan over the whole horizon (one order), £ tied up, KPI sums."""
    funded = of(toy_run(product("T0001")), "T0001").model_dump()
    assert funded["sell_price"] == 5.00
    assert funded["lost_sales_gbp"] == 1300.00
    assert funded["lost_sales_after_plan_gbp"] == 300.00
    assert funded["at_risk_after_plan"] is True
    assert funded["tied_up_gbp"] == 0.00
    unfunded = of(toy_run(product("T0001"), budget_gbp=300), "T0001").model_dump()
    assert unfunded["lost_sales_after_plan_gbp"] == 1300.00
    over = of(
        toy_run(product("T0005", stock_on_hand=1000), horizon_months=12), "T0005"
    ).model_dump()
    assert over["tied_up_gbp"] == 1280.00

    result = toy_run(
        product("T0001"),
        product("T0002", lead_time_weeks=10),
        product("T0005", stock_on_hand=1000),
    )
    k = result.kpis.model_dump()
    rows = [p.model_dump() for p in result.products]
    for field in ("lost_sales_gbp", "lost_sales_after_plan_gbp", "tied_up_gbp"):
        assert k[field] == round(sum(r[field] for r in rows), 2), field
