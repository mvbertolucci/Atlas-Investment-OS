from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_dict(value: Any) -> dict:
    if value is None:
        return {}

    if is_dataclass(value):
        return asdict(value)

    if hasattr(value, "to_dict"):
        try:
            result = value.to_dict()
            if isinstance(result, dict):
                return result
        except Exception:
            return {}

    if isinstance(value, dict):
        return value

    return {}


def _score_summary(df: pd.DataFrame, column: str) -> dict:
    if column not in df.columns:
        return {
            "available": False,
            "count": 0,
            "average": None,
            "minimum": None,
            "maximum": None,
        }

    values = pd.to_numeric(df[column], errors="coerce").dropna()

    if values.empty:
        return {
            "available": True,
            "count": 0,
            "average": None,
            "minimum": None,
            "maximum": None,
        }

    return {
        "available": True,
        "count": int(values.count()),
        "average": round(float(values.mean()), 2),
        "minimum": round(float(values.min()), 2),
        "maximum": round(float(values.max()), 2),
    }


def build_performance_validation_report(
    df: pd.DataFrame,
    *,
    portfolio_report: Any = None,
    outcome_report: Any = None,
    portfolio_validation_report: Mapping[str, Any] | None = None,
    snapshot_date: str | None = None,
) -> dict:
    """
    Publica o primeiro contrato de validação de performance do Atlas.

    Esta versão é propositalmente conservadora: ela NÃO afirma backtest,
    alfa, CAGR, Sharpe ou drawdown se esses dados ainda não foram calculados
    com histórico real. O objetivo é criar o artefato governado que será
    preenchido progressivamente conforme a validação de performance evoluir.

    Só lê o que os motores já produziram nesta run -- distribuição dos scores
    já calculados (`scoring/investment.py`), o resumo de qualidade da carteira
    (`portfolio/report.py::build_portfolio_report`) e o hit rate de outcomes
    (`outcomes/analytics.py`). Nenhum número novo é calculado aqui; campos
    ausentes viram `None`/`False`, nunca inventados.
    """

    portfolio_data = _safe_dict(portfolio_report)
    outcome_data = _safe_dict(outcome_report)
    historical_data = _safe_dict(portfolio_validation_report)

    portfolio_summary = portfolio_data.get("summary", {})
    allocation = portfolio_data.get("allocation", {})

    hit_rate = outcome_data.get("hit_rate", {})
    if not isinstance(hit_rate, dict):
        hit_rate = _safe_dict(hit_rate)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot_date": snapshot_date,
        "status": "validation_contract_initialized",
        "important_note": (
            "This report initializes the governed performance-validation "
            "contract. It does not yet claim realized portfolio alpha, CAGR, "
            "Sharpe ratio or max drawdown unless those metrics are explicitly "
            "available from validated historical performance data."
        ),
        "coverage": {
            "companies_analyzed": int(len(df)),
            "portfolio_report_available": portfolio_report is not None,
            "outcome_report_available": outcome_report is not None,
        },
        "current_score_distribution": {
            "investment_score": _score_summary(df, "Investment Score"),
            "opportunity_score": _score_summary(df, "Opportunity Score"),
            "conviction_score": _score_summary(df, "Conviction Score"),
            "business_score": _score_summary(df, "Business Score"),
            "valuation_score": _score_summary(df, "Valuation Score"),
            "financial_score": _score_summary(df, "Financial Score"),
            "timing_score": _score_summary(df, "Timing Score"),
            "risk_penalty": _score_summary(df, "Risk Penalty"),
        },
        "portfolio_quality": {
            "quality_score": _safe_float(portfolio_summary.get("quality_score")),
            "quality_rating": portfolio_summary.get("quality_rating"),
            "total_positions": portfolio_summary.get("holdings_count"),
            "currency": portfolio_summary.get("currency"),
            "allocation_by_symbol_available": bool(
                allocation.get("by_symbol")
            )
            if isinstance(allocation, dict)
            else False,
        },
        "outcome_validation": {
            "eligible_count": hit_rate.get("eligible_count"),
            "hit_count": hit_rate.get("hit_count"),
            "hit_rate": hit_rate.get("hit_rate"),
        },
        "historical_validation": _historical_validation_summary(
            historical_data
        ),
        "open_items": [
            "Add realized portfolio return series.",
            "Add benchmark comparison.",
            "Add CAGR.",
            "Add volatility.",
            "Add Sharpe ratio.",
            "Add maximum drawdown.",
            "Add factor contribution to realized return.",
        ],
    }


def _historical_validation_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Expose the validated historical contract without recalculating it."""
    if not report:
        return {
            "available": False,
            "status": "not_available",
            "summary": None,
            "periods": 0,
            "incomplete_periods": 0,
            "return_sources": [],
        }

    periods = report.get("periods", [])
    incomplete_periods = report.get("incomplete_periods", [])
    summary = report.get("summary")
    period_count = len(periods) if isinstance(periods, list) else 0
    incomplete_count = (
        len(incomplete_periods) if isinstance(incomplete_periods, list) else 0
    )
    return {
        "available": True,
        "status": report.get("status", "unknown"),
        "summary": summary if isinstance(summary, dict) else None,
        "periods": period_count,
        "incomplete_periods": incomplete_count,
        "return_sources": report.get("return_sources", []),
        "assessment": _historical_assessment(
            report, period_count, incomplete_count
        ),
    }


def _historical_assessment(
    report: dict[str, Any],
    period_count: int,
    incomplete_count: int,
) -> dict[str, Any]:
    summary = report.get("summary")
    if report.get("status") != "complete" or not isinstance(summary, dict):
        return {
            "status": "INCONCLUSIVE",
            "reasons": ["VALIDATION_INCOMPLETE"],
        }
    if incomplete_count or period_count < 12:
        reasons = []
        if incomplete_count:
            reasons.append("INCOMPLETE_PERIODS")
        if period_count < 12:
            reasons.append("SAMPLE_BELOW_12_PERIODS")
        return {"status": "INCONCLUSIVE", "reasons": reasons}

    excess = summary.get("annualized_excess_return")
    if isinstance(excess, (int, float)) and excess > 0:
        return {"status": "PASS", "reasons": ["OUTPERFORMS_BENCHMARK"]}
    return {"status": "FAIL", "reasons": ["UNDERPERFORMS_BENCHMARK"]}


def write_performance_validation_report(
    report: dict,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path
