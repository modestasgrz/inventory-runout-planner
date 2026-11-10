import re
import tomllib

from runout_toy import REPO

FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
TOKENS = {
    "BG": "#0A0A0B",
    "BORDER": "#26262A",
    "MUTED": "#8A8A93",
    "BLUE": "#3B82F6",
    "AMBER": "#F59E0B",
    "RED": "#EF4444",
}


def test_ac_34_theme_config() -> None:
    """AC-34: config.toml has the Graphite theme and system font; theme.py holds the Graphite tokens;
    style.css hides the number-input steppers."""
    theme = tomllib.loads((REPO / ".streamlit" / "config.toml").read_text())["theme"]
    assert theme["base"] == "dark"
    assert theme["backgroundColor"].upper() == "#0A0A0B"
    assert theme["secondaryBackgroundColor"].upper() == "#111113"
    assert theme["textColor"].upper() == "#EDEDEF"
    assert theme["primaryColor"].upper() == "#EDEDEF"
    assert theme["font"] == FONT
    source = (REPO / "src" / "inventory_runout_planner" / "ui" / "theme.py").read_text()
    for name, value in TOKENS.items():
        assert re.search(
            rf'^{name} = "{value}"', source, re.MULTILINE | re.IGNORECASE
        ), name
    css = (REPO / "assets" / "style.css").read_text()
    for testid in ("stNumberInputStepUp", "stNumberInputStepDown"):
        rule = re.search(
            r'([^{}]*\[data-testid="' + testid + r'"\][^{}]*)\{([^}]*)\}', css
        )
        assert rule is not None, testid
        assert re.search(r"display\s*:\s*none", rule.group(2)), testid
