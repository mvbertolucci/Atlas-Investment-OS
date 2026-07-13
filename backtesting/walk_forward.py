from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from backtesting.point_in_time import AsOfSnapshot, PointInTimeDataset
from backtesting.point_in_time_fundamentals import derive_point_in_time_ratios
from scoring.investment import score_dataframe


PERFORMANCE_DISCLAIMER = (
    "This report deterministically replays Atlas decisions at each cutoff "
    "using only evidence visible at that time. It makes no return, risk or "
    "performance claim -- that validation is a separate, later step."
)


def _text(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} não pode ser vazio.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} não pode ser vazio.")
    return text


def _utc_timestamp(value: datetime | str, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name} deve ser um timestamp ISO-8601 com fuso horário."
            ) from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} exige fuso horário explícito.")
    return value.astimezone(timezone.utc)


def compute_governed_config_hashes(
    paths: Mapping[str, str | Path],
) -> dict[str, str]:
    """
    SHA-256 dos arquivos de configuração governada usados num run de
    walk-forward. Prova de que os pesos/thresholds usados na reconstrução
    são exatamente os do commit auditado -- não uma alegação não verificável.
    """
    return {
        label: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for label, path in paths.items()
    }


@dataclass(frozen=True)
class HistoricalInputManifest:
    """
    Proveniência versionada e atribuível de um run de walk-forward.

    Espelha exatamente a lista de "Required provenance for PR-033" em
    docs/POINT_IN_TIME_DATA.md. Se um campo obrigatório não puder ser
    preenchido honestamente, o manifesto não deve ser construído --
    preencher com um valor inventado violaria o próprio propósito do
    contrato point-in-time.
    """

    source_name: str
    source_version: str
    benchmark_source: str
    constituent_history_source: str
    decision_calendar_description: str
    timezone: str
    tracked_fields: tuple[str, ...]
    revision_policy: str
    delisting_coverage_description: str
    unresolved_delisting_count: int
    atlas_code_revision: str
    governed_config_hashes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "source_name",
            "source_version",
            "benchmark_source",
            "constituent_history_source",
            "decision_calendar_description",
            "timezone",
            "revision_policy",
            "delisting_coverage_description",
            "atlas_code_revision",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )

        tracked_fields = tuple(
            _text(item, "tracked_fields")
            for item in self.tracked_fields
        )
        if not tracked_fields:
            raise ValueError("tracked_fields não pode ser vazio.")
        object.__setattr__(self, "tracked_fields", tracked_fields)

        count = int(self.unresolved_delisting_count)
        if count < 0:
            raise ValueError("unresolved_delisting_count não pode ser negativo.")
        object.__setattr__(self, "unresolved_delisting_count", count)

        hashes = dict(self.governed_config_hashes)
        if not hashes:
            raise ValueError("governed_config_hashes não pode ser vazio.")
        object.__setattr__(self, "governed_config_hashes", hashes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_version": self.source_version,
            "benchmark_source": self.benchmark_source,
            "constituent_history_source": self.constituent_history_source,
            "decision_calendar_description": self.decision_calendar_description,
            "timezone": self.timezone,
            "tracked_fields": list(self.tracked_fields),
            "revision_policy": self.revision_policy,
            "delisting_coverage_description": self.delisting_coverage_description,
            "unresolved_delisting_count": self.unresolved_delisting_count,
            "atlas_code_revision": self.atlas_code_revision,
            "governed_config_hashes": dict(self.governed_config_hashes),
        }


@dataclass(frozen=True)
class IncompleteDecision:
    """
    A decision that could not be honestly reconstructed at this cutoff.

    Never silently dropped, never repaired with present-day data -- reported
    explicitly with a machine-readable reason.
    """

    symbol: str
    decision_at: datetime
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "decision_at": self.decision_at.isoformat(),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ReplayedDecision:
    """One symbol's reconstructed decision at one historical cutoff."""

    symbol: str
    decision_at: datetime
    investment_score: float | None
    opportunity_score: float | None
    conviction_score: float | None
    decision: str
    deal_breakers: tuple[str, ...]
    model_confidence: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "decision_at": self.decision_at.isoformat(),
            "investment_score": self.investment_score,
            "opportunity_score": self.opportunity_score,
            "conviction_score": self.conviction_score,
            "decision": self.decision,
            "deal_breakers": list(self.deal_breakers),
            "model_confidence": self.model_confidence,
        }


