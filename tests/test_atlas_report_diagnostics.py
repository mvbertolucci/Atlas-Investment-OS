from __future__ import annotations

from reports.atlas_report.diagnostics import extract_status_conflicts

_STATUS_MD_WITH_CONFLICTS = """
# STATUS.md

## 1. Motores de decisão ativos

| Motor | O que decide |
|---|---|
| `decision/policy.py` | Decision |

### ⚠️ Conflitos sinalizados
1. **`Decision` vs `Recommendation`** — dois classificadores em paralelo.
2. **`priority.build_sell_priority` vs `portfolio.sell_rules`** — podem divergir.

---

## 2. Fórmulas em produção

| Métrica | Fórmula | Status |
|---|---|---|
| ROIC | live vs backtest | **CONFLITO A RESOLVER (parcial)** |
| Interest Coverage | live vs backtest | **CONFLITO A RESOLVER (parcial)** |
| F-Score | igual nos dois | Sem conflito |
"""

_STATUS_MD_WITHOUT_CONFLICTS = """
# STATUS.md

## 1. Motores de decisão ativos

| Motor | O que decide |
|---|---|
| `decision/policy.py` | Decision |

## 2. Fórmulas em produção

| Métrica | Fórmula | Status |
|---|---|---|
| F-Score | igual nos dois | Sem conflito |
"""


def test_extracts_engine_conflict_count_from_numbered_section() -> None:
    alerts = extract_status_conflicts(_STATUS_MD_WITH_CONFLICTS)
    assert any("2 conflitos entre motores" in alert for alert in alerts)


def test_extracts_formula_conflict_count_from_table_rows() -> None:
    alerts = extract_status_conflicts(_STATUS_MD_WITH_CONFLICTS)
    assert any("2 fórmulas com implementação conflitante" in alert for alert in alerts)


def test_no_alerts_when_status_md_has_no_conflict_markers() -> None:
    assert extract_status_conflicts(_STATUS_MD_WITHOUT_CONFLICTS) == ()


def test_no_alerts_when_status_md_text_is_empty() -> None:
    assert extract_status_conflicts("") == ()


def test_conflict_section_stops_at_next_heading() -> None:
    text = """
### ⚠️ Conflitos sinalizados
1. Primeiro conflito.

## 2. Outra seção
1. Isto não é um conflito de motor, é outra lista.
"""
    alerts = extract_status_conflicts(text)
    assert any("1 conflito entre motores" in alert for alert in alerts)
