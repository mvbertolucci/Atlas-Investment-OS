# Changelog

PR-017.2 — Fechar o Peso Fantasma Residual

- `config/settings.json`: `history_period` `1y` -> `2y`. `momentum_12m`
  (janela de 252 pregões) era estruturalmente impossível com 1y (~251
  pregões), sempre `None` apesar de 20% do peso do fator timing. Defaults
  de fallback em `run_all.py` e `providers/yahoo.py` também atualizados.
- `analytics/fundamentals.py`: nova `_compute_buyback` (valor absoluto de
  `Repurchase Of Capital Stock`, fallback `Common Stock Payments`),
  exposta como coluna `buyback`.
- `providers/yahoo.py`: `fetch_symbol` emite `dividend_rate`
  (`dividendRate`, dólares/ação).
- `analytics/mapper.py`: `shareholder_yield` recomposto como
  `dividend_rate/price + buyback/market_cap` (ambos em fração, mesma
  escala). Corrige (a) buybacks ignorados, (b) mistura de escala
  percentual/fração do `dividendYield`, (c) não-pagadores virando `NaN`.
- `analytics/feature_audit.py`: `PRODUCIBLE_COLUMNS` += `dividend_rate`,
  `buyback`.
- Testes: buyback em `test_fundamentals.py`; novo
  `test_mapper_shareholder_yield.py` (4 casos de escala);
  `dividend_rate`/`buyback` em `test_feature_contract.py`.

Resultado (smoke test real AMD/ATO/ADBE): peso fantasma 5,5% -> 0,0%,
nenhuma feature morta. Somado ao PR-017.1: 20% -> 0% de ponta a ponta.

Tradeoff: `2y` dobra o volume de download por ticker. Ver
`README_PR0172.md` para fórmulas e decisões.
