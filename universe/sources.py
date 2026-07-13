from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen


SP500_CONSTITUENTS_URL = (
    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
)


class _ConstituentsTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "constituents":
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
class ConstituentBatch:
    batch_number: int
    total_batches: int
    total_constituents: int
    frame_rows: tuple[dict[str, str], ...]


def parse_sp500_constituents(
    html: str,
    *,
    source_url: str = SP500_CONSTITUENTS_URL,
    snapshot_date: str | None = None,
) -> list[dict[str, str]]:
    parser = _ConstituentsTableParser()
    parser.feed(html)
    if len(parser.rows) < 2:
        raise ValueError("Tabela de constituintes não encontrada.")

    header = parser.rows[0]
    required = {
        "Symbol",
        "Security",
        "GICS Sector",
        "GICS Sub-Industry",
    }
    if not required.issubset(header):
        raise ValueError("Schema inesperado da tabela de constituintes.")

    as_of = snapshot_date or date.today().isoformat()
    records: list[dict[str, str]] = []
    for values in parser.rows[1:]:
        if len(values) < len(header):
            continue
        row = dict(zip(header, values))
        source_symbol = row["Symbol"].strip().upper()
        if not re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z])?", source_symbol):
            continue
        records.append(
            {
                "symbol": source_symbol.replace(".", "-"),
                "source_symbol": source_symbol,
                "name": row["Security"].strip(),
                "sector": row["GICS Sector"].strip(),
                "industry": row["GICS Sub-Industry"].strip(),
                "headquarters": row.get("Headquarters Location", "").strip(),
                "date_added": row.get("Date added", "").strip(),
                "cik": row.get("CIK", "").strip(),
                "founded": row.get("Founded", "").strip(),
                "source_url": source_url,
                "snapshot_date": as_of,
            }
        )

    records.sort(key=lambda item: item["symbol"])
    symbols = [item["symbol"] for item in records]
    if len(symbols) != len(set(symbols)):
        raise ValueError("Snapshot contém símbolos Yahoo duplicados.")
    return records


def fetch_sp500_constituents(
    *,
    url: str = SP500_CONSTITUENTS_URL,
    snapshot_date: str | None = None,
) -> list[dict[str, str]]:
    request = Request(url, headers={"User-Agent": "Atlas-Investment-OS/2.0"})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    return parse_sp500_constituents(
        html,
        source_url=url,
        snapshot_date=snapshot_date,
    )


def write_constituent_snapshot(
    records: Iterable[dict[str, str]],
    output_path: str | Path,
) -> Path:
    rows = list(records)
    if not rows:
        raise ValueError("Snapshot de constituintes não pode ser vazio.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output


def load_constituent_snapshot(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("Snapshot de constituintes está vazio.")
    symbols = [row.get("symbol", "").strip() for row in rows]
    if any(not symbol for symbol in symbols):
        raise ValueError("Snapshot contém símbolo vazio.")
    if len(symbols) != len(set(symbols)):
        raise ValueError("Snapshot contém símbolos duplicados.")
    return rows


def select_constituent_batch(
    records: Iterable[dict[str, str]],
    *,
    batch_size: int,
    batch_number: int,
) -> ConstituentBatch:
    rows = sorted(list(records), key=lambda row: row["symbol"])
    if batch_size <= 0:
        raise ValueError("batch_size deve ser positivo.")
    total_batches = math.ceil(len(rows) / batch_size) if rows else 0
    if batch_number < 1 or batch_number > total_batches:
        raise ValueError("batch_number fora do intervalo disponível.")
    start = (batch_number - 1) * batch_size
    return ConstituentBatch(
        batch_number=batch_number,
        total_batches=total_batches,
        total_constituents=len(rows),
        frame_rows=tuple(rows[start : start + batch_size]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atualiza o snapshot versionado do universo S&P 500."
    )
    parser.add_argument(
        "--output",
        default="config/research_universe.csv",
    )
    args = parser.parse_args()
    records = fetch_sp500_constituents()
    output = write_constituent_snapshot(records, args.output)
    print(f"{len(records)} constituintes salvos em {output}")


if __name__ == "__main__":
    main()
