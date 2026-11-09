import math
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

NNBSP = " "


def _rounded(value: float, places: int) -> Decimal:
    return (
        Decimal(str(value)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP) + 0
    )  # + 0 turns -0 into 0


def number(n: float) -> str:
    if not math.isfinite(n):
        return "∞"
    return f"{_rounded(n, 0):,.0f}".replace(",", NNBSP)


def units(n: float) -> str:
    return f"{number(n)} units"


def gbp(value: float, pence: bool = False) -> str:
    places = 2 if pence else 0
    return f"£{_rounded(value, places):,.{places}f}".replace(",", NNBSP)


def month(key: str) -> str:
    return datetime.strptime(key, "%Y-%m").strftime("%b %Y")
