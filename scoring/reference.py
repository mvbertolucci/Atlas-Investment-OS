from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


CONTRACT_VERSION = "1.0"
DEFAULT_REFERENCE_VERSION = "1"
VALID_SCOPES = {"market", "sector"}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"", "none", "nan", "n/a"} else text


def _numeric_values(values: Any) -> list[float]:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    return sorted(float(value) for value in series.tolist())


def load_feature_scopes(features_path: str | Path) -> dict[str, str]:
    """Resolve a política de percentil de cada coluna do Feature Store."""
    data = yaml.safe_load(Path(features_path).read_text(encoding="utf-8")) or {}
    scopes: dict[str, str] = {}
    for block in data.values():
        if not isinstance(block, dict):
            continue
        for name, config in block.items():
            if not isinstance(config, dict):
                continue
            column = str(config.get("column") or name)
            scope = str(config.get("percentile_scope", "market")).strip().lower()
            if scope not in VALID_SCOPES:
                raise ValueError(
                    f"percentile_scope inválido para {column}: {scope!r}."
                )
            previous = scopes.get(column)
            if previous is not None and previous != scope:
                raise ValueError(
                    f"A coluna {column} tem percentile_scope conflitante: "
                    f"{previous!r} e {scope!r}."
                )
            scopes[column] = scope
    return scopes


