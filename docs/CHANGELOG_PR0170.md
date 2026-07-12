# Changelog

PR-017.0 — Feature Coverage Audit

- Adicionado `analytics/feature_audit.py`: audita quanto do Investment
  Score está alocado a features cujas colunas nunca chegam populadas
  (peso fantasma = constante 50 neutro).
- Adicionado `PRODUCIBLE_COLUMNS`: contrato explícito do schema que o
  pipeline (provider -> enrich -> mapper) consegue produzir.
- `run_all.py` passa a imprimir o relatório de cobertura e a registrar
  um aviso quando há peso fantasma. Não altera scores.
- Adicionado `tests/test_feature_contract.py`: testes de contrato
  entre coleta e modelo, sem rede. Fantasmas conhecidos ficam em
  `xfail` estrito; o peso fantasma atual (20%) fica travado contra
  regressão.

Diagnóstico atual (dados completos):

- business : 40% do peso preso em `roic`, `f_score_annual`,
  `interest_coverage`.
- valuation: 15% do peso preso em `ev_ebit`.
- financial: 10% do peso preso em `interest_coverage`.
- Investment Score: 20% do total é constante neutra.

Próximo passo: derivar `roic`, `f_score_annual`, `altman_z` e
`interest_coverage` no mapper a partir dos financials do Yahoo, ou
removê-los do config. Ao fazê-lo, atualizar `KNOWN_PHANTOM_FEATURES` e
`EXPECTED_PHANTOM_INVESTMENT_SHARE` no teste de contrato.
