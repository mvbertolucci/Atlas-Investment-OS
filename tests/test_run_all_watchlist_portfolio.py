"""
Tests for merge_watchlist_with_portfolio: the manually-curated research
watchlist (config/watchlist.csv) and the real portfolio (config/portfolio.csv)
are distinct sources -- neither overwrites the other on disk -- but the
sell-only rebalance engine needs a CompanyReport for every real holding, so
the analysis universe collected/scored for one run must include both.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import run_all


def _watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "ADBE", "name": "Adobe"},
            {"symbol": "MSFT", "name": "Microsoft"},
        ]
    )


def _write_portfolio_csv(path: Path, rows: str) -> Path:
    path.write_text(
        "symbol,quantity,average_price,current_price,currency,sector,country,notes\n"
        + rows,
        encoding="utf-8",
    )
    return path


def test_merge_adds_portfolio_symbols_not_already_in_watchlist(
    tmp_path: Path,
) -> None:
    portfolio_path = _write_portfolio_csv(
        tmp_path / "portfolio.csv",
        "MSFT,10,100,110,USD,Technology,USA,\n"
        "LMT,5,300,320,USD,Industrials,USA,\n",
    )
    settings = {"portfolio_path": str(portfolio_path)}

    result = run_all.merge_watchlist_with_portfolio(_watchlist(), settings)

    assert sorted(result["symbol"]) == ["ADBE", "LMT", "MSFT"]
    # MSFT was already in the watchlist -- must not appear twice.
    assert list(result["symbol"]).count("MSFT") == 1


def test_merge_does_not_write_back_to_watchlist_csv(tmp_path: Path) -> None:
    portfolio_path = _write_portfolio_csv(
        tmp_path / "portfolio.csv", "LMT,5,300,320,USD,Industrials,USA,\n"
    )
    watchlist_path = tmp_path / "watchlist.csv"
    watchlist = _watchlist()
    watchlist.to_csv(watchlist_path, index=False)

    run_all.merge_watchlist_with_portfolio(
        watchlist, {"portfolio_path": str(portfolio_path)}
    )

    on_disk = pd.read_csv(watchlist_path)
    assert sorted(on_disk["symbol"]) == ["ADBE", "MSFT"]


def test_merge_returns_watchlist_unchanged_without_a_portfolio_file(
    tmp_path: Path,
) -> None:
    settings = {"portfolio_path": str(tmp_path / "does_not_exist.csv")}
    watchlist = _watchlist()

    result = run_all.merge_watchlist_with_portfolio(watchlist, settings)

    assert result is watchlist


def test_merge_degrades_gracefully_on_an_unreadable_portfolio_file(
    tmp_path: Path,
) -> None:
    portfolio_path = tmp_path / "portfolio.csv"
    portfolio_path.write_text("not,a,valid,portfolio,schema\n1,2,3,4,5\n", encoding="utf-8")
    settings = {"portfolio_path": str(portfolio_path)}
    watchlist = _watchlist()

    result = run_all.merge_watchlist_with_portfolio(watchlist, settings)

    assert result is watchlist


def test_merge_with_no_new_symbols_returns_the_same_frame(tmp_path: Path) -> None:
    portfolio_path = _write_portfolio_csv(
        tmp_path / "portfolio.csv", "MSFT,10,100,110,USD,Technology,USA,\n"
    )
    watchlist = _watchlist()

    result = run_all.merge_watchlist_with_portfolio(
        watchlist, {"portfolio_path": str(portfolio_path)}
    )

    assert result is watchlist
