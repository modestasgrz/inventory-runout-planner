from runout_toy import PAGES, app, texts


def test_ac_25_notices() -> None:
    """AC-25: badge and 'Data as of Dec 2011' in the main area; sidebar has the planning date and CC BY 4.0 but no DOI."""
    at = app().run()
    for page in PAGES:
        at.switch_page(page).run()
        main = texts(at.main)
        assert "Synthetic stock data — demonstration only" in main, page
        assert "Data as of Dec 2011" in main, page
        assert "Planning as of" not in main, page
        side = texts(at.sidebar)
        assert "Planning as of 1 Dec 2011" in side, page
        assert "CC BY 4.0" in side, page
        assert "10.24432/C5CG6D" not in side, page
