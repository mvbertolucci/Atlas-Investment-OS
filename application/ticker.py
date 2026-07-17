from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd

from portfolio.exceptions import PortfolioError
from portfolio.models import Portfolio
from reports.atlas_report.one_pager import (
    compute_symbol_contributions,
    render_one_pager,
)
from reports.atlas_report.render import page_shell
from reports.atlas_report.write import write_one_pager
from scoring.reference import ScoringReference


Settings = dict[str, Any]
OutputWriter = Callable[[str], None]


class CollectionPort(Protocol):
    def collect_market_data(
        self,
        settings: Settings,
        analysis_universe: pd.DataFrame,
        *,
        failures: list[str] | None = None,
    ) -> pd.DataFrame: ...


class ScoringPort(Protocol):
    def load_official_reference(
        self, settings: Settings
    ) -> ScoringReference | None: ...

    def build_scores(
        self,
        frame: pd.DataFrame,
        scoring_reference: ScoringReference | None = None,
    ) -> pd.DataFrame: ...


class HistoryPort(Protocol):
    def load_score_history(self, path: Path | None = None) -> pd.DataFrame: ...

    def portfolio_path(self, settings: Settings) -> Path: ...

    def load_portfolio(self, path: Path) -> Portfolio: ...


@dataclass(frozen=True)
class TickerAnalysisApplicationService:
    config: Path
    output_reports: Path
    collection: CollectionPort
    scoring: ScoringPort
    history: HistoryPort
    logger: logging.Logger
    output_writer: OutputWriter = print

    def run_ticker_mode(self, symbol: str, settings: Settings) -> Path:
        """Analyze one symbol against the governed broad-market reference."""
        symbol = symbol.strip().upper()
        self.logger.info(
            "Modo --ticker: analisando %s contra a referência ampla.", symbol
        )
        scoring_reference = self.scoring.load_official_reference(settings)
        analysis_universe = pd.DataFrame(
            [{"symbol": symbol, "name": symbol, "origin": "ticker"}]
        )
        frame = self.collection.collect_market_data(
            settings, analysis_universe
        )
        frame = self.scoring.build_scores(frame, scoring_reference)

        symbol_rows = frame.index[
            frame["symbol"].astype(str).str.strip().str.upper() == symbol
        ]
        if len(symbol_rows) == 0:
            raise RuntimeError(
                f"Não foi possível coletar dados de mercado para {symbol}."
            )
        position = symbol_rows[0]

        investment_score = None
        if "Investment Score" in frame.columns:
            try:
                investment_score = float(
                    frame.loc[position, "Investment Score"]
                )
            except (TypeError, ValueError):
                investment_score = None

        positive, negative = compute_symbol_contributions(
            frame,
            symbol,
            self.config / "features.yaml",
            self.config / "model.yaml",
        )

        score_history = self.history.load_score_history()
        if not score_history.empty and "symbol" in score_history.columns:
            score_history = score_history.loc[
                score_history["symbol"].astype(str).str.upper() == symbol
            ]

        thesis = ""
        portfolio_path = self.history.portfolio_path(settings)
        if portfolio_path.exists():
            try:
                holding = self.history.load_portfolio(portfolio_path).holding(
                    symbol
                )
                if holding is not None:
                    thesis = holding.thesis
            except PortfolioError:
                self.logger.warning(
                    "Não foi possível ler %s para buscar a tese de %s.",
                    portfolio_path,
                    symbol,
                )

        company_name = (
            str(frame.loc[position].get("name", "") or "").strip() or symbol
        )
        body = render_one_pager(
            symbol=symbol,
            company_name=company_name,
            investment_score=investment_score,
            positive=positive,
            negative=negative,
            score_history=score_history,
            thesis=thesis,
        )
        html = page_shell(f"Atlas One-Pager — {symbol}", body)

        date_stamp = datetime.now().isoformat(timespec="seconds").replace(
            ":", "-"
        )
        path = write_one_pager(
            html, self.output_reports, symbol, date_stamp
        )
        self.output_writer(f"One-pager de {symbol} gerado em {path}")
        self.logger.info("One-pager de %s gerado em %s.", symbol, path)
        return path
