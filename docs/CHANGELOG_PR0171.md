# Changelog

PR-017.1 — Derivar Fundamentals Fantasmas

- Adicionado `analytics/fundamentals.py`: deriva `ebit`,
  `interest_coverage`, `roic`, `altman_z` e `f_score_annual` a partir das
  demonstrações financeiras anuais do Yahoo (`balance_sheet`,
  `financials`, `cashflow`).
- `providers/yahoo.py::fetch_symbol` passa a anexar as 3 demonstrações
  brutas (`_balance_sheet`, `_income_statement`, `_cashflow`); tickers
  sem cobertura recebem `None` em vez de propagar exceção.
- `run_all.py` roda `compute_fundamentals` logo após `enrich_technicals`;
  as chaves de demonstração bruta são descartadas do row no processo.
- `analytics/mapper.py` deriva `ev_ebit = enterprise_value / ebit`.
- `scoring/investment.py::apply_deal_breakers`: corrigidas as chaves de
  `f_score_annual_min` e `current_liquidity_min` (liam nomes que não
  existem em `deal_breakers.json`, funcionavam só por coincidência de
  default); adicionado o bloco de `altman_z_min`, que não existia.
- `analytics/feature_audit.py`: `PRODUCIBLE_COLUMNS` atualizado com as
  novas colunas produzíveis.
- `tests/test_feature_contract.py`: `KNOWN_PHANTOM_FEATURES` esvaziado,
  peso fantasma esperado zerado (era 20%, business 40% / valuation 15% /
  financial 10%).
- Adicionado `tests/test_fundamentals.py`: valida as 4 fórmulas contra
  contas feitas à mão, cobre ausência de demonstrações e de apenas o ano
  anterior.

Resultado (sintético, dados completos): peso fantasma no Investment Score
20% -> 0%. Resultado (smoke test real, AMD): 20% -> 5.5%, restante vindo
de `momentum_12m` (janela de histórico) e `shareholder_yield` (empresa
sem dividendo) — causas não relacionadas a este PR, candidatas a
PR-017.2.

Ver `README_PR0171.md` para fórmulas e decisões tomadas.
