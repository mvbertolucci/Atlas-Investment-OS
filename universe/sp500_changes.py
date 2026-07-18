from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen

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
