"""
Tests for the S&P 500 "Selected changes" table parser.

Only the pure parsing function is tested with a small, synthetic, offline
fixture shaped like the real Wikipedia markup (measured live 2026-07-18) --
same convention as universe.sources' own constituents parser and
backtesting.sec_edgar's converters. No live network call is made here.
"""
from __future__ import annotations

import pytest

from universe.sp500_changes import (
    SP500Change,
    parse_sp500_changes,
    reconstruct_membership,
)


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


def _change(effective_date, added="", removed="") -> SP500Change:
    return SP500Change(
        effective_date=effective_date,
        added_ticker=added,
        added_security="",
        removed_ticker=removed,
        removed_security="",
        reason="test",
    )


def test_reconstruct_membership_carries_untouched_symbol_from_window_start() -> None:
    result = reconstruct_membership(
        changes=(),
        current_constituents=["AAPL"],
        window_start="2020-01-01",
    )

    assert len(result.intervals) == 1
    interval = result.intervals[0]
    assert interval.symbol == "AAPL"
    assert interval.effective_from.isoformat() == "2020-01-01"
    assert interval.effective_to is None
    assert result.is_consistent


def test_reconstruct_membership_handles_a_simple_addition() -> None:
    """TSLA-shaped case: added within the window, still active today."""
    result = reconstruct_membership(
        changes=(_change("2020-12-21", added="TSLA", removed="AIV"),),
        current_constituents=["TSLA"],
        window_start="2020-01-01",
    )

    tsla = next(i for i in result.intervals if i.symbol == "TSLA")
    assert tsla.effective_from.isoformat() == "2020-12-21"
    assert tsla.effective_to is None
    # AIV was removed with no prior "add" in the window -- lower-bounded at
    # window_start, and correctly absent from today's reconstruction.
    aiv = next(i for i in result.intervals if i.symbol == "AIV")
    assert aiv.effective_from.isoformat() == "2020-01-01"
    assert aiv.effective_to.isoformat() == "2020-12-21"
    assert "AIV" not in result.reconstructed_today
    assert result.is_consistent


def test_reconstruct_membership_handles_add_then_remove_within_window() -> None:
    """A symbol that entered and left entirely inside the window must not
    get a still-open interval -- it is genuinely not a member today."""
    result = reconstruct_membership(
        changes=(
            _change("2021-03-01", added="ZZZZ", removed="AAAA"),
            _change("2022-06-01", added="BBBB", removed="ZZZZ"),
        ),
        current_constituents=["BBBB"],
        window_start="2020-01-01",
    )

    zzzz_intervals = [i for i in result.intervals if i.symbol == "ZZZZ"]
    assert len(zzzz_intervals) == 1
    assert zzzz_intervals[0].effective_from.isoformat() == "2021-03-01"
    assert zzzz_intervals[0].effective_to.isoformat() == "2022-06-01"
    assert "ZZZZ" not in result.reconstructed_today
    assert result.is_consistent


def test_reconstruct_membership_handles_a_re_entry() -> None:
    """Removed once, later re-added: two separate intervals for the same
    symbol, correctly active today via the second one."""
    result = reconstruct_membership(
        changes=(
            _change("2021-01-01", added="X1", removed="CCCC"),
            _change("2023-01-01", added="CCCC", removed="X2"),
        ),
        current_constituents=["CCCC", "X1"],
        window_start="2020-01-01",
    )

    cccc_intervals = sorted(
        (i for i in result.intervals if i.symbol == "CCCC"),
        key=lambda i: i.effective_from,
    )
    assert len(cccc_intervals) == 2
    assert cccc_intervals[0].effective_from.isoformat() == "2020-01-01"
    assert cccc_intervals[0].effective_to.isoformat() == "2021-01-01"
    assert cccc_intervals[1].effective_from.isoformat() == "2023-01-01"
    assert cccc_intervals[1].effective_to is None
    assert "CCCC" in result.reconstructed_today
    assert result.is_consistent


