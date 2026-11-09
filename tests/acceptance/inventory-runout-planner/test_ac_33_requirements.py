import shutil
import subprocess

from runout_toy import REPO


def packages(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_ac_33_requirements() -> None:
    """AC-33: requirements.txt equals `uv export --no-dev --no-hashes --frozen` (comments ignored) and pins streamlit==1.67.0."""
    uv = shutil.which("uv")
    assert uv is not None
    exported = subprocess.run(
        [uv, "export", "--no-dev", "--no-hashes", "--frozen"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    committed = (REPO / "requirements.txt").read_text()
    assert packages(committed) == packages(exported)
    assert "streamlit==1.67.0" in packages(committed)
