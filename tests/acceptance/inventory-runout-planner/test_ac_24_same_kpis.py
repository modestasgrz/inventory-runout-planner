from runout_toy import KPI_LABELS, OVERVIEW_KPI_LABELS, PAGES, app, kpis


def test_ac_24_same_kpis() -> None:
    """AC-24: every page renders under Baseline; Overview shows the KPIs without Earliest run-out, the others all 6;
    each KPI value is identical on every page that shows it."""
    at = app().run()
    seen: dict[str, set[str]] = {}
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
        values = kpis(at)
        wanted = OVERVIEW_KPI_LABELS if page.endswith("overview.py") else KPI_LABELS
        assert list(values) == wanted, page
        for label, value in values.items():
            seen.setdefault(label, set()).add(value)
    assert all(len(v) == 1 for v in seen.values()), seen