def test_reconstruct_membership_flags_a_missing_change_instead_of_silently_drifting() -> None:
    """If the log is missing a change, reconstructed "today" will not match
    the real current constituents supplied as ground truth -- the whole
    point of anchoring on today instead of an unverifiable old baseline."""
    result = reconstruct_membership(
        changes=(
            # X was removed once in the window (closes its interval, absent
            # from reconstructed "today")...
            _change("2021-01-01", added="OTHER", removed="X"),
        ),
        # ...but ground truth says X is a member today anyway: something
        # must have re-added X later, and that change is missing from the
        # log -- a real gap, not an ambiguous case.
        current_constituents=["OTHER", "X"],
        window_start="2020-01-01",
    )

    assert not result.is_consistent
    assert result.missing_from_reconstruction == frozenset({"X"})
    assert result.unexpected_in_reconstruction == frozenset()


def test_reconstruct_membership_handles_same_day_ticker_reuse_for_a_new_entity() -> None:
    """Real case measured live (2026-07-18): 21st Century Fox was removed
    and Fox Corporation (a different entity, the post-Disney-merger
    spinoff) was added under the identical FOXA ticker on the same
    effective date. Must not crash on effective_to == effective_from,
    and must produce two real, correct intervals -- not a no-op."""
    result = reconstruct_membership(
        changes=(_change("2019-03-19", added="FOXA", removed="FOXA"),),
        current_constituents=["FOXA"],
        window_start="2015-01-01",
    )

    foxa_intervals = sorted(
        (i for i in result.intervals if i.symbol == "FOXA"),
        key=lambda i: i.effective_from,
    )
    assert len(foxa_intervals) == 2
    assert foxa_intervals[0].effective_from.isoformat() == "2015-01-01"
    assert foxa_intervals[0].effective_to.isoformat() == "2019-03-19"
    assert foxa_intervals[1].effective_from.isoformat() == "2019-03-19"
    assert foxa_intervals[1].effective_to is None
    assert "FOXA" in result.reconstructed_today
    assert result.is_consistent


def test_reconstruct_membership_flags_a_second_unmatched_removal_as_ambiguous() -> None:
    """Real case measured live: AGN was removed in 2015 and again in 2020
    with no recorded re-addition between them in the log -- almost
    certainly ticker reuse across a restructuring, not resolvable from this
    log alone. Must be reported as ambiguous, not guessed as two identical
    window_start-anchored intervals."""
    result = reconstruct_membership(
        changes=(
            _change("2015-03-23", added="", removed="AGN"),
            _change("2020-05-12", added="", removed="AGN"),
        ),
        current_constituents=[],
        window_start="2010-01-01",
    )

    assert "AGN" in result.anomalous_symbols
    assert not any(i.symbol == "AGN" for i in result.intervals)
    # AGN is correctly absent from both today-sets, but an ambiguity was
    # still encountered while building history in between -- is_consistent
    # stays False as a conservative "do not fully trust this window" signal
    # even though today's snapshot happens to line up.
    assert not result.is_consistent
    assert result.missing_from_reconstruction == frozenset()


def test_reconstruct_membership_flags_two_adds_with_no_remove_between() -> None:
    result = reconstruct_membership(
        changes=(
            _change("2016-01-01", added="DUPX", removed=""),
            _change("2018-01-01", added="DUPX", removed=""),
        ),
        current_constituents=["DUPX"],
        window_start="2015-01-01",
    )

    assert "DUPX" in result.anomalous_symbols
    assert not result.is_consistent  # DUPX expected today, but flagged, not reconstructed


def test_reconstruct_membership_ignores_changes_before_window_start() -> None:
    result = reconstruct_membership(
        changes=(_change("2015-01-01", added="OLD", removed="OLDER"),),
        current_constituents=["OLD"],
        window_start="2020-01-01",
    )

    # The 2015 change is outside the window, so OLD is treated as an
    # untouched symbol carried from window_start, not from the 2015 event.
    interval = next(i for i in result.intervals if i.symbol == "OLD")
    assert interval.effective_from.isoformat() == "2020-01-01"
    assert result.is_consistent
