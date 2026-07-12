# Rollback

Antes do commit:

```cmd
del tests\test_valuation_config.py
del docs\CHANGELOG_PR0173.md
del README_PR0173.md
```

Reverter as edicoes:
- `factors/valuation.py`: remover `resolve_valuation_features` e o
  parametro `features` de `score_valuation`; voltar o loop a iterar
  `VALUATION_FEATURES` direto (`for column, cfg in VALUATION_FEATURES...`).
- `factors/engine.py`: voltar para `score_valuation(result)`.
- `config/features.yaml`: restaurar a secao `valuation` antiga (pe 0.20,
  forward_pe 0.15, ev_to_ebitda 0.20, pb 0.15, peg 0.10, fcf_yield 0.10,
  shareholder_yield 0.10) e remover a nota de cabecalho.
- `analytics/feature_audit.py`: voltar o import para
  `from factors.valuation import VALUATION_FEATURES` e `_valuation_bindings`
  a iterar `VALUATION_FEATURES` (sem o parametro `features`); reverter a
  chamada em `collect_model_features` para `_valuation_bindings(factor_weight)`.

Nota: como o PR foi behavior-preserving, reverter tambem nao muda nenhum
Investment Score — so volta valuation a ser nao-tunavel por config.

Depois do commit:

```cmd
git revert HEAD
```
