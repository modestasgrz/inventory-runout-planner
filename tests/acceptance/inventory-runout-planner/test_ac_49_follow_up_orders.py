from runout_toy import of, product, toy_run


def test_ac_49_follow_up_orders() -> None:
    """AC-49: a second order is planned on top of the first when stock dips again; it is funded only if the first
    one is and it fits the budget left; max_orders=1 keeps one order."""
    result = toy_run(product("T0001"), max_orders=4)
    plan = [line.model_dump() for line in result.plan]
    assert [line["rank"] for line in plan] == [1, 2]
    first, second = plan
    assert (first["order_no"], first["order_month"], first["qty"]) == (
        1,
        "2011-12",
        200,
    )
    assert {
        k: second[k]
        for k in (
            "order_no",
            "order_month",
            "arrival_month",
            "qty",
            "cost_gbp",
            "funded",
            "limiting_factor",
        )
    } == {
        "order_no": 2,
        "order_month": "2012-03",
        "arrival_month": "2012-04",
        "qty": 180,
        "cost_gbp": 360.00,
        "funded": True,
        "limiting_factor": "stock",
    }
    assert second["reason"].startswith(
        "Follow-up order 2: runs out May 2012 after the earlier order(s)."
    )
    p = of(result, "T0001")
    assert all(r.unmet == 0 for r in p.plan_months)
    assert p.model_dump()["lost_sales_after_plan_gbp"] == 0.00

    tight = toy_run(product("T0001"), max_orders=4, budget_gbp=700)
    second = tight.plan[1].model_dump()
    assert second["funded"] is False
    assert second["limiting_factor"] == "budget"
    assert second["reason"].endswith("Not funded: £300.00 left of budget.")
    assert "Short after plan: 60 units from May 2012" in of(tight, "T0001").flags

    blocked = toy_run(product("T0001"), max_orders=4, budget_gbp=380)
    first, second = (line.model_dump() for line in blocked.plan)
    assert first["funded"] is False
    assert second["cost_gbp"] == 360.00
    assert second["funded"] is False
    assert second["reason"].endswith("Not funded: earlier order not funded.")

    assert len(toy_run(product("T0001"), max_orders=1).plan) == 1
