# Rollback

Antes do commit:

```cmd
del docs\CHANGELOG_PR0175.md
del README_PR0175.md
```

Reverter as edicoes:
- `config/deal_breakers.json`: remover as chaves `altman_z_exempt_sectors`
  e `current_liquidity_exempt_sectors`.
- `scoring/investment.py`: remover a funcao `exemption_mask`, as duas
  variaveis `altman_z_exempt` / `current_liquidity_exempt`, e voltar as
  condicoes de Altman Z e current ratio para sem o `& ~exempt`.
- `tests/test_deal_breaker_contract.py`: reverter
  `test_every_config_key_is_covered` (remover o filtro `_exempt_sectors`) e
  remover os testes `test_altman_z_exempt_for_utilities`,
  `test_current_liquidity_exempt_for_software`,
  `test_exemption_matches_sector_or_industry`.

Nota: reverter faz ATO e ADBE voltarem a ser punidos por falsos positivos
setoriais (Investment Score cai de volta).

Depois do commit:

```cmd
git revert HEAD
```
