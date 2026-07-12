# Rollback

Antes do commit:

```cmd
del tests\test_mapper_shareholder_yield.py
del docs\CHANGELOG_PR0172.md
del README_PR0172.md
```

Reverter as edições:
- `config/settings.json`: `history_period` de volta para `"1y"`.
- `run_all.py`: fallback de `history_period` de volta para `"1y"`.
- `providers/yahoo.py`: `period` default de volta para `"1y"` (2
  ocorrências) e remover a chave `dividend_rate` do dict de `fetch_symbol`.
- `analytics/fundamentals.py`: remover `_compute_buyback` e a linha
  `row["buyback"] = _compute_buyback(cashflow)`.
- `analytics/mapper.py`: restaurar o bloco antigo de `shareholder_yield`
  (`out["shareholder_yield"] = pd.to_numeric(out["dividend_yield"], ...)`).
- `analytics/feature_audit.py`: remover `dividend_rate` e `buyback` de
  `PRODUCIBLE_COLUMNS`.
- `tests/test_feature_contract.py`: remover `dividend_rate` de
  `RAW_PROVIDER_COLUMNS` e `buyback` de `FUNDAMENTAL_COLUMNS`.
- `tests/test_fundamentals.py`: remover
  `test_buyback_absolute_value` e `test_buyback_none_when_absent`.

Depois do commit:

```cmd
git revert HEAD
```
