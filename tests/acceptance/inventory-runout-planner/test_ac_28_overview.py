from inventory_runout_planner.fmt import gbp
from inventory_runout_planner.planner import run
from inventory_runout_planner.presets import BASELINE
from runout_toy import app, of, real_data, texts


def test_ac_28_overview() -> None:
    """AC-28: the run-out card shows '<Title Case description> (84347)', a Lead time chip, the status and cost lines,
    no 'Expedite?' / '(funded)'; a flags table (Product before Code) lists 47566 as Overstocked."""
    data = real_data()
    description = next(p.description for p in data.products if p.stock_code == "84347")
    stockout = of(run(data, BASELINE), "84347").model_dump()["stockout"]
    at = app().run()
    assert not at.exception
    main = texts(at.main)
    assert f"{description.title()} (84347)" in main
    assert "Lead time" in main
    assert "Out of stock Dec 2011–Feb 2012, covered from Mar 2012" in main
    assert f"{gbp(stockout['lost_sales_gbp'])} lost sales" in main
    assert "Expedite?" not in main
    assert "(funded)" not in main
    frames = [d.value for d in at.dataframe] + [t.value for t in at.table]
    flags = next(
        f
        for f in frames
        if "Code" in f.columns and f["Code"].astype(str).eq("47566").any()
    )
    cols = list(flags.columns)
    assert cols.index("Product") < cols.index("Code")
    assert (
        flags[flags["Code"].astype(str) == "47566"]
        .astype(str)
        .apply(lambda r: "Overstocked" in " ".join(r), axis=1)
        .any()
    )
