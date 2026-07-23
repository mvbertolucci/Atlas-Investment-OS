from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from storage.history_db import HistoryDatabase


POSITIVE_DECISIONS = frozenset(
    {"STRONG_BUY", "BUY", "ACCUMULATE"}
)
NEGATIVE_DECISIONS = frozenset({"AVOID"})
CALIBRATION_SCORES = frozenset(
    {
        "opportunity_score",
        "conviction_score",
        "business_score",
        "valuation_score",
        "financial_score",
        "timing_score",
    }
)
FACTOR_SCORES = (
    "business_score",
    "valuation_score",
    "financial_score",
    "timing_score",
)


@dataclass(frozen=True)
class HitRateReport:
    eligible_count: int
    hit_count: int
    miss_count: int
    excluded_count: int
    hit_rate: float | None
    threshold_pct: float
    by_horizon: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible_count": self.eligible_count,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "excluded_count": self.excluded_count,
            "hit_rate": self.hit_rate,
            "threshold_pct": self.threshold_pct,
            "by_horizon": [dict(row) for row in self.by_horizon],
        }


@dataclass(frozen=True)
class OutcomeAnalyticsReport:
    hit_rate: HitRateReport
    opportunity_calibration: tuple[dict[str, Any], ...]
    conviction_calibration: tuple[dict[str, Any], ...]
    factor_attribution: tuple[dict[str, Any], ...]
    decision_attribution: tuple[dict[str, Any], ...]
    deal_breaker_attribution: tuple[dict[str, Any], ...]
    # Aditivo (default = ()): descreve a estabilidade da watchlist entre datas
    # de decisão. Não altera nenhum campo existente do contrato JSON.
    watchlist_drift: tuple[dict[str, Any], ...] = ()
    evaluated_outcomes: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit_rate": self.hit_rate.to_dict(),
            "opportunity_calibration": [
                dict(row)
                for row in self.opportunity_calibration
            ],
            "conviction_calibration": [
                dict(row)
                for row in self.conviction_calibration
            ],
            "factor_attribution": [
                dict(row)
                for row in self.factor_attribution
            ],
            "decision_attribution": [
                dict(row)
                for row in self.decision_attribution
            ],
            "deal_breaker_attribution": [
                dict(row)
                for row in self.deal_breaker_attribution
            ],
            "watchlist_drift": [
                dict(row)
                for row in self.watchlist_drift
            ],
            "evaluated_outcomes": [
                dict(row)
                for row in self.evaluated_outcomes
            ],
        }


def build_outcome_dataset(
    database: HistoryDatabase,
) -> pd.DataFrame:
    if not isinstance(database, HistoryDatabase):
        raise TypeError(
            "database deve ser HistoryDatabase."
        )

    snapshots = database.load_outcome_snapshots()
    results = database.load_outcome_results()

    if snapshots.empty or results.empty:
        return pd.DataFrame()

    return results.merge(
        snapshots,
        on=["decision_date", "symbol"],
        how="inner",
        suffixes=("", "_snapshot"),
        validate="many_to_one",
    )


def _expected_direction(decision: Any) -> int | None:
    normalized = str(decision).strip().upper()
    if normalized in POSITIVE_DECISIONS:
        return 1
    if normalized in NEGATIVE_DECISIONS:
        return -1
    return None


