from inventory_runout_planner.fmt import gbp, month, number, units

NNBSP = " "


def test_ac_22_formats() -> None:
    """AC-22: GBP, units, numbers and months with the U+202F thousands separator and half-up rounding."""
    assert gbp(1234567.891) == f"£1{NNBSP}234{NNBSP}568"
    assert gbp(400, pence=True) == "£400.00"
    assert gbp(0.005, pence=True) == "£0.01"
    assert units(1234) == f"1{NNBSP}234 units"
    assert number(1234567) == f"1{NNBSP}234{NNBSP}567"
    assert month("2012-01") == "Jan 2012"
