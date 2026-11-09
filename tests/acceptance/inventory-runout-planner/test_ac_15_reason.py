from inventory_runout_planner.fmt import gbp, number, units
from runout_toy import of, product, toy_run


def test_ac_15_reason() -> None:
    """AC-15: T0001's order reason cites its numbers per the DEC-12 template."""
    p = of(toy_run(product("T0001")), "T0001")
    assert p.order is not None
    reason = p.order.reason
    for part in (
        "Runs out Jan 2012",
        "order Dec 2011, arrives Jan 2012",
        f"Order {units(200)}",
        f"demand {number(180)}",
        f"safety {number(60)}",
        f"available {number(40)}",
        f"MOQ {number(50)}",
        gbp(400, pence=True),
    ):
        assert part in reason, part
