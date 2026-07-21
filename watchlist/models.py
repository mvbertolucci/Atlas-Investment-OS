from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from portfolio.validators import normalize_symbol, normalize_text

TRIGGER_STATUSES = (
    "no_condition",
    "invalid_condition",
    "not_evaluated",
    "clear",
    "triggered",
)

WATCHLIST_ENTRY_SOURCES = ("manual", "auto")


@dataclass(frozen=True)
class WatchlistEntry:
    """
    Uma linha de config/watchlist.csv. `included_at`/`note`/`trigger_condition`
    são metadado escrito pelo usuário -- retrocompatível: um CSV com só
    `symbol,name` carrega normalmente com os três vazios.

    `source` distingue curadoria manual (`"manual"`, o default -- inclui
    toda linha legada sem essa coluna) de entradas gravadas pelo fluxo de
    curadoria automática (`"auto"`). É a base da salvaguarda "nunca excluir
    automaticamente uma entrada manual": só remoção automática consulta este
    campo, o gate manual (`promote_to_watchlist`/planilha) nunca precisa se
    importar com ele.
    """

    symbol: str
    name: str = ""
    included_at: date | str | None = None
    note: str = ""
    trigger_condition: str = ""
    source: str = "manual"

    def __post_init__(self) -> None:
        symbol = normalize_symbol(self.symbol)
        if not symbol:
            raise ValueError("WatchlistEntry exige um símbolo válido.")
        object.__setattr__(self, "symbol", symbol)

        for field_name in ("name", "note", "trigger_condition"):
            object.__setattr__(
                self,
                field_name,
                normalize_text(getattr(self, field_name)),
            )

        source = normalize_text(self.source).lower() or "manual"
        if source not in WATCHLIST_ENTRY_SOURCES:
            raise ValueError(
                f"source de watchlist inválido: {source!r} "
                f"(esperado um de {WATCHLIST_ENTRY_SOURCES})"
            )
        object.__setattr__(self, "source", source)

        included_at = self.included_at
        if isinstance(included_at, str):
            text = included_at.strip()
            try:
                included_at = date.fromisoformat(text) if text else None
            except ValueError as exc:
                raise ValueError(
                    "included_at deve usar o formato YYYY-MM-DD."
                ) from exc
        if included_at is not None and not isinstance(included_at, date):
            raise TypeError("included_at exige date, string ISO ou None.")
        object.__setattr__(self, "included_at", included_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "included_at": (
                self.included_at.isoformat()
                if self.included_at is not None
                else None
            ),
            "note": self.note,
            "trigger_condition": self.trigger_condition,
            "source": self.source,
        }


@dataclass(frozen=True)
class WatchlistTriggerResult:
    """
    Resultado da avaliação de um símbolo num run: se a condição disparou
    NESTE run (transição, não estado), mais aging (idade/sugestão de limpeza).
    """

    symbol: str
    trigger_condition: str
    status: str
    message: str
    age_days: int | None = None
    last_triggered_at: str | None = None
    cleanup_suggested: bool = False

    def __post_init__(self) -> None:
        if self.status not in TRIGGER_STATUSES:
            raise ValueError(f"status de trigger inválido: {self.status}")

    @property
    def triggered_this_run(self) -> bool:
        return self.status == "triggered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trigger_condition": self.trigger_condition,
            "status": self.status,
            "triggered_this_run": self.triggered_this_run,
            "message": self.message,
            "age_days": self.age_days,
            "last_triggered_at": self.last_triggered_at,
            "cleanup_suggested": self.cleanup_suggested,
        }


@dataclass(frozen=True)
class WatchlistReport:
    """
    `auto_curation`, se presente, é o `AutoCurationResult.to_dict()` do
    fluxo de curadoria automática deste mesmo run -- guardado como dict já
    serializado (não o tipo `AutoCurationResult` em si) para não criar um
    import circular (`watchlist.auto_curation` já importa `WatchlistEntry`
    deste módulo).
    """

    results: tuple[WatchlistTriggerResult, ...] = field(default_factory=tuple)
    generated_at: datetime = field(default_factory=datetime.now)
    auto_curation: dict[str, Any] | None = None

    @property
    def triggered(self) -> tuple[WatchlistTriggerResult, ...]:
        return tuple(item for item in self.results if item.triggered_this_run)

    @property
    def cleanup_candidates(self) -> tuple[WatchlistTriggerResult, ...]:
        return tuple(item for item in self.results if item.cleanup_suggested)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "triggered_count": len(self.triggered),
            "cleanup_candidate_count": len(self.cleanup_candidates),
            "results": [item.to_dict() for item in self.results],
            "auto_curation": self.auto_curation,
        }
