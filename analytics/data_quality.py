from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _policy_block(policy: dict[str, Any] | None, name: str) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    block = policy.get(name)
    return block if isinstance(block, dict) else {}


def source_quality_scores(
    frame: pd.DataFrame,
    policy: dict[str, Any] | None,
) -> pd.Series:
    block = _policy_block(policy, "source_quality")
    missing_score = float(block.get("missing_score", 0.0))
    unknown_score = float(block.get("unknown_score", 50.0))
    patterns = {
        str(pattern).casefold(): float(score)
        for pattern, score in dict(block.get("patterns") or {}).items()
    }
    sources = frame.get("source", pd.Series("", index=frame.index)).fillna("")

    def score(value: Any) -> float:
        text = str(value).strip()
        if not text or text.casefold() in {"none", "nan", "n/a"}:
            return missing_score
        matches = [
            quality
            for pattern, quality in patterns.items()
            if pattern in text.casefold()
        ]
        return max(matches) if matches else unknown_score

    return sources.map(score).astype(float).clip(0.0, 100.0).round(1)


def freshness_scores(
    frame: pd.DataFrame,
    policy: dict[str, Any] | None,
    *,
    evaluated_at: datetime | None = None,
) -> pd.Series:
    block = _policy_block(policy, "freshness")
    fresh_days = float(block.get("fresh_days", 7.0))
    acceptable_days = float(block.get("acceptable_days", 35.0))
    if acceptable_days < fresh_days:
        raise ValueError("acceptable_days não pode ser menor que fresh_days.")
    fresh_score = float(block.get("fresh_score", 100.0))
    acceptable_score = float(block.get("acceptable_score", 70.0))
    stale_score = float(block.get("stale_score", 0.0))
    now = evaluated_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=timezone.utc)
    now_timestamp = pd.Timestamp(now).tz_convert("UTC")
    timestamps = pd.to_datetime(
        frame.get("as_of", pd.Series(None, index=frame.index)),
        errors="coerce",
        utc=True,
    )
    ages = (now_timestamp - timestamps).dt.total_seconds() / 86400.0
    result = pd.Series(stale_score, index=frame.index, dtype="float64")
    result = result.mask(ages <= acceptable_days, acceptable_score)
    result = result.mask(ages <= fresh_days, fresh_score)
    # Timestamp futuro dentro de uma pequena diferença de relógio continua
    # fresco; valores ausentes permanecem stale_score.
    result = result.mask(ages < 0, fresh_score)
    return result.clip(0.0, 100.0).round(1)