@dataclass(frozen=True)
class WalkForwardReport:
    manifest: HistoricalInputManifest
    decision_dates: tuple[datetime, ...]
    replayed_decisions: tuple[ReplayedDecision, ...]
    incomplete_decisions: tuple[IncompleteDecision, ...]
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "advisory_only": True,
            "performance_disclaimer": PERFORMANCE_DISCLAIMER,
            "manifest": self.manifest.to_dict(),
            "decision_dates": [
                item.isoformat() for item in self.decision_dates
            ],
            "summary": {
                "total_decision_dates": len(self.decision_dates),
                "total_replayed": len(self.replayed_decisions),
                "total_incomplete": len(self.incomplete_decisions),
            },
            "replayed_decisions": [
                item.to_dict() for item in self.replayed_decisions
            ],
            "incomplete_decisions": [
                item.to_dict() for item in self.incomplete_decisions
            ],
        }


def reconstruct_snapshot_frame(snapshot: AsOfSnapshot) -> pd.DataFrame:
    """
    Reconstrói um DataFrame a partir de um AsOfSnapshot: uma linha por membro
    ativo, uma coluna por field_name de fato observado no snapshot.

    Pura reconstrução -- nenhum valor é inventado ou preenchido a partir de
    outra data ou símbolo. Um membro sem nenhuma observação disponível ainda
    ganha uma linha (todos os campos None), para que possa ser reportado como
    decisão incompleta em vez de silenciosamente descartado.
    """
    field_names = sorted(
        {observation.field_name for observation in snapshot.observations}
    )
    rows: list[dict[str, Any]] = []
    for symbol in snapshot.members:
        row: dict[str, Any] = {"symbol": symbol}
        for field_name in field_names:
            try:
                row[field_name] = snapshot.value(symbol, field_name)
            except KeyError:
                row[field_name] = None
        rows.append(row)
    return pd.DataFrame(rows, columns=["symbol", *field_names])


def replay_decision_batch(
    snapshot: AsOfSnapshot,
    *,
    model_path: str | Path,
    deal_breakers_path: str | Path,
) -> tuple[tuple[ReplayedDecision, ...], tuple[IncompleteDecision, ...]]:
    """
    Reconstrói o snapshot e roda o motor de decisão governado (score_dataframe,
    inalterado) exatamente sobre os dados visíveis naquele corte.

    Um símbolo é incompleto quando:
    - tem delistagem conhecida e efetiva com return_treatment "unresolved"
      (nunca resolvido silenciosamente); ou
    - não há nenhuma observação disponível para ele neste corte (não se
      inventa nem se empresta dado de outra data).
    Do contrário, o score_dataframe já existente decide -- inclusive seu
    próprio tratamento tolerante de campos individualmente ausentes
    (fator neutro, confiança reduzida), sem duplicar essa lógica aqui.
    """
    delisting_by_symbol = {
        record.symbol: record for record in snapshot.delistings
    }
    frame = reconstruct_snapshot_frame(snapshot)
    data_columns = [
        column for column in frame.columns if column != "symbol"
    ]

    incomplete: list[IncompleteDecision] = []
    complete_symbols: list[str] = []

    for symbol in snapshot.members:
        reasons: list[str] = []

        delisting = delisting_by_symbol.get(symbol)
        if delisting is not None and delisting.return_treatment == "unresolved":
            reasons.append("UNRESOLVED_DELISTING")

        if data_columns:
            row = frame.loc[frame["symbol"] == symbol, data_columns]
            has_any_data = bool(row.notna().any(axis=1).iloc[0])
        else:
            has_any_data = False

        if not has_any_data:
            reasons.append("NO_DATA_AVAILABLE")

        if reasons:
            incomplete.append(
                IncompleteDecision(
                    symbol=symbol,
                    decision_at=snapshot.decision_at,
                    reasons=tuple(reasons),
                )
            )
        else:
            complete_symbols.append(symbol)

    if not complete_symbols:
        return (), tuple(incomplete)

    eligible = frame[frame["symbol"].isin(complete_symbols)].reset_index(
        drop=True
    )
    # config/features.yaml lê razões (gross_margin, current_ratio, roic...),
    # não os totais brutos que a reconstrução point-in-time produz -- sem
    # isto, replay sobre dado real da SEC cairia quase todo em fatores
    # neutros. derive_point_in_time_ratios só preenche o que está ausente,
    # nunca sobrescreve uma razão já fornecida pela fonte.
    eligible = derive_point_in_time_ratios(eligible)
    scored = score_dataframe(eligible, Path(model_path), Path(deal_breakers_path))

    replayed: list[ReplayedDecision] = []
    for _, row in scored.iterrows():
        replayed.append(
            ReplayedDecision(
                symbol=str(row["symbol"]),
                decision_at=snapshot.decision_at,
                investment_score=row.get("Investment Score"),
                opportunity_score=row.get("Opportunity Score"),
                conviction_score=row.get("Conviction Score"),
                decision=str(row.get("Decision") or ""),
                deal_breakers=(
                    tuple(
                        item.strip()
                        for item in str(row.get("Deal Breakers") or "").split(";")
                        if item.strip() and item.strip() != "Nenhum"
                    )
                ),
                model_confidence=row.get("Model Confidence"),
            )
        )

    return tuple(replayed), tuple(incomplete)


