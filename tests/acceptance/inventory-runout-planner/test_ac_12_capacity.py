from runout_toy import of, product, toy_run


def test_ac_12_capacity() -> None:
    """AC-12: capacity 200 caps the order at 160; MOQ 400 > room 360 blocks the order (limiting factor capacity, flag)."""
    capped = of(toy_run(product("T0001", capacity=200)), "T0001")
    assert capped.order is not None
    assert capped.order.qty == 160

    blocked = of(toy_run(product("T0001", moq=400)), "T0001")
    assert blocked.order is None
    assert blocked.limiting_factor == "capacity"
    assert "Capacity blocks order: room 360 < MOQ 400" in blocked.flags
