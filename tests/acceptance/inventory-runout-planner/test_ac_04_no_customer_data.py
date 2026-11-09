import subprocess

from runout_toy import REPO

BANNED = {"Customer ID", "customer_id", "Invoice", "Country"}


def test_ac_04_no_customer_data() -> None:
    """AC-04: no committed data file has a customer/invoice/country column, and none is larger than 200 KB."""
    files = subprocess.run(
        ["git", "ls-files", "data"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert {
        "data/demand_monthly.csv",
        "data/products_synthetic.csv",
        "data/median_prices.csv",
    } <= set(files)
    for name in files:
        path = REPO / name
        assert path.stat().st_size <= 200 * 1024, name
        if name.endswith(".csv"):
            header = path.read_text().splitlines()[0].split(",")
            assert not BANNED & {h.strip() for h in header}, name
