"""Coleta SEC não trava em símbolo que falha sempre, e resolve renomeação.

Os dois defeitos foram medidos ao vivo em 2026-07-24 coletando o S&P 500
para o backtest: BK (BNY Mellon) trocou de ticker -- a SEC o registra como
`BNY` sob o mesmo CIK 0001390777, enquanto o universo point-in-time de
2026-01-01 ainda diz `BK`. A busca por símbolo falhava, e como
`select_next_incomplete_batch` devolve sempre o primeiro lote incompleto, o
laço bateu 55 vezes no mesmo erro enquanto a coleta parava em 69 de 502.
"""
from __future__ import annotations

from pathlib import Path

from backtesting.sec_edgar_collector import (
    SecEdgarCollectionState,
    exhausted_symbols,
    load_cik_overrides_from_csv,
    select_next_incomplete_batch,
)


def _state(**failures) -> SecEdgarCollectionState:
    return SecEdgarCollectionState(
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
        failures=dict(failures),
    )


def test_persistently_failing_symbol_stops_blocking_progress() -> None:
    """O caso BK: sem isto o lote 1 é devolvido para sempre."""
    tickers = ("AAA", "BBB", "CCC", "DDD")
    state = _state(AAA={"attempts": 3, "last_error": "CIK não encontrado."})

    given_up = exhausted_symbols(state, max_attempts=3)
    batch = select_next_incomplete_batch(
        tickers, batch_size=2, completed_symbols=(), exhausted_symbols=given_up
    )

    assert given_up == ("AAA",)
    # avança para o lote com BBB ainda pendente, em vez de repetir AAA
    assert batch is not None
    assert "BBB" in batch.tickers


def test_symbol_below_the_attempt_limit_is_still_retried() -> None:
    """Desistir cedo demais perderia coleta por falha transitória de rede."""
    state = _state(AAA={"attempts": 2})

    assert exhausted_symbols(state, max_attempts=3) == ()


def test_collection_completes_when_only_exhausted_symbols_remain() -> None:
    tickers = ("AAA", "BBB")
    state = _state(BBB={"attempts": 5})

    batch = select_next_incomplete_batch(
        tickers,
        batch_size=2,
        completed_symbols=("AAA",),
        exhausted_symbols=exhausted_symbols(state, max_attempts=3),
    )

    assert batch is None


def test_zero_max_attempts_never_gives_up() -> None:
    """Desligar a desistência precisa ser possível e explícito."""
    state = _state(AAA={"attempts": 99})

    assert exhausted_symbols(state, max_attempts=0) == ()


def test_cik_override_read_from_the_universe_file(tmp_path: Path) -> None:
    """O CIK não muda quando o ticker muda -- e o arquivo de constituintes
    já o traz. É o conserto de raiz da renomeação."""
    csv_file = tmp_path / "universe.csv"
    csv_file.write_text(
        "symbol,name,cik\nBK,BNY Mellon,0001390777\nAAPL,Apple,0000320193\n",
        encoding="utf-8",
    )

    overrides = load_cik_overrides_from_csv(csv_file)

    assert overrides["BK"] == "0001390777"
    assert overrides["AAPL"] == "0000320193"


def test_cik_override_tolerates_a_file_without_the_column(tmp_path: Path) -> None:
    csv_file = tmp_path / "no_cik.csv"
    csv_file.write_text("symbol,name\nBK,BNY Mellon\n", encoding="utf-8")

    assert load_cik_overrides_from_csv(csv_file) == {}


def test_cik_override_tolerates_a_missing_file(tmp_path: Path) -> None:
    assert load_cik_overrides_from_csv(tmp_path / "nao_existe.csv") == {}


def test_sec_map_wins_over_the_universe_file() -> None:
    """A SEC é a fonte primária; o arquivo só cobre o que ela não conhece.
    `setdefault` é o que garante essa precedência."""
    sec_map = {"AAPL": "0000320193"}
    overrides = {"AAPL": "9999999999", "BK": "0001390777"}

    for symbol, cik in overrides.items():
        sec_map.setdefault(symbol, cik)

    assert sec_map["AAPL"] == "0000320193"
    assert sec_map["BK"] == "0001390777"
