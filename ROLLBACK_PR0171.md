# Rollback

Antes do commit:

```cmd
del analytics\fundamentals.py
del tests\test_fundamentals.py
del docs\CHANGELOG_PR0171.md
del README_PR0171.md
```

Reverter as edições:
- `providers/yahoo.py`: remover `_safe_statement` e as 3 chaves
  `_balance_sheet`/`_income_statement`/`_cashflow` do dict retornado por
  `fetch_symbol`.
- `run_all.py`: remover o import de `analytics.fundamentals` e voltar
  `enriched = [enrich_technicals(row) for row in rows]` (sem
  `compute_fundamentals`).
- `analytics/mapper.py`: remover o bloco que deriva `ev_ebit`.
- `scoring/investment.py`: reverter `min_f_score`/`min_current_ratio`
  para as chaves antigas e remover o bloco `if "altman_z" in
  result.columns`.
- `analytics/feature_audit.py`: remover `ebit`, `roic`, `f_score_annual`,
  `altman_z`, `interest_coverage`, `ev_ebit` de `PRODUCIBLE_COLUMNS`.
- `tests/test_feature_contract.py`: restaurar `KNOWN_PHANTOM_FEATURES`,
  `EXPECTED_PHANTOM_INVESTMENT_SHARE` (20.0) e
  `EXPECTED_DEAD_WEIGHT_BY_FACTOR` (business 40.0, financial 10.0,
  valuation 15.0) do PR-017.0; remover `FUNDAMENTAL_COLUMNS`.

Depois do commit:

```cmd
git revert HEAD
```
