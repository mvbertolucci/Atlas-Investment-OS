from __future__ import annotations

from typing import Any, Mapping


# Vocabulário de status derivado (não armazenado): computado de journal + ledger
# a cada leitura, evitando uma segunda fonte de verdade que pudesse
# dessincronizar. Ordem de precedência: um fill no ledger domina o journal.
STATUS_NEW = "novo"
STATUS_ANALYZING = "em_analise"
STATUS_DECIDED = "decidido"
STATUS_EXECUTED = "executado"
STATUS_DISCARDED = "descartado"

STATUS_LABELS = {
    STATUS_NEW: "Novo",
    STATUS_ANALYZING: "Em análise",
    STATUS_DECIDED: "Decidido",
    STATUS_EXECUTED: "Executado",
    STATUS_DISCARDED: "Descartado",
}

_JOURNAL_STATUS_MAP = {
    "ACCEPTED": STATUS_DECIDED,
    "REJECTED": STATUS_DISCARDED,
    "DEFERRED": STATUS_ANALYZING,
}


def _latest_journal_status_by_decision(journal: Mapping[str, Any]) -> dict[str, str]:
    latest: dict[str, str] = {}
    for event in journal.get("events", []):
        decision_id = str(event.get("decision_id", ""))
        if decision_id:
            latest[decision_id] = str(event.get("status", "")).upper()
    return latest


def derive_decision_statuses(
    journal: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> dict[str, str]:
    """Status corrente por decision_id, derivado de journal + ledger.

    Retorna apenas ids com algum evento humano ou fill; um id ausente é
    implicitamente `novo` (ver `status_for`). Um fill no ledger classifica
    como `executado` independentemente do último status humano — o ledger só
    aceita um fill sobre uma decisão cujo último status seja ACCEPTED, então
    `executado` sempre implica um ACCEPTED anterior.
    """
    statuses: dict[str, str] = {}
    for decision_id, journal_status in _latest_journal_status_by_decision(
        journal
    ).items():
        statuses[decision_id] = _JOURNAL_STATUS_MAP.get(journal_status, STATUS_NEW)
    for event in ledger.get("events", []):
        decision_id = str(event.get("decision_id", ""))
        if decision_id:
            statuses[decision_id] = STATUS_EXECUTED
    return statuses


def status_for(statuses: Mapping[str, str], decision_id: str) -> str:
    """Status de um decision_id, com `novo` como padrão para ids sem registro."""
    return statuses.get(str(decision_id), STATUS_NEW)
