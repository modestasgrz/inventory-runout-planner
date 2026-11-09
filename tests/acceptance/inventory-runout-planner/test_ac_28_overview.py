from runout_toy import app, real_data, texts


def test_ac_28_overview() -> None:
    """AC-28: Overview shows the earliest run-out as '<description> (84347)', Dec 2011, 'Limiting factor: lead time',
    and a flags table (Product before Code) listing 47566 as Overstocked."""
    description = next(
        p.description for p in real_data().products if p.stock_code == "84347"
    )
    at = app().run()
    assert not at.exception
    main = texts(at.main)
    assert f"{description} (84347)" in main
    assert "Dec 2011" in main
    assert "Limiting factor: lead time" in main
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
