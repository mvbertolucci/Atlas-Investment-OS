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

# Diretório oficial de símbolos da NASDAQ Trader -- cobre NASDAQ (arquivo
# "nasdaqlisted") e as demais bolsas dos EUA (NYSE, NYSE American, NYSE Arca,
# Cboe BATS) no arquivo "otherlisted". É a fonte pública mais próxima de um
# "mercado americano inteiro" com small caps: não existe lista de
# constituintes gratuita para índices como Russell 3000/Wilshire 5000 (são
# proprietários da FTSE/Russell).
NASDAQ_LISTED_URL = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
)
OTHER_LISTED_URL = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
)

_OTHER_EXCHANGE_NAMES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BATS",
    "V": "IEXG",
}


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


def _parse_pipe_delimited(text: str) -> list[dict[str, str]]:
    """
    Parser genérico dos arquivos de diretório da NASDAQ Trader: pipe-
    delimited, primeira linha é o cabeçalho, última linha é um rodapé
    "File Creation Time: ..." (descartado).
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return []

    header = lines[0].split("|")
    rows: list[dict[str, str]] = []

    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        values = line.split("|")
        if len(values) != len(header):
            continue
        rows.append(dict(zip(header, values)))

    return rows


def parse_nasdaq_listed(text: str) -> list[dict[str, str]]:
    """
    Parser do arquivo `nasdaqlisted.txt`. Exclui explicitamente ETFs,
    NextShares (veículos tipo fundo) e Test Issues via as flags do próprio
    arquivo -- não via heurística de ticker.

    O filtro de símbolo (`_SYMBOL_PATTERN`) é best-effort para excluir
    preferenciais/warrants/units que não têm flag dedicada neste arquivo;
    a camada real de garantia é o `allowed_quote_types` do universo, que
    verifica o `quote_type` de verdade retornado pelo Yahoo em cada ticker.
    """
    records: list[dict[str, str]] = []

    for row in _parse_pipe_delimited(text):
        if row.get("Test Issue") == "Y":
            continue
        if row.get("ETF") == "Y":
            continue
        if row.get("NextShares") == "Y":
            continue

        symbol = row.get("Symbol", "").strip().upper()
        if not re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z])?", symbol):
            continue

        records.append(
            {
                "symbol": symbol.replace(".", "-"),
                "source_symbol": symbol,
                "name": row.get("Security Name", "").strip(),
                "exchange": "NASDAQ",
            }
        )

    return records


def parse_other_listed(text: str) -> list[dict[str, str]]:
    """
    Parser do arquivo `otherlisted.txt` (NYSE, NYSE American, NYSE Arca,
    Cboe BATS). Mesmo critério de exclusão explícita de `parse_nasdaq_listed`.
    """
    records: list[dict[str, str]] = []

    for row in _parse_pipe_delimited(text):
        if row.get("Test Issue") == "Y":
            continue
        if row.get("ETF") == "Y":
            continue

        symbol = row.get("ACT Symbol", "").strip().upper()
        if not re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z])?", symbol):
            continue

        exchange_code = row.get("Exchange", "").strip()

        records.append(
            {
                "symbol": symbol.replace(".", "-"),
                "source_symbol": symbol,
                "name": row.get("Security Name", "").strip(),
                "exchange": _OTHER_EXCHANGE_NAMES.get(
                    exchange_code,
                    exchange_code,
                ),
            }
        )

    return records


def fetch_us_market_constituents(
    *,
    nasdaq_url: str = NASDAQ_LISTED_URL,
    other_url: str = OTHER_LISTED_URL,
    snapshot_date: str | None = None,
) -> list[dict[str, str]]:
    """
    Constrói o snapshot do screener de mercado amplo (NASDAQ + demais bolsas
    dos EUA), separado do screener S&P 500. Um mesmo símbolo pode aparecer
    nos dois arquivos-fonte (dupla listagem); mantém a primeira ocorrência
    de forma determinística.

    Não inclui setor/indústria/GICS -- essa fonte não os fornece. Isso é
    inofensivo: `universe.collector.collect_constituent_batch` só usa
    `symbol`/`name`/`source_symbol` do snapshot; setor, país, preço, volume
    e market cap vêm do fetch ao vivo do Yahoo por ticker, igual ao
    screener S&P 500.
    """
    as_of = snapshot_date or date.today().isoformat()

    nasdaq_request = Request(
        nasdaq_url,
        headers={"User-Agent": "Atlas-Investment-OS/2.0"},
    )
    with urlopen(nasdaq_request, timeout=30) as response:
        nasdaq_text = response.read().decode("utf-8")

    other_request = Request(
        other_url,
        headers={"User-Agent": "Atlas-Investment-OS/2.0"},
    )
    with urlopen(other_request, timeout=30) as response:
        other_text = response.read().decode("utf-8")

    combined = parse_nasdaq_listed(nasdaq_text) + parse_other_listed(
        other_text
    )

    deduplicated: dict[str, dict[str, str]] = {}
    for record in combined:
        deduplicated.setdefault(record["symbol"], record)

    records = [
        {
            **record,
            "source_url": f"{nasdaq_url} ; {other_url}",
            "snapshot_date": as_of,
        }
        for record in sorted(
            deduplicated.values(),
            key=lambda item: item["symbol"],
        )
    ]

    if not records:
        raise ValueError(
            "Nenhum constituinte válido encontrado nas fontes da NASDAQ Trader."
        )

    return records


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
        description=(
            "Atualiza o snapshot versionado de constituintes. Por padrão, "
            "o universo S&P 500 (Wikipedia); com --market, o universo "
            "amplo de mercado (NASDAQ Trader), um screener separado."
        )
    )
    parser.add_argument(
        "--market",
        action="store_true",
        help="Usa a fonte de mercado amplo (NASDAQ + demais bolsas) em vez do S&P 500.",
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.market:
        records = fetch_us_market_constituents()
        default_output = "config/research_universe_market.csv"
    else:
        records = fetch_sp500_constituents()
        default_output = "config/research_universe.csv"

    output = write_constituent_snapshot(
        records,
        args.output or default_output,
    )
    print(f"{len(records)} constituintes salvos em {output}")


if __name__ == "__main__":
    main()
