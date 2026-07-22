from __future__ import annotations

import pytest

from backtesting.total_return_batch import build_total_return_evidence_from_directory


def test_build_total_return_evidence_from_price_directory(tmp_path) -> None:
    prices = tmp_path / "prices"
    prices.mkdir()
    csv = (
        "Date,Close,Dividends\n"
        "2025-01-02,100,0\n"
        "2025-02-03,110,0\n"
        "2025-03-03,121,1\n"
    )
    (prices / "AAA.csv").write_text(csv, encoding="utf-8")
    (prices / "SPY.csv").write_text(csv.replace("100", "200"), encoding="utf-8")

    evidence = build_total_return_evidence_from_directory(
        prices,
        retrieved_at="2025-04-01T00:00:00Z",
    )

    assert len(evidence.returns) == 4
    aaa = [row for row in evidence.returns if row.symbol == "AAA"]
    assert aaa[0].total_return == pytest.approx(0.1)
    assert aaa[1].total_return > 0.1
