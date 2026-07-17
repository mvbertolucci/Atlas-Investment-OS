from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.feature_audit import (
    audit_coverage,
    format_coverage_report,
    phantom_weight_summary,
)
from analytics.mapper import normalize_columns
from ranking import (
    RankingReport,
    load_ranking_policy,
    rank_companies,
    write_ranking_report,
)
from scoring.investment import load_yaml, score_dataframe
from scoring.reference import ScoringReference, load_scoring_reference
from universe import (
    UniverseReport,
    evaluate_universe,
    load_universe_policy,
    write_universe_report,
)


Settings = dict[str, Any]


@dataclass(frozen=True)
class ScoringApplicationService:
    root: Path
    config: Path
    universe_report_file: Path
    ranking_report_file: Path
    logger: logging.Logger

    def load_official_reference(
        self, settings: Settings
    ) -> ScoringReference | None:
        reference_path = self.root / settings.get(
            "scoring_reference_path",
            "output/dados/scoring_reference_market.json",
        )
        if not reference_path.exists():
            self.logger.warning(
                "Referência oficial de scoring ausente em %s; usando o lote "
                "corrente com metadado CURRENT_BATCH.",
                reference_path,
            )
            return None
        try:
            reference = load_scoring_reference(reference_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.logger.warning(
                "Referência oficial inválida em %s (%s); usando o lote "
                "corrente.",
                reference_path,
                exc,
            )
            return None

        expected_universe = str(
            settings.get(
                "scoring_reference_universe_id", "US_MARKET_ELIGIBLE"
            )
        ).strip()
        current_model_version = str(
            load_yaml(self.config / "model.yaml").get(
                "model_version", "legacy"
            )
        ).strip()
        if reference.universe_id != expected_universe:
            self.logger.warning(
                "Referência %s usa universe_id=%s, esperado=%s; usando o "
                "lote corrente.",
                reference_path,
                reference.universe_id,
                expected_universe,
            )
            return None
        if reference.model_version != current_model_version:
            self.logger.warning(
                "Referência %s usa model_version=%s, modelo atual=%s; "
                "usando o lote corrente.",
                reference_path,
                reference.model_version,
                current_model_version,
            )
            return None
        self.logger.info(
            "Referência oficial carregada: %s, data=%s, n=%s, versão=%s.",
            reference.universe_id,
            reference.reference_date,
            reference.reference_count,
            reference.reference_version,
        )
        return reference

    def build_scores(
        self,
        frame: pd.DataFrame,
        scoring_reference: ScoringReference | None = None,
    ) -> pd.DataFrame:
        self.logger.info("Iniciando normalização e scoring.")
        result = normalize_columns(frame)
        result = score_dataframe(
            result,
            self.config / "model.yaml",
            self.config / "deal_breakers.json",
            scoring_reference=scoring_reference,
        )
        self.logger.info("Scoring concluído para %s empresas.", len(result))
        return result

    def audit_feature_coverage(
        self, frame: pd.DataFrame
    ) -> dict[str, Any]:
        coverage = audit_coverage(
            frame,
            self.config / "features.yaml",
            self.config / "model.yaml",
        )
        summary = phantom_weight_summary(coverage)
        print()
        print(format_coverage_report(coverage, summary))
        phantom_share = summary["phantom_investment_share"]
        if phantom_share > 0:
            self.logger.warning(
                "Peso fantasma no Investment Score: %.1f%% "
                "(features sempre neutras por falta de dados).",
                phantom_share,
            )
        return summary

    def generate_universe_report(
        self, frame: pd.DataFrame, settings: Settings
    ) -> UniverseReport | None:
        if not settings.get("universe_enabled", True):
            self.logger.info("Market Universe desabilitado.")
            return None
        policy_path = self.root / settings.get(
            "universe_policy_path", "config/universe.yaml"
        )
        policy = load_universe_policy(policy_path)
        report = evaluate_universe(frame, policy)
        write_universe_report(report, self.universe_report_file)
        self.logger.info(
            "Market Universe: %s elegíveis de %s; cobertura média %s%%.",
            report.eligible_count,
            report.total_count,
            report.average_data_coverage_pct,
        )
        return report

    def generate_ranking_report(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        universe_report: UniverseReport | None,
    ) -> RankingReport | None:
        if not settings.get("ranking_enabled", True):
            self.logger.info("Analytical Ranking desabilitado.")
            return None
        if universe_report is None:
            self.logger.warning(
                "Analytical Ranking ignorado: Universe Report indisponível."
            )
            return None
        policy_path = self.root / settings.get(
            "ranking_policy_path", "config/ranking.yaml"
        )
        policy = load_ranking_policy(policy_path)
        report = rank_companies(frame, universe_report, policy)
        write_ranking_report(report, self.ranking_report_file)
        self.logger.info(
            "Analytical Ranking: %s candidatos de %s empresas.",
            report.candidate_count,
            report.total_count,
        )
        return report
