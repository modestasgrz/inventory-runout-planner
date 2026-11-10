from runout_toy import of, product, toy_run


def test_ac_39_order_now_flag() -> None:
    """AC-39: order_now = run-out within lead months + 1 (the products_at_risk link moved to AC-45)."""
    result = toy_run(
        product("T0001"),
        product("T0002", lead_time_weeks=10),
        product("T0006", stock_on_hand=300),
        product("T0005", stock_on_hand=1000),
    )
    assert [
        of(result, c).model_dump()["order_now"]
        for c in ("T0001", "T0002", "T0006", "T0005")
    ] == [
        True,
        True,
        False,
        False,
    ]
