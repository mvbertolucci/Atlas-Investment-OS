from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Iterable
from urllib.request import Request, urlopen

from backtesting.point_in_time import UniverseMembership
from universe.sources import SP500_CONSTITUENTS_URL


class _ChangesTableParser(HTMLParser):
    """Mirrors universe.sources._ConstituentsTableParser's approach (stdlib
    only, target the table by its stable `id`), for the second wikitable on
    the same page: `id="changes"`, "Selected changes to the list of S&P 500
    components". Two header rows (Effective Date/Added/Removed/Reason, then
    Ticker/Security/Ticker/Security) collapse to the same cell count as data
    rows because colspan/rowspan attributes are ignored -- callers skip the
    first two parsed rows and use fixed column positions, not a header dict.
    """

    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "changes":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"th", "td"}:
            self.in_cell = True
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in {"th", "td"} and self.in_cell:
            text = " ".join("".join(self.current_cell).split())
            self.current_row.append(text)
            self.in_cell = False
        elif self.in_table and tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []
        elif self.in_table and tag == "table":
            self.in_table = False


@dataclass(frozen=True)
class SP500Change:
    effective_date: str  # ISO 8601
    added_ticker: str
    added_security: str
    removed_ticker: str
    removed_security: str
    reason: str


def _parse_effective_date(text: str) -> str:
    """Wikipedia renders this column as e.g. "June 30, 2026". Raises
    ValueError on anything else rather than silently dropping or guessing a
    date -- an unparseable date is a schema change worth failing loudly on,
    not an absent row worth skipping quietly."""
    return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()


def parse_sp500_changes(html: str) -> tuple[SP500Change, ...]:
    parser = _ChangesTableParser()
    parser.feed(html)
    if len(parser.rows) < 3:
        raise ValueError("Tabela de mudanças do S&P 500 não encontrada.")

    # Two collapsed header rows (colspan/rowspan not reconstructed): row 0
    # is ["Effective Date", "Added", "Removed", "Reason"], row 1 is
    # ["Ticker", "Security", "Ticker", "Security"]. Fixed positional
    # mapping for data rows, not a header-name lookup.
    changes: list[SP500Change] = []
    for values in parser.rows[2:]:
        if len(values) != 6:
            continue
        effective_date_text, added_ticker, added_security, removed_ticker, removed_security, reason = values
        changes.append(
            SP500Change(
                effective_date=_parse_effective_date(effective_date_text),
                added_ticker=added_ticker.strip(),
                added_security=added_security.strip(),
                removed_ticker=removed_ticker.strip(),
                removed_security=removed_security.strip(),
                reason=reason.strip(),
            )
        )
    return tuple(changes)


def fetch_sp500_changes(*, url: str = SP500_CONSTITUENTS_URL) -> tuple[SP500Change, ...]:
    request = Request(url, headers={"User-Agent": "Atlas-Investment-OS/2.0"})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    return parse_sp500_changes(html)


@dataclass(frozen=True)
class MembershipReconstruction:
    """Result of reconstructing intervals from `window_start` to today.

    `is_consistent` is the integrity check this exists for: reconstructed
    "active today" must exactly match the real current constituent list
    supplied as ground truth, or a change is missing from the log somewhere
    in the window and the intervals should not be trusted blindly.
    """

    intervals: tuple[UniverseMembership, ...]
    reconstructed_today: frozenset[str]
    expected_today: frozenset[str]
    anomalous_symbols: frozenset[str] = frozenset()

    @property
    def missing_from_reconstruction(self) -> frozenset[str]:
        return self.expected_today - self.reconstructed_today - self.anomalous_symbols

    @property
    def unexpected_in_reconstruction(self) -> frozenset[str]:
        return self.reconstructed_today - self.expected_today

    @property
    def is_consistent(self) -> bool:
        return (
            not self.anomalous_symbols
            and self.reconstructed_today == self.expected_today
        )


