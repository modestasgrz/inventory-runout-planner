from runout_toy import KPI_LABELS, PAGES, app, kpis


def test_ac_24_same_kpis() -> None:
    """AC-24: every page renders under Baseline with the 5 KPI metrics, each identical on all 5 pages."""
    at = app().run()
    seen = []
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        values = kpis(at)
        assert list(values) == KPI_LABELS, page
        seen.append(values)
    assert all(v == seen[0] for v in seen)
