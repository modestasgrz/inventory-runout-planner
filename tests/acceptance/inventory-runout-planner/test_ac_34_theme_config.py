import re
import tomllib

from runout_toy import REPO

FONT = '"Inter", "Avenir Next", "Helvetica Neue", Arial, sans-serif'


def test_ac_34_theme_config() -> None:
    """AC-34: config.toml theme is dark navy with the DEC-17 colors and font; style.css hides the number-input steppers."""
    theme = tomllib.loads((REPO / ".streamlit" / "config.toml").read_text())["theme"]
    assert theme["base"] == "dark"
    assert theme["backgroundColor"].upper() == "#0B1730"
    assert theme["secondaryBackgroundColor"].upper() == "#13223F"
    assert theme["textColor"].upper() == "#E6ECF5"
    assert theme["primaryColor"].upper() == "#3B82F6"
    assert theme["font"] == FONT
    css = (REPO / "assets" / "style.css").read_text()
    for testid in ("stNumberInputStepUp", "stNumberInputStepDown"):
        rule = re.search(
            r'([^{}]*\[data-testid="' + testid + r'"\][^{}]*)\{([^}]*)\}', css
        )
        assert rule is not None, testid
        assert re.search(r"display\s*:\s*none", rule.group(2)), testid
