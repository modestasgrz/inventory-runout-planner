from pathlib import Path

import pytest
from runout_toy import app


def test_ac_32_missing_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-32: an empty data dir shows 'Data file not found: demand_monthly.csv', no metric, no exception."""
    monkeypatch.setenv("RUNOUT_DATA_DIR", str(tmp_path))
    at = app().run()
    assert not at.exception
    assert "Data file not found: demand_monthly.csv" in [e.value for e in at.error]
    assert len(at.metric) == 0
