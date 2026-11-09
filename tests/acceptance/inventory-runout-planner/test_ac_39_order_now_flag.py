from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import PRESETS
from runout_toy import of, product, real_data, toy_run


def test_ac_39_order_now_flag() -> None:
    """AC-39: order_now = run-out within lead months + 1; products_at_risk counts exactly those."""
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

    data = real_data()
    for name, scenario in PRESETS.items():
        r = run(data, scenario)
        assert r.kpis.products_at_risk == sum(
            p.model_dump()["order_now"] for p in r.products
        ), name