@dataclass(frozen=True)
class ScoringReference:
    universe_id: str
    reference_date: str
    reference_count: int
    reference_version: str
    model_version: str
    generated_at: str
    min_sector_size: int
    feature_scopes: dict[str, str]
    distributions: dict[str, dict[str, Any]]
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError(
                f"Versão de contrato de referência não suportada: "
                f"{self.contract_version!r}."
            )
        if not _clean_text(self.universe_id):
            raise ValueError("A referência exige universe_id.")
        if not _clean_text(self.reference_date):
            raise ValueError("A referência exige reference_date.")
        if int(self.reference_count) <= 0:
            raise ValueError("A referência exige reference_count positivo.")
        if int(self.min_sector_size) < 2:
            raise ValueError("min_sector_size deve ser pelo menos 2.")
        for column, scope in self.feature_scopes.items():
            if scope not in VALID_SCOPES:
                raise ValueError(
                    f"Escopo inválido na referência para {column}: {scope!r}."
                )
            if column not in self.distributions:
                raise ValueError(f"Distribuição ausente para a feature {column}.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "universe_id": self.universe_id,
            "reference_date": self.reference_date,
            "reference_count": self.reference_count,
            "reference_version": self.reference_version,
            "model_version": self.model_version,
            "generated_at": self.generated_at,
            "min_sector_size": self.min_sector_size,
            "feature_scopes": dict(sorted(self.feature_scopes.items())),
            "distributions": dict(sorted(self.distributions.items())),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoringReference":
        if not isinstance(data, dict):
            raise TypeError("O artefato de referência deve ser um objeto JSON.")
        return cls(
            contract_version=str(data.get("contract_version", "")),
            universe_id=str(data.get("universe_id", "")),
            reference_date=str(data.get("reference_date", "")),
            reference_count=int(data.get("reference_count", 0)),
            reference_version=str(data.get("reference_version", "")),
            model_version=str(data.get("model_version", "")),
            generated_at=str(data.get("generated_at", "")),
            min_sector_size=int(data.get("min_sector_size", 5)),
            feature_scopes={
                str(key): str(value)
                for key, value in dict(data.get("feature_scopes") or {}).items()
            },
            distributions={
                str(key): dict(value)
                for key, value in dict(data.get("distributions") or {}).items()
            },
        )

    def values_for(self, column: str, sector: Any = None) -> list[float]:
        distribution = self.distributions.get(column) or {}
        if self.feature_scopes.get(column, "market") == "sector":
            sector_name = _clean_text(sector) or "UNKNOWN"
            sector_values = list(
                (distribution.get("sectors") or {}).get(sector_name) or []
            )
            if len(sector_values) >= self.min_sector_size:
                return sector_values
        return list(distribution.get("market") or [])


def build_scoring_reference(
    frame: pd.DataFrame,
    *,
    features_path: str | Path,
    model_path: str | Path,
    universe_id: str,
    reference_date: str,
    reference_version: str = DEFAULT_REFERENCE_VERSION,
    min_sector_size: int = 5,
) -> ScoringReference:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("A referência exige um DataFrame elegível não vazio.")
    scopes = load_feature_scopes(features_path)
    sectors = (
        frame.get("sector", pd.Series("UNKNOWN", index=frame.index))
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .replace("", "UNKNOWN")
    )
    distributions: dict[str, dict[str, Any]] = {}
    for column, scope in scopes.items():
        market_values = _numeric_values(frame.get(column, pd.Series(dtype=float)))
        sector_values: dict[str, list[float]] = {}
        if scope == "sector" and column in frame.columns:
            for sector_name in sorted(sectors.unique()):
                values = _numeric_values(frame.loc[sectors == sector_name, column])
                if values:
                    sector_values[str(sector_name)] = values
        distributions[column] = {
            "market": market_values,
            "sectors": sector_values,
        }

    model = yaml.safe_load(Path(model_path).read_text(encoding="utf-8")) or {}
    return ScoringReference(
        universe_id=universe_id,
        reference_date=reference_date,
        reference_count=len(frame),
        reference_version=reference_version,
        model_version=str(model.get("model_version", "legacy")),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        min_sector_size=min_sector_size,
        feature_scopes=scopes,
        distributions=distributions,
    )


def write_scoring_reference(
    reference: ScoringReference,
    path: str | Path,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(reference.to_dict(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(output)
    return output


def load_scoring_reference(path: str | Path) -> ScoringReference:
    source = Path(path)
    return ScoringReference.from_dict(
        json.loads(source.read_text(encoding="utf-8"))
    )


def _empirical_percentile(value: Any, reference_values: list[float]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 50.0
    if number != number or not reference_values:
        return 50.0
    lower = bisect_left(reference_values, number)
    equal = bisect_right(reference_values, number) - lower
    percentile = (lower + (equal + 1) / 2) / len(reference_values) * 100.0
    return max(0.0, min(100.0, percentile))


def percentile_rank(
    frame: pd.DataFrame,
    column: str,
    *,
    higher_is_better: bool = True,
    reference: ScoringReference | None = None,
    scope: str = "market",
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(50.0, index=frame.index)
    values = pd.to_numeric(frame[column], errors="coerce")
    if reference is None:
        if values.notna().sum() <= 1:
            return pd.Series(50.0, index=frame.index)
        result = values.rank(method="average", pct=True) * 100.0
    else:
        sectors = frame.get("sector", pd.Series("UNKNOWN", index=frame.index))
        result = pd.Series(
            [
                _empirical_percentile(
                    value,
                    reference.values_for(
                        column,
                        sectors.loc[index] if scope == "sector" else None,
                    ),
                )
                for index, value in values.items()
            ],
            index=frame.index,
            dtype="float64",
        )
    if not higher_is_better:
        result = 100.0 - result
    return result.fillna(50.0).clip(0.0, 100.0)


def attach_reference_metadata(
    frame: pd.DataFrame,
    reference: ScoringReference | None,
) -> pd.DataFrame:
    result = frame.copy()
    if reference is None:
        result["reference_universe"] = "CURRENT_BATCH"
        result["reference_date"] = None
        result["reference_count"] = len(result)
        result["reference_version"] = "legacy-cross-sectional"
        return result
    result["reference_universe"] = reference.universe_id
    result["reference_date"] = reference.reference_date
    result["reference_count"] = reference.reference_count
    result["reference_version"] = reference.reference_version
    return result
