from __future__ import annotations

from pathlib import Path

import pytest

from universe.sources import (
    load_constituent_snapshot,
    parse_sp500_constituents,
    select_constituent_batch,
    write_constituent_snapshot,
)


HTML = """
<table id="constituents">
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>
<th>GICS Sub-Industry</th><th>Headquarters Location</th>
<th>Date added</th><th>CIK</th><th>Founded</th></tr>
<tr><td>MSFT</td><td>Microsoft</td><td>Information Technology</td>
<td>Systems Software</td><td>Redmond, Washington</td>
<td>1994-06-01</td><td>0000789019</td><td>1975</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td>
<td>Multi-Sector Holdings</td><td>Omaha, Nebraska</td>
<td>2010-02-16</td><td>0001067983</td><td>1839</td></tr>
</table>
"""


def test_parse_constituents_normalizes_yahoo_symbols() -> None:
    records = parse_sp500_constituents(
        HTML,
        source_url="https://example.test/source",
        snapshot_date="2026-07-13",
    )

    assert [row["symbol"] for row in records] == ["BRK-B", "MSFT"]
    assert records[0]["source_symbol"] == "BRK.B"
    assert records[0]["snapshot_date"] == "2026-07-13"
    assert records[1]["sector"] == "Information Technology"


def test_parse_rejects_missing_table_and_schema() -> None:
    with pytest.raises(ValueError, match="não encontrada"):
        parse_sp500_constituents("<html></html>")
    with pytest.raises(ValueError, match="Schema inesperado"):
        parse_sp500_constituents(
            '<table id="constituents"><tr><th>Symbol</th></tr>'
            '<tr><td>AAA</td></tr></table>'
        )


def test_snapshot_roundtrip_and_validation(tmp_path: Path) -> None:
    records = parse_sp500_constituents(HTML, snapshot_date="2026-07-13")
    output = write_constituent_snapshot(records, tmp_path / "universe.csv")

    assert load_constituent_snapshot(output) == records
    with pytest.raises(ValueError, match="não pode ser vazio"):
        write_constituent_snapshot([], tmp_path / "empty.csv")


def test_batches_are_deterministic_and_complete() -> None:
    records = [
        {"symbol": symbol}
        for symbol in ["DDD", "AAA", "CCC", "BBB", "EEE"]
    ]

    first = select_constituent_batch(records, batch_size=2, batch_number=1)
    third = select_constituent_batch(records, batch_size=2, batch_number=3)

    assert first.total_constituents == 5
    assert first.total_batches == 3
    assert [row["symbol"] for row in first.frame_rows] == ["AAA", "BBB"]
    assert [row["symbol"] for row in third.frame_rows] == ["EEE"]


def test_batch_contract_rejects_invalid_bounds() -> None:
    records = [{"symbol": "AAA"}]
    with pytest.raises(ValueError, match="batch_size"):
        select_constituent_batch(records, batch_size=0, batch_number=1)
    with pytest.raises(ValueError, match="batch_number"):
        select_constituent_batch(records, batch_size=1, batch_number=2)


def test_canonical_research_universe_snapshot_is_pinned() -> None:
    records = load_constituent_snapshot("config/research_universe.csv")

    assert len(records) == 503
    assert len({row["symbol"] for row in records}) == 503
    assert {row["snapshot_date"] for row in records} == {"2026-07-13"}
    assert {row["source_url"] for row in records} == {
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    }
    assert len({row["sector"] for row in records}) == 11
    assert any(row["symbol"] == "BRK-B" for row in records)