def calculate_hit_rate(
    dataset: pd.DataFrame,
    *,
    threshold_pct: float = 0.0,
) -> HitRateReport:
    try:
        threshold = float(threshold_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "threshold_pct deve ser numérico e não negativo."
        ) from exc

    if threshold != threshold or threshold < 0:
        raise ValueError(
            "threshold_pct deve ser numérico e não negativo."
        )

    if dataset.empty:
        return HitRateReport(
            eligible_count=0,
            hit_count=0,
            miss_count=0,
            excluded_count=0,
            hit_rate=None,
            threshold_pct=threshold,
            by_horizon=(),
        )

    required = {"decision", "return_pct", "horizon_days"}
    missing = required.difference(dataset.columns)
    if missing:
        raise ValueError(
            "Dataset sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    frame = dataset.copy()
    frame["expected_direction"] = frame["decision"].map(
        _expected_direction
    )
    frame["return_pct"] = pd.to_numeric(
        frame["return_pct"],
        errors="coerce",
    )
    eligible = frame.loc[
        frame["expected_direction"].notna()
        & frame["return_pct"].notna()
    ].copy()
    eligible["directional_return_pct"] = (
        eligible["return_pct"]
        * eligible["expected_direction"].astype(float)
    )
    eligible["is_hit"] = (
        eligible["directional_return_pct"] > threshold
    )

    hit_count = int(eligible["is_hit"].sum())
    eligible_count = len(eligible)
    by_horizon: list[dict[str, Any]] = []

    for horizon, group in eligible.groupby(
        "horizon_days",
        sort=True,
    ):
        group_hits = int(group["is_hit"].sum())
        count = len(group)
        by_horizon.append(
            {
                "horizon_days": int(horizon),
                "eligible_count": count,
                "hit_count": group_hits,
                "miss_count": count - group_hits,
                "hit_rate": round(
                    group_hits / count * 100,
                    2,
                ),
                "average_directional_return_pct": round(
                    float(
                        group["directional_return_pct"].mean()
                    ),
                    4,
                ),
            }
        )

    return HitRateReport(
        eligible_count=eligible_count,
        hit_count=hit_count,
        miss_count=eligible_count - hit_count,
        excluded_count=len(frame) - eligible_count,
        hit_rate=(
            round(hit_count / eligible_count * 100, 2)
            if eligible_count
            else None
        ),
        threshold_pct=threshold,
        by_horizon=tuple(by_horizon),
    )


def calculate_score_calibration(
    dataset: pd.DataFrame,
    score_column: str,
    *,
    bucket_size: int = 20,
) -> tuple[dict[str, Any], ...]:
    """
    Bucketiza um score em faixas fixas 0-100 e mede o retorno médio por faixa
    e horizonte.

    LIMITAÇÃO CONHECIDA (não é bug): os scores do Atlas são percentis
    cross-sectionais dentro da watchlist de cada execução (ver
    factors/engine.py::pct_rank e docs/SCORING_MODEL.md). Como este cálculo
    agrupa snapshots de TODAS as datas de decisão na mesma faixa, um bucket
    (ex.: [80,100)) não representa a mesma qualidade absoluta entre execuções
    quando a composição da watchlist muda. A calibração só é estritamente
    comparável com watchlist estável; caso contrário, é indicativa. Corrigir
    isto (score absoluto ou normalização por execução) muda a semântica do
    modelo e exige decisão de produto — não fazer aqui silenciosamente.
    """
    if score_column not in CALIBRATION_SCORES:
        raise ValueError(
            "score_column não é um score calibrável do Atlas."
        )

    if isinstance(bucket_size, bool):
        raise ValueError(
            "bucket_size deve ser inteiro entre 1 e 100."
        )

    try:
        size = int(bucket_size)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "bucket_size deve ser inteiro entre 1 e 100."
        ) from exc

    if size <= 0 or size > 100 or float(bucket_size) != size:
        raise ValueError(
            "bucket_size deve ser inteiro entre 1 e 100."
        )

    if dataset.empty:
        return ()

    required = {score_column, "return_pct", "horizon_days"}
    missing = required.difference(dataset.columns)
    if missing:
        raise ValueError(
            "Dataset sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    frame = dataset.copy()
    frame[score_column] = pd.to_numeric(
        frame[score_column],
        errors="coerce",
    )
    frame["return_pct"] = pd.to_numeric(
        frame["return_pct"],
        errors="coerce",
    )
    frame = frame.dropna(
        subset=[score_column, "return_pct", "horizon_days"]
    )
    frame = frame.loc[
        frame[score_column].between(0, 100)
    ].copy()

    if frame.empty:
        return ()

    frame["bucket_min"] = (
        (frame[score_column] // size) * size
    ).clip(upper=max(0, 100 - size))
    frame["bucket_max"] = (
        frame["bucket_min"] + size
    ).clip(upper=100)
    rows: list[dict[str, Any]] = []

    for (horizon, lower, upper), group in frame.groupby(
        ["horizon_days", "bucket_min", "bucket_max"],
        sort=True,
    ):
        rows.append(
            {
                "score": score_column,
                "horizon_days": int(horizon),
                "bucket_min": int(lower),
                "bucket_max": int(upper),
                "count": len(group),
                "average_score": round(
                    float(group[score_column].mean()),
                    2,
                ),
                "average_return_pct": round(
                    float(group["return_pct"].mean()),
                    4,
                ),
                "positive_return_rate": round(
                    float((group["return_pct"] > 0).mean())
                    * 100,
                    2,
                ),
            }
        )

    return tuple(rows)


def calculate_factor_attribution(
    dataset: pd.DataFrame,
    *,
    bucket_size: int = 20,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for factor in FACTOR_SCORES:
        if factor not in dataset.columns:
            continue
        rows.extend(
            calculate_score_calibration(
                dataset,
                factor,
                bucket_size=bucket_size,
            )
        )
    return tuple(rows)


def _categorical_rows(
    frame: pd.DataFrame,
    category_column: str,
) -> tuple[dict[str, Any], ...]:
    if frame.empty:
        return ()

    required = {category_column, "return_pct", "horizon_days"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "Dataset sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    data = frame.copy()
    data["return_pct"] = pd.to_numeric(
        data["return_pct"],
        errors="coerce",
    )
    data = data.dropna(
        subset=[category_column, "return_pct", "horizon_days"]
    )
    rows: list[dict[str, Any]] = []

    for (horizon, category), group in data.groupby(
        ["horizon_days", category_column],
        sort=True,
    ):
        rows.append(
            {
                "category": category_column,
                "value": str(category),
                "horizon_days": int(horizon),
                "count": len(group),
                "average_return_pct": round(
                    float(group["return_pct"].mean()),
                    4,
                ),
                "positive_return_rate": round(
                    float((group["return_pct"] > 0).mean())
                    * 100,
                    2,
                ),
            }
        )
    return tuple(rows)


def calculate_watchlist_drift(
    dataset: pd.DataFrame,
) -> tuple[dict[str, Any], ...]:
    """
    Mede a estabilidade da composição da watchlist entre datas de decisão.

    A calibração de score (calculate_score_calibration) agrupa buckets de TODAS
    as datas, assumindo que um score significa a mesma qualidade entre
    execuções. Isso só vale se o conjunto de símbolos for estável -- os scores
    do Atlas são percentis cross-sectionais dentro do lote de cada execução
    (ver docs/SCORING_MODEL.md). Esta função quantifica a suposição: para cada
    transição entre datas consecutivas retorna o Jaccard (interseção/união) e
    quantos símbolos entraram/saíram. `stable` é True quando nada mudou.

    Não altera score algum; é diagnóstico. Retorna () quando há menos de duas
    datas (nada a comparar).
    """
    if dataset.empty:
        return ()

    required = {"decision_date", "symbol"}
    missing = required.difference(dataset.columns)
    if missing:
        raise ValueError(
            "Dataset sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    frame = dataset.dropna(subset=["decision_date", "symbol"])
    dates = sorted(frame["decision_date"].unique())
    if len(dates) < 2:
        return ()

    symbols_by_date = {
        date: set(frame.loc[frame["decision_date"] == date, "symbol"])
        for date in dates
    }

    rows: list[dict[str, Any]] = []
    for previous, current in zip(dates, dates[1:]):
        before = symbols_by_date[previous]
        after = symbols_by_date[current]
        union = before | after
        intersection = before & after
        rows.append(
            {
                "from_date": str(previous),
                "to_date": str(current),
                "jaccard": (
                    round(len(intersection) / len(union), 4)
                    if union
                    else 1.0
                ),
                "added_count": len(after - before),
                "removed_count": len(before - after),
                "stable": before == after,
            }
        )
    return tuple(rows)


def calculate_decision_attribution(
    dataset: pd.DataFrame,
) -> tuple[dict[str, Any], ...]:
    return _categorical_rows(dataset, "decision")


def calculate_deal_breaker_attribution(
    dataset: pd.DataFrame,
) -> tuple[dict[str, Any], ...]:
    if dataset.empty:
        return ()
    if "deal_breakers" not in dataset.columns:
        raise ValueError(
            "Dataset sem coluna obrigatória: deal_breakers"
        )

    frame = dataset.copy()
    frame["deal_breaker"] = frame["deal_breakers"].map(
        lambda values: (
            tuple(values)
            if values
            else ("NO_DEAL_BREAKER",)
        )
    )
    frame = frame.explode("deal_breaker")
    return _categorical_rows(frame, "deal_breaker")


def build_outcome_analytics_report(
    database: HistoryDatabase,
    *,
    threshold_pct: float = 0.0,
    bucket_size: int = 20,
) -> OutcomeAnalyticsReport:
    dataset = build_outcome_dataset(database)

    watchlist_drift = calculate_watchlist_drift(dataset)
    unstable = [row for row in watchlist_drift if not row["stable"]]
    if unstable:
        logging.getLogger("atlas").warning(
            "Watchlist composition changed across %d decision-date "
            "transition(s); cross-run score calibration pools "
            "non-comparable buckets. See docs/SCORING_MODEL.md.",
            len(unstable),
        )

    return OutcomeAnalyticsReport(
        hit_rate=calculate_hit_rate(
            dataset,
            threshold_pct=threshold_pct,
        ),
        opportunity_calibration=calculate_score_calibration(
            dataset,
            "opportunity_score",
            bucket_size=bucket_size,
        ),
        conviction_calibration=calculate_score_calibration(
            dataset,
            "conviction_score",
            bucket_size=bucket_size,
        ),
        factor_attribution=calculate_factor_attribution(
            dataset,
            bucket_size=bucket_size,
        ),
        decision_attribution=calculate_decision_attribution(
            dataset,
        ),
        deal_breaker_attribution=(
            calculate_deal_breaker_attribution(dataset)
        ),
        watchlist_drift=watchlist_drift,
        evaluated_outcomes=tuple(
            dataset.loc[
                :,
                [
                    "decision_date",
                    "symbol",
                    "company_name",
                    "horizon_days",
                    "due_date",
                    "evaluation_date",
                    "return_pct",
                    "decision",
                ],
            ].to_dict("records")
        ) if not dataset.empty else (),
    )