def reconstruct_membership(
    changes: Iterable[SP500Change],
    current_constituents: Iterable[str],
    *,
    window_start: str,
    source: str = "Wikipedia S&P 500 selected changes (reconstructed)",
) -> MembershipReconstruction:
    """Reconstruct per-symbol membership intervals from `window_start` to
    today, anchored on the real current constituent list rather than an
    unknown ancient baseline -- see ADR-035's "next step" note.

    For a symbol with change events inside the window, its own event
    sequence (sorted chronologically) is walked to build alternating
    intervals: an "add" opens one, a "remove" closes it. A "remove" with no
    preceding "add" in the window means the symbol was already a member
    when the window started -- its interval's `effective_from` is
    `window_start` itself, an explicit lower bound, not a claim about when
    it actually joined. That lower-bound reasoning is only sound the FIRST
    time it happens for a symbol; a second "remove" with no intervening
    "add" (measured live: AGN, removed 2015 and again 2020 in the S&P 500
    log with no recorded re-addition between -- almost certainly ticker
    reuse across a corporate restructuring, not a data-entry error) cannot
    be resolved from this log alone and is reported as ambiguous instead of
    guessed. A same-day add-then-remove for the same symbol (measured live:
    FOXA, 2019-03-19, the Disney/Fox transaction) never opens a real
    interval -- explicitly skipped, not an anomaly, since it makes no
    membership claim either way. An "add" while an interval is already open
    (two adds with no remove between) is likewise ambiguous and reported,
    not guessed.

    A symbol with *no* change events in the window but present in
    `current_constituents` is assumed continuously active since
    `window_start` -- same explicit lower-bound caveat.

    Never claims certainty beyond what `window_start` bounds; the
    consistency check on the result is what tells the caller whether the
    window was actually complete, not an assumption baked into this
    function.
    """
    start = date.fromisoformat(window_start)
    expected_today = frozenset(
        str(symbol).strip().upper() for symbol in current_constituents if str(symbol).strip()
    )
    known_at = datetime.now(timezone.utc)

    events: dict[str, list[tuple[date, str]]] = {}
    for change in changes:
        change_date = date.fromisoformat(change.effective_date)
        if change_date < start:
            continue
        if change.added_ticker:
            events.setdefault(change.added_ticker, []).append((change_date, "add"))
        if change.removed_ticker:
            events.setdefault(change.removed_ticker, []).append((change_date, "remove"))

    intervals: list[UniverseMembership] = []
    anomalous_symbols: set[str] = set()
    touched_symbols = set(events)
    for symbol, symbol_events in events.items():
        # "remove" sorts before "add" on a same-date tie: a ticker reused
        # for a successor entity the same day (measured live: FOXA,
        # 2019-03-19 -- 21st Century Fox removed and Fox Corporation added
        # under the identical ticker for the Disney/Fox transaction) must
        # close the outgoing entity's interval before opening the
        # incoming one, not collide.
        symbol_events.sort(key=lambda item: (item[0], item[1] != "remove"))
        open_from: date | None = None
        used_start_heuristic = False
        symbol_intervals: list[UniverseMembership] = []
        is_anomalous = False
        for event_date, action in symbol_events:
            if action == "add":
                if open_from is not None:
                    is_anomalous = True  # two adds with no remove between
                    break
                open_from = event_date
            else:  # "remove"
                if open_from is None:
                    if used_start_heuristic:
                        is_anomalous = True  # second unmatched remove
                        break
                    interval_start = start
                    used_start_heuristic = True
                else:
                    interval_start = open_from
                symbol_intervals.append(
                    UniverseMembership(
                        symbol=symbol,
                        effective_from=interval_start,
                        effective_to=event_date,
                        known_at=known_at,
                        source=source,
                    )
                )
                open_from = None
        if is_anomalous:
            anomalous_symbols.add(symbol)
            continue
        if open_from is not None:
            symbol_intervals.append(
                UniverseMembership(
                    symbol=symbol,
                    effective_from=open_from,
                    effective_to=None,
                    known_at=known_at,
                    source=source,
                )
            )
        intervals.extend(symbol_intervals)

    for symbol in expected_today - touched_symbols:
        intervals.append(
            UniverseMembership(
                symbol=symbol,
                effective_from=start,
                effective_to=None,
                known_at=known_at,
                source=source,
            )
        )

    reconstructed_today = frozenset(
        interval.symbol for interval in intervals if interval.effective_to is None
    )
    return MembershipReconstruction(
        intervals=tuple(intervals),
        reconstructed_today=reconstructed_today,
        expected_today=expected_today,
        anomalous_symbols=frozenset(anomalous_symbols),
    )
