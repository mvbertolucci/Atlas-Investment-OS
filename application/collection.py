from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from analytics.fundamentals import compute_fundamentals
from analytics.indicators import enrich_technicals
from portfolio.exceptions import PortfolioError
from portfolio.loader import load_portfolio_csv
from providers.contracts import ProviderPolicy
from providers.evidence import apply_sector_applicability, ensure_field_evidence
from providers.finnhub import build_finnhub_secondary_provider
from providers.fmp import build_fmp_secondary_provider
from providers.massive import build_massive_secondary_provider
from providers.sec_companyfacts import build_sec_secondary_provider
from providers.yahoo import fetch_watchlist
from storage.raw_snapshots import resolve_raw_snapshot_path


Settings = dict[str, Any]

ORIGIN_PORTFOLIO = "portfolio"
ORIGIN_WATCHLIST = "watchlist"
ORIGIN_UNIVERSE = "universe"
ORIGIN_PRIORITY = (ORIGIN_PORTFOLIO, ORIGIN_WATCHLIST, ORIGIN_UNIVERSE)


@dataclass(frozen=True)
class CollectionApplicationService:
    root: Path
    config: Path
    logger: logging.Logger

    def load_watchlist(
        self, settings: Settings
    ) -> tuple[Path, pd.DataFrame]:
        watchlist_path = self.root / settings.get(
            "watchlist_path",
            "config/watchlist.csv",
        )
        if not watchlist_path.exists():
            raise FileNotFoundError(
                f"Watchlist não encontrada: {watchlist_path}"
            )

        watchlist = pd.read_csv(watchlist_path)
        if watchlist.empty:
            raise RuntimeError(f"A watchlist está vazia: {watchlist_path}")
        return watchlist_path, watchlist

    def merge_watchlist_with_portfolio(
        self,
        watchlist: pd.DataFrame,
        settings: Settings,
    ) -> pd.DataFrame:
        """Une watchlist e carteira apenas em memória, preservando origem."""
        result = watchlist.copy()
        if "origin" not in result.columns:
            result["origin"] = ORIGIN_WATCHLIST

        portfolio_path = self.root / settings.get(
            "portfolio_path",
            "config/portfolio.csv",
        )
        if not portfolio_path.exists():
            return result

        try:
            portfolio = load_portfolio_csv(portfolio_path)
        except PortfolioError:
            self.logger.warning(
                "Não foi possível ler %s para incluir a carteira no universo "
                "analisado; seguindo apenas com a watchlist.",
                portfolio_path,
            )
            return result

        portfolio_symbols = {
            holding.symbol for holding in portfolio.holdings
        }
        existing_symbols = (
            result["symbol"].astype(str).str.strip().str.upper()
        )
        result.loc[
            existing_symbols.isin(portfolio_symbols), "origin"
        ] = ORIGIN_PORTFOLIO

        already_present = set(existing_symbols)
        extra_rows = [
            {
                "symbol": holding.symbol,
                "name": holding.symbol,
                "origin": ORIGIN_PORTFOLIO,
            }
            for holding in portfolio.holdings
            if holding.symbol not in already_present
        ]
        if not extra_rows:
            return result
        return pd.concat(
            [result, pd.DataFrame(extra_rows)],
            ignore_index=True,
        )

    def collect_market_data(
        self,
        settings: Settings,
        watchlist: pd.DataFrame,
        *,
        failures: list[str] | None = None,
    ) -> pd.DataFrame:
        self.logger.info(
            "Iniciando coleta de dados para %s empresas.", len(watchlist)
        )
        origin_by_symbol = (
            {
                str(symbol).strip().upper(): origin
                for symbol, origin in zip(
                    watchlist.get("symbol", []),
                    watchlist.get("origin", []),
                )
            }
            if "origin" in watchlist.columns
            else {}
        )

        secondary_fetcher = build_sec_secondary_provider(self.root, settings)
        fmp_fetcher = build_fmp_secondary_provider(self.root, settings)
        if fmp_fetcher is not None and bool(
            settings.get("fmp_automatic_prefetch_enabled", False)
        ):
            prefetch_summary = fmp_fetcher.prefetch(
                watchlist.get("symbol", pd.Series(dtype=str)).tolist()
            )
            if prefetch_summary.get("mode") == "batch_cache":
                self.logger.info(
                    "FMP batch/cache: requested=%s, market=%s, float=%s, "
                    "enterprise=%s, quota=%s/%s, missing=%s/%s/%s.",
                    prefetch_summary.get("requested"),
                    prefetch_summary.get("market_cached"),
                    prefetch_summary.get("float_cached"),
                    prefetch_summary.get("enterprise_cached"),
                    prefetch_summary.get("quota_used_after"),
                    settings.get("fmp_daily_call_limit", 250),
                    prefetch_summary.get("market_missing"),
                    prefetch_summary.get("float_missing"),
                    prefetch_summary.get("enterprise_missing"),
                )
                if prefetch_summary.get("errors"):
                    self.logger.warning(
                        "FMP batch/cache registrou %s erros explícitos.",
                        prefetch_summary.get(
                            "error_count",
                            len(prefetch_summary["errors"]),
                        ),
                    )
        massive_fetcher = build_massive_secondary_provider(
            self.root,
            settings,
            float_fetcher=(
                fmp_fetcher.fetch_float if fmp_fetcher is not None else None
            ),
            fundamentals_fetcher=secondary_fetcher,
        )
        finnhub_fetcher = build_finnhub_secondary_provider(self.root, settings)
        if (
            bool(settings.get("finnhub_secondary_enabled", False))
            and finnhub_fetcher is None
        ):
            self.logger.warning(
                "Segunda fonte Finnhub habilitada, mas finnhub_api_key não "
                "foi encontrada em %s ou FINNHUB_API_KEY.",
                settings.get(
                    "provider_secrets_path",
                    "config/provider_secrets.json",
                ),
            )
        if (
            bool(settings.get("sec_secondary_enabled", False))
            and secondary_fetcher is None
        ):
            self.logger.warning(
                "Segunda fonte SEC habilitada, mas sec_user_agent não foi "
                "encontrado em %s.",
                settings.get(
                    "provider_secrets_path",
                    "config/provider_secrets.json",
                ),
            )
        if (
            bool(settings.get("fmp_secondary_enabled", False))
            and fmp_fetcher is None
        ):
            self.logger.warning(
                "Segunda fonte FMP habilitada, mas fmp_api_key não foi "
                "encontrada em %s ou FMP_API_KEY.",
                settings.get(
                    "provider_secrets_path",
                    "config/provider_secrets.json",
                ),
            )
        if (
            bool(settings.get("massive_secondary_enabled", False))
            and massive_fetcher is None
        ):
            self.logger.warning(
                "Segunda fonte Massive habilitada, mas massive_api_key não "
                "foi encontrada em %s ou MASSIVE_API_KEY.",
                settings.get(
                    "provider_secrets_path",
                    "config/provider_secrets.json",
                ),
            )

        rows = fetch_watchlist(
            watchlist,
            period=settings.get("history_period", "2y"),
            interval=settings.get("history_interval", "1d"),
            failures=failures,
            provider_policy=ProviderPolicy(
                timeout_seconds=float(
                    settings.get("provider_timeout_seconds", 30)
                ),
                max_retries=int(settings.get("provider_max_retries", 2)),
                backoff_seconds=float(
                    settings.get("provider_backoff_seconds", 0.5)
                ),
                rate_limit_per_second=float(
                    settings.get("provider_rate_limit_per_second", 2)
                ),
            ),
            raw_snapshot_dir=resolve_raw_snapshot_path(
                self.root,
                settings.get("raw_snapshot_path", "data/raw_snapshots"),
            ),
            secondary_fetcher=secondary_fetcher,
            secondary_fetchers=tuple(
                fetcher
                for fetcher in (
                    finnhub_fetcher,
                    massive_fetcher,
                    fmp_fetcher,
                )
                if fetcher is not None
            ),
            critical_fields=tuple(
                settings.get(
                    "provider_critical_fields",
                    (
                        # market_cap/enterprise_value/short_float are
                        # deliberately absent (ADR-038) -- see
                        # providers/yahoo.py::DEFAULT_CRITICAL_FIELDS
                        "total_debt",
                        "total_cash",
                        "ebitda",
                        "free_cashflow",
                        "current_ratio",
                        "roe",
                    ),
                )
            ),
        )

        for row in rows:
            symbol = str(row.get("symbol", "")).strip().upper()
            row["origin"] = origin_by_symbol.get(symbol, ORIGIN_WATCHLIST)

        quality_policy = yaml.safe_load(
            (self.config / "data_quality.yaml").read_text(encoding="utf-8")
        ) or {}
        enriched = []
        for row in rows:
            prepared = compute_fundamentals(enrich_technicals(row))
            ensure_field_evidence(prepared)
            enriched.append(
                apply_sector_applicability(prepared, quality_policy)
            )

        frame = pd.DataFrame(
            [
                {
                    key: value
                    for key, value in row.items()
                    if key != "history"
                }
                for row in enriched
            ]
        )
        if frame.empty:
            raise RuntimeError(
                "Nenhum dado foi coletado. "
                "Verifique a watchlist ou a conexão."
            )

        self.logger.info(
            "Coleta concluída: %s empresas retornadas.", len(frame)
        )
        return frame
