"""
Tests for the S&P 500 "Selected changes" table parser.

Only the pure parsing function is tested with a small, synthetic, offline
fixture shaped like the real Wikipedia markup (measured live 2026-07-18) --
same convention as universe.sources' own constituents parser and
backtesting.sec_edgar's converters. No live network call is made here.
"""
from __future__ import annotations

import pytest

from universe.sp500_changes import SP500Change, parse_sp500_changes


def _table(rows_html: str) -> str:
    return f"""
    <html><body>
    <table class="wikitable sortable" id="changes">
    <tbody>
    <tr>
    <th rowspan="2">Effective Date</th>
    <th colspan="2">Added</th>
    <th colspan="2">Removed</th>
    <th rowspan="2">Reason</th></tr>
    <tr>
    <th>Ticker</th><th>Security</th><th>Ticker</th><th>Security</th></tr>
    {rows_html}
    </tbody>
    </table>
    </body></html>
    """


def test_parses_a_symmetric_add_and_remove_row() -> None:
    html = _table(
        """
        <tr><td>June 24, 2026</td><td>ECHO</td>
        <td><a href="/wiki/EchoStar">EchoStar</a></td>
        <td>SATS</td><td>EchoStar</td>
        <td>EchoStar changed its ticker symbol from SATS to ECHO.
        <sup class="reference"><a href="#cite_note-7">[7]</a></sup></td></tr>
        """
    )

    changes = parse_sp500_changes(html)

    assert changes == (
        SP500Change(
            effective_date="2026-06-24",
            added_ticker="ECHO",
            added_security="EchoStar",
            removed_ticker="SATS",
            removed_security="EchoStar",
            reason="EchoStar changed its ticker symbol from SATS to ECHO. [7]",
        ),
    )


def test_parses_a_removal_only_row_without_inventing_an_addition() -> None:
    """A real measured row (2026-07-18): Conagra's removal with no ticker
    named as its replacement on the same row. The parser must not invent
    an added_ticker/added_security to fill the gap."""
    html = _table(
        """
        <tr><td>June 30, 2026</td><td></td><td></td>
        <td>CAG</td><td>Conagra Brands</td>
        <td>Market capitalization change.</td></tr>
        """
    )

    changes = parse_sp500_changes(html)

    assert changes[0].added_ticker == ""
    assert changes[0].added_security == ""
    assert changes[0].removed_ticker == "CAG"


def test_parses_multiple_rows_in_document_order() -> None:
    html = _table(
        """
        <tr><td>July 1, 1976</td><td>DIS</td><td>The Walt Disney Company</td>
        <td>AYE</td><td>Allegheny Energy</td><td>Major restructuring.</td></tr>
        <tr><td>June 22, 2026</td><td>MRVL</td><td>Marvell Technology</td>
        <td>POOL</td><td>Pool Corporation</td><td>Market cap change.</td></tr>
        """
    )

    changes = parse_sp500_changes(html)

    assert [change.effective_date for change in changes] == [
        "1976-07-01",
        "2026-06-22",
    ]


def test_rejects_missing_table() -> None:
    with pytest.raises(ValueError, match="não encontrada"):
        parse_sp500_changes("<html><body>no table here</body></html>")


def test_rejects_unparseable_date_instead_of_guessing() -> None:
    html = _table(
        """
        <tr><td>not-a-date</td><td>AAA</td><td>Alpha</td>
        <td>BBB</td><td>Beta</td><td>reason</td></tr>
        """
    )

    with pytest.raises(ValueError):
        parse_sp500_changes(html)


def test_ignores_rows_with_wrong_column_count() -> None:
    """A malformed or edited row (e.g. a stray merged cell) is skipped, not
    force-fit into the fixed 6-column mapping."""
    html = _table(
        """
        <tr><td>June 1, 2026</td><td>only</td><td>three</td><td>cells</td></tr>
        <tr><td>June 2, 2026</td><td>AAA</td><td>Alpha</td>
        <td>BBB</td><td>Beta</td><td>reason</td></tr>
        """
    )

    changes = parse_sp500_changes(html)

    assert len(changes) == 1
    assert changes[0].effective_date == "2026-06-02"
