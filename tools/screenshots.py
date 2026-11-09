"""Full-page screenshots of every page at 1280 and 1440 px, plus the four non-Baseline presets on Overview.

Usage: make run (in another terminal), then uv run python tools/screenshots.py [base_url]
"""

import sys
from pathlib import Path

from loguru import logger
from playwright.sync_api import Page, sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
PAGES = {
    "overview": "",
    "forecast": "forecast",
    "scenarios": "scenarios",
    "reorder-plan": "reorder_plan",
    "methodology": "methodology",
}
PRESETS = {
    "peak": "Peak season +25%",
    "delay": "Supplier delay +3 weeks",
    "tight-budget": "Tight budget",
    "efficiency": "Efficiency",
}
WIDTHS = [1280, 1440]


def settle(page: Page) -> None:
    page.wait_for_selector('[data-testid="stMetric"]', timeout=30_000)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')",
        timeout=30_000,
    )
    page.wait_for_timeout(1_500)


def shoot(page: Page, path: Path, width: int) -> None:
    """Streamlit scrolls an inner container, so grow the viewport to the content height first."""
    height = page.evaluate(
        "document.querySelector('[data-testid=\"stMain\"]').scrollHeight"
    )
    page.set_viewport_size({"width": width, "height": max(900, int(height))})
    page.wait_for_timeout(800)
    page.screenshot(path=path, full_page=True)
    page.set_viewport_size({"width": width, "height": 900})


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8786"
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in WIDTHS:
            page = browser.new_page(
                viewport={"width": width, "height": 900}, locale="en-GB"
            )
            for name, path in PAGES.items():
                page.goto(f"{base}/{path}")
                settle(page)
                shoot(page, OUT / f"{width}-{name}.png", width)
            for name, preset in PRESETS.items():
                page.goto(base)
                settle(page)
                page.get_by_label("Preset").click()
                page.get_by_role("option", name=preset, exact=True).click()
                settle(page)
                shoot(page, OUT / f"{width}-overview-{name}.png", width)
            page.close()
        browser.close()
    logger.info("Saved screenshots to {}", OUT)


if __name__ == "__main__":
    main()
