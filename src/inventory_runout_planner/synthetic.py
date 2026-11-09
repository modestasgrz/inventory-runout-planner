"""Seeded synthetic stock data (DEC-06). Demand is real; every field generated here is synthetic."""

import math

import numpy as np
from inventory_runout_planner.models import Product

COST_SHARE = 0.6
LEAD_CHOICES = [4, 6, 8, 10, 12]


def round_up(value: float, step: int) -> int:
    return max(step, step * math.ceil(value / step))


def generate(
    history: dict[str, list[int]],
    prices: dict[str, float],
    names: dict[str, tuple[str, str]],
    seed: int,
) -> list[Product]:
    """history: 24 months oldest first (Dec 2009 … Nov 2011); names: code → (description, group)."""
    rng = np.random.default_rng(seed)
    products = []
    for code in sorted(history):
        last12 = history[code][-12:]
        avg = sum(last12) / 12
        dec = last12[0]
        stock = max(round(avg * float(rng.uniform(2.0, 6.0))), round(dec * 1.3))
        fields = {
            "stock_on_hand": stock,
            "lead_time_weeks": int(rng.choice(LEAD_CHOICES)),
            "moq": round_up(avg * 0.5, 50),
            "inbound_qty": 0,
            "inbound_weeks": 0,
        }
        if code == "84347":
            fields |= {
                "stock_on_hand": round(dec * 0.6),
                "lead_time_weeks": 10,
            }
        elif code == "85123A":
            fields |= {
                "stock_on_hand": dec + round(last12[1] * 0.5),
                "lead_time_weeks": 4,
            }
        elif code == "47566":
            fields |= {
                "stock_on_hand": round(sum(last12) * 1.3),
                "lead_time_weeks": 6,
            }
        elif code == "85099B":
            fields |= {
                "stock_on_hand": dec + 100,
                "lead_time_weeks": 6,
                "inbound_qty": round_up(sum(last12[1:5]) * 1.1, 100),
                "inbound_weeks": 3,
            }
        elif code == "21212":
            fields |= {
                "stock_on_hand": sum(last12[:5]),
                "lead_time_weeks": 8,
                "inbound_qty": round_up(sum(last12[5:]) * 1.2, 100),
                "inbound_weeks": 16,
            }
        stock_total = fields["stock_on_hand"] + fields["inbound_qty"]
        fields["capacity"] = round_up(
            max(fields["stock_on_hand"] * 1.5, avg * 6, stock_total * 1.2), 100
        )
        description, group = names[code]
        products.append(
            Product(
                stock_code=code,
                description=description,
                group=group,
                unit_cost=max(0.01, round(prices[code] * COST_SHARE, 2)),
                **fields,
            )
        )
    return products
