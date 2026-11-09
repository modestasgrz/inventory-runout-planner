from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import PRESETS
from runout_toy import PRESET_NAMES, real_data


def test_ac_16_invariants() -> None:
    """AC-16: on real data under every preset, both projections are non-negative and conserve stock; spend <= budget."""
    data = real_data()
    assert list(PRESETS) == PRESET_NAMES
    for name, scenario in PRESETS.items():
        result = run(data, scenario)
        assert result.kpis.funded_spend_gbp <= result.kpis.budget_gbp, name
        for p in result.products:
            for rows in (p.months, p.plan_months):
                assert len(rows) == scenario.horizon_months
                for i, r in enumerate(rows):
                    assert (
                        min(
                            r.demand,
                            r.opening,
                            r.inbound,
                            r.shipped,
                            r.unmet,
                            r.closing,
                        )
                        >= 0
                    ), (name, p.stock_code)
                    assert r.shipped + r.unmet == r.demand, (
                        name,
                        p.stock_code,
                        r.month,
                    )
                    assert r.closing == r.opening + r.inbound - r.shipped, (
                        name,
                        p.stock_code,
                        r.month,
                    )
                    if i + 1 < len(rows):
                        assert rows[i + 1].opening == r.closing, (
                            name,
                            p.stock_code,
                            r.month,
                        )
