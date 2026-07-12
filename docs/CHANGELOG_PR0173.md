# Changelog

PR-017.3 — Unificar o Fator Valuation com o Config

- `factors/valuation.py`: nova `resolve_valuation_features(features)` le a
  secao `valuation` de config/features.yaml (fonte da verdade), com o dict
  `VALUATION_FEATURES` como fallback documentado. `score_valuation` ganha o
  parametro `features`.
- `factors/engine.py`: passa o features.yaml carregado para score_valuation.
- `config/features.yaml`: secao `valuation` reescrita para espelhar
  exatamente os pesos/labels/direcoes que rodavam hardcoded (comportamento
  preservado). Antes esta secao era ignorada.
- `analytics/feature_audit.py`: `_valuation_bindings` le a mesma fonte, para
  o audit acompanhar tuning de pesos de valuation.
- `tests/test_valuation_config.py` (novo): trava a fonte da verdade (YAML
  espelha fallback; editar peso muda o score; fallback quando ausente; aceita
  `higher`/`higher_is_better`).

Motivacao: valuation era o unico fator que ignorava features.yaml (dict
hardcoded), com pesos divergentes do config — mesma classe do bug de deal
breaker do PR-017.1. Decisao: unificar preservando o score.

Verificacao: baseline de score/confidence/detalhes identico antes e depois;
165 passed; smoke real com valuation confidence 100% e peso fantasma 0%.

Ver README_PR0173.md.
