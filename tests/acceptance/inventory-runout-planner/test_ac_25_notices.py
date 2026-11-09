from runout_toy import PAGES, app, texts


def test_ac_25_notices() -> None:
    """AC-25: every page shows the synthetic notice and planning date in the main area and the attribution in the sidebar."""
    at = app().run()
    for page in PAGES:
        at.switch_page(page).run()
        main = texts(at.main)
        assert "Synthetic stock data — demonstration only" in main, page
        assert "Planning as of 1 Dec 2011" in main, page
        side = texts(at.sidebar)
        assert "Online Retail II" in side, page
        assert "CC BY 4.0" in side, page
        assert "https://doi.org/10.24432/C5CG6D" in side, page