def run_walk_forward(
    dataset: PointInTimeDataset,
    decision_dates: Iterable[datetime | str],
    manifest: HistoricalInputManifest,
    *,
    model_path: str | Path,
    deal_breakers_path: str | Path,
) -> WalkForwardReport:
    """
    Motor de walk-forward determinístico: para cada data de decisão, chama
    `dataset.as_of(decision_at)` e reconstrói a decisão usando apenas o que
    era visível naquele corte, através do motor de scoring governado
    existente. Não recalcula retornos, risco ou performance -- isso é
    validação separada e posterior.
    """
    if not isinstance(dataset, PointInTimeDataset):
        raise TypeError("run_walk_forward exige um PointInTimeDataset.")
    if not isinstance(manifest, HistoricalInputManifest):
        raise TypeError("run_walk_forward exige um HistoricalInputManifest.")

    dates = tuple(
        sorted(
            {
                _utc_timestamp(item, "decision_at")
                for item in decision_dates
            }
        )
    )
    if not dates:
        raise ValueError("decision_dates não pode ser vazio.")

    replayed: list[ReplayedDecision] = []
    incomplete: list[IncompleteDecision] = []

    for decision_at in dates:
        snapshot = dataset.as_of(decision_at)
        batch_replayed, batch_incomplete = replay_decision_batch(
            snapshot,
            model_path=model_path,
            deal_breakers_path=deal_breakers_path,
        )
        replayed.extend(batch_replayed)
        incomplete.extend(batch_incomplete)

    return WalkForwardReport(
        manifest=manifest,
        decision_dates=dates,
        replayed_decisions=tuple(replayed),
        incomplete_decisions=tuple(incomplete),
    )


def monthly_decision_calendar(
    start: date | str,
    end: date | str,
    *,
    day_of_month: int = 1,
) -> tuple[datetime, ...]:
    """
    Calendário de decisão explícito e determinístico: um corte por mês,
    UTC à meia-noite, do dia `day_of_month` (grudado ao último dia do mês
    quando este for mais curto). Conveniência opcional -- o motor aceita
    qualquer iterável explícito de datas, gerado por este helper ou não.
    """
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)
    if end < start:
        raise ValueError("end não pode anteceder start.")
    if not 1 <= day_of_month <= 28:
        raise ValueError("day_of_month deve estar entre 1 e 28.")

    dates: list[datetime] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        candidate = date(year, month, day_of_month)
        if start <= candidate <= end:
            dates.append(
                datetime(
                    candidate.year,
                    candidate.month,
                    candidate.day,
                    tzinfo=timezone.utc,
                )
            )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return tuple(dates)


def write_walk_forward_report(
    report: WalkForwardReport,
    output_path: str | Path,
) -> Path:
    if not isinstance(report, WalkForwardReport):
        raise TypeError("report deve ser WalkForwardReport.")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
