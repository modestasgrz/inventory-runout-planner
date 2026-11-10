from runout_toy import KPI_LABELS, PAGES, app, kpis


def test_ac_24_same_kpis() -> None:
    """AC-24: every page (Overview included) renders under Baseline with the same 5 KPI metrics, identical everywhere."""
    at = app().run()
    seen = []
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        values = kpis(at)
        assert list(values) == KPI_LABELS, page
        seen.append(values)
    assert all(v == seen[0] for v in seen)
