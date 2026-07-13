from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ranking.models import RankedCompany, RankingPolicy, RankingReport
from universe.models import UniverseReport


def load_ranking_policy(path: str | Path) -> RankingPolicy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return RankingPolicy.from_dict(data)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _deal_breakers(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        values = value
    else:
        values = str(value).split(";")
    result = tuple(
        str(item).strip()
        for item in values
        if str(item).strip()
        and str(item).strip().casefold() not in {"nenhum", "none", "nan"}
    )
    return result


def _sort_key(row: pd.Series, policy: RankingPolicy) -> tuple[Any, ...]:
    score_columns = (policy.primary_score, *policy.tie_breakers)
    scores = tuple(
        -(_number(row.get(column)) if _number(row.get(column)) is not None else -1.0)
        for column in score_columns
    )
    return (*scores, str(row.get("symbol", "")).upper())


def rank_companies(
    frame: pd.DataFrame,
    universe_report: UniverseReport,
    policy: RankingPolicy,
) -> RankingReport:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("rank_companies exige um DataFrame.")
    if not isinstance(universe_report, UniverseReport):
        raise TypeError("rank_companies exige UniverseReport.")
    if not isinstance(policy, RankingPolicy):
        raise TypeError("rank_companies exige RankingPolicy.")

    members = {member.symbol: member for member in universe_report.members}
    rows = [row for _, row in frame.iterrows()]
    eligible_rows = [
        row
        for row in rows
        if members.get(str(row.get("symbol", "")).strip().upper())
        and members[str(row.get("symbol", "")).strip().upper()].eligible
    ]
    eligible_rows.sort(key=lambda row: _sort_key(row, policy))
    market_ranks = {
        str(row.get("symbol", "")).strip().upper(): index
        for index, row in enumerate(eligible_rows, start=1)
    }

    sector_ranks: dict[str, int] = {}
    for sector in sorted(
        {str(row.get("sector", "")).strip() or "UNKNOWN" for row in eligible_rows}
    ):
        sector_rows = [
            row
            for row in eligible_rows
            if (str(row.get("sector", "")).strip() or "UNKNOWN") == sector
        ]
        sector_rows.sort(key=lambda row: _sort_key(row, policy))
        for index, row in enumerate(sector_rows, start=1):
            sector_ranks[str(row.get("symbol", "")).strip().upper()] = index

    preliminary: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        member = members.get(symbol)
        universe_eligible = bool(member and member.eligible)
        confidence = _number(row.get("Confidence Score"))
        investment_score = _number(row.get(policy.primary_score))
        breakers = _deal_breakers(row.get("Deal Breakers"))
        reasons: list[str] = []
        if not universe_eligible:
            reasons.append("UNIVERSE_INELIGIBLE")
        if investment_score is None:
            reasons.append("MISSING_PRIMARY_SCORE")
        if confidence is None:
            reasons.append("MISSING_CONFIDENCE_SCORE")
        elif confidence < policy.min_confidence_score:
            reasons.append("CONFIDENCE_BELOW_MINIMUM")
        if policy.require_no_deal_breakers and breakers:
            reasons.append("DEAL_BREAKER_TRIGGERED")
        preliminary.append(
            {
                "symbol": symbol,
                "sector": str(row.get("sector", "")).strip() or "UNKNOWN",
                "universe_eligible": universe_eligible,
                "safeguard_passed": not reasons,
                "safeguard_reasons": tuple(reasons),
                "market_rank": market_ranks.get(symbol),
                "sector_rank": sector_ranks.get(symbol),
                "investment_score": investment_score,
                "opportunity_score": _number(row.get("Opportunity Score")),
                "conviction_score": _number(row.get("Conviction Score")),
                "confidence_score": confidence,
                "deal_breakers": breakers,
            }
        )

    candidates = sorted(
        (item for item in preliminary if item["safeguard_passed"]),
        key=lambda item: (
            -(item["investment_score"] if item["investment_score"] is not None else -1),
            -(item["opportunity_score"] if item["opportunity_score"] is not None else -1),
            -(item["conviction_score"] if item["conviction_score"] is not None else -1),
            item["symbol"],
        ),
    )
    candidate_ranks = {
        item["symbol"]: index for index, item in enumerate(candidates, start=1)
    }
    companies = tuple(
        RankedCompany(
            **item,
            candidate_rank=candidate_ranks.get(item["symbol"]),
        )
        for item in sorted(
            preliminary,
            key=lambda item: (
                not item["safeguard_passed"],
                candidate_ranks.get(item["symbol"], 10**9),
                item["symbol"],
            ),
        )
    )
    return RankingReport(policy=policy, companies=companies)
