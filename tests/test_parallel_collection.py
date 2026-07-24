"""
Trava as invariantes da coleta paralela.

Paralelizar a coleta reduz latência (cada símbolo custa ~6 requisições HTTP
sequenciais ao Yahoo), mas não pode afrouxar nada do que já era garantido:
o teto global de chamadas por segundo, a ordem determinística das linhas e a
associação símbolo -> falha.
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import pytest

import providers.yahoo as yahoo
from providers.contracts import ProviderPolicy


def _watchlist(count: int) -> pd.DataFrame:
    symbols = [f"S{index:02d}" for index in range(count)]
    return pd.DataFrame({"symbol": symbols, "name": symbols})


def _fake_fetch(delay: float, starts: list[float], lock: threading.Lock):
    def fetch(symbol, name, period="2y", interval="1d"):
        with lock:
            starts.append(time.monotonic())
        time.sleep(delay)
        return {
            "symbol": symbol,
            "as_of": "2026-07-24T00:00:00",
            "field_evidence": {},
        }

    return fetch


def test_parallel_collection_preserves_row_order(monkeypatch) -> None:
    starts: list[float] = []
    monkeypatch.setattr(
        yahoo, "fetch_symbol", _fake_fetch(0.02, starts, threading.Lock())
    )
    frame = _watchlist(8)
    rows = yahoo.fetch_watchlist(
        frame,
        provider_policy=ProviderPolicy(rate_limit_per_second=1000),
        max_workers=4,
    )
    assert [row["symbol"] for row in rows] == list(frame["symbol"])


def test_parallel_collection_respects_the_global_rate_limit(monkeypatch) -> None:
    """O limite é do conjunto, não por thread -- senão 4 workers = 4x o teto."""
    starts: list[float] = []
    monkeypatch.setattr(
        yahoo, "fetch_symbol", _fake_fetch(0.01, starts, threading.Lock())
    )
    yahoo.fetch_watchlist(
        _watchlist(5),
        # Intervalo de 0.2s: bem acima da granularidade do timer do Windows
        # (~15ms), senão o teste fica instável quando a máquina está carregada.
        provider_policy=ProviderPolicy(rate_limit_per_second=5),
        max_workers=4,
    )
    ordered = sorted(starts)
    gaps = [after - before for before, after in zip(ordered, ordered[1:])]
    assert min(gaps) >= 0.15


def test_failures_keep_symbol_association_and_order(monkeypatch) -> None:
    def fetch(symbol, name, period="2y", interval="1d"):
        if symbol in {"S01", "S03"}:
            raise RuntimeError("falha simulada")
        return {
            "symbol": symbol,
            "as_of": "2026-07-24T00:00:00",
            "field_evidence": {},
        }

    monkeypatch.setattr(yahoo, "fetch_symbol", fetch)
    failures: list[str] = []
    rows = yahoo.fetch_watchlist(
        _watchlist(5),
        provider_policy=ProviderPolicy(rate_limit_per_second=1000),
        max_workers=4,
        failures=failures,
    )
    assert [row["symbol"] for row in rows] == ["S00", "S02", "S04"]
    assert [failure.split(":")[0] for failure in failures] == ["S01", "S03"]


def test_sequential_and_parallel_produce_the_same_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        yahoo, "fetch_symbol", _fake_fetch(0.0, [], threading.Lock())
    )
    frame = _watchlist(6)
    policy = ProviderPolicy(rate_limit_per_second=1000)
    sequential = yahoo.fetch_watchlist(frame, provider_policy=policy, max_workers=1)
    parallel = yahoo.fetch_watchlist(frame, provider_policy=policy, max_workers=4)
    assert [r["symbol"] for r in sequential] == [r["symbol"] for r in parallel]


def test_parallel_is_faster_when_latency_dominates(monkeypatch) -> None:
    """Com trabalho acima do intervalo do rate limit, paralelizar compensa."""
    monkeypatch.setattr(
        yahoo, "fetch_symbol", _fake_fetch(0.20, [], threading.Lock())
    )
    frame = _watchlist(6)
    policy = ProviderPolicy(rate_limit_per_second=50)

    start = time.monotonic()
    yahoo.fetch_watchlist(frame, provider_policy=policy, max_workers=1)
    sequential = time.monotonic() - start

    start = time.monotonic()
    yahoo.fetch_watchlist(frame, provider_policy=policy, max_workers=4)
    parallel = time.monotonic() - start

    assert parallel < sequential / 2
