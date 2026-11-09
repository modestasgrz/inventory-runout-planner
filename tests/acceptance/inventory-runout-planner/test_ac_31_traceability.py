from runout_toy import app, texts

GROUPS = ["Bags & storage", "Candles & lights", "Baking & party", "Gifts & small goods"]


def test_ac_31_traceability() -> None:
    """AC-31: every KPI metric has help text with its formula; Methodology shows the lead-time formula, the groups,
    the hand cases AC-07..AC-14 and the attribution."""
    at = app().run()
    assert len(at.metric) == 5
    for m in at.metric:
        assert m.proto.help.strip(), m.label
        assert "=" in m.proto.help, m.label
    at.switch_page("app_pages/methodology.py").run()
    assert not at.exception
    text = (
        texts(at.main)
        + "\n".join(str(d.value.to_string()) for d in at.dataframe)
        + "\n".join(str(t.value.to_string()) for t in at.table)
    )
    assert "ceil((lead time weeks + delay weeks) × 7 / 30.44)" in text
    for group in GROUPS:
        assert group in text, group
    for ac in range(7, 15):
        assert f"AC-{ac:02d}" in text, ac
    assert "10.24432/C5CG6D" in text
