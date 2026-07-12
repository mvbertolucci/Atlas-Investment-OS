# Changelog

PR-017.5 — Deal Breakers Cientes de Setor

- `config/deal_breakers.json`: novas listas `altman_z_exempt_sectors`
  (Utilities, Financial Services, Banks, Insurance) e
  `current_liquidity_exempt_sectors` (Software).
- `scoring/investment.py`: `apply_deal_breakers` ganha `exemption_mask` que
  casa termos (substring, case-insensitive) contra `sector` OU `industry`.
  Altman Z e current ratio deixam de punir setores onde a metrica e
  estruturalmente enganosa (utilities/financeiras para Altman Z; SaaS com
  deferred revenue para current ratio).
- `tests/test_deal_breaker_contract.py`: chaves `*_exempt_sectors` tratadas
  como modificadores; testes de isencao (utility/SaaS isentos,
  industrial/hardware punidos, casamento sector OU industry).

Motivacao: rodar o modelo no universo real (PR-017.4) revelou falsos
positivos setoriais -- numeros certos, regra cega a setor. Nao e bug de
calculo, e limitacao de modelagem.

Nota: BUD (cervejaria, Altman Z 1.53) NAO foi isentada de proposito -- ali a
alavancagem e risco real, nao artefato setorial. Isencao mira so os casos
estruturais (utilities/financeiras/SaaS).

Prova (real): ADBE e ATO deixam de ser punidos (score 57.9->67.9 e
32.9->47.9); BUD e AKAM (risco real) seguem flagados. 180 passed.

Ver README_PR0175.md.
