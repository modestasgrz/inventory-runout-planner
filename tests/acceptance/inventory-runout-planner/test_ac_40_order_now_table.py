from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import PRESETS
from runout_toy import app, real_data


def test_ac_40_order_now_table() -> None:
    """AC-40: Overview's Order now table lists exactly the order_now products, with Qty, Cost £ and Funded columns."""
    data = real_data()
    at = app().run()
    for name, scenario in PRESETS.items():
        at.selectbox(key="preset").select(name).run()
        assert not at.exception, name
        wanted = [
            p.stock_code
            for p in run(data, scenario).products
            if p.model_dump()["order_now"]
        ]
        table = next(d.value for d in at.dataframe if "Runs out" in d.value.columns)
        assert list(table["Code"].astype(str)) == wanted, name
        assert {"Qty", "Cost £", "Funded"} <= set(table.columns), name
