# PR-017.1 — Derivar Fundamentals Fantasmas (ROIC, F-Score, Altman Z, Interest Coverage, EV/EBIT)

## Objetivo

Zerar o peso fantasma diagnosticado no PR-017.0 (20% do Investment Score
travado em constante 50 neutro) derivando as métricas ausentes a partir
das demonstrações financeiras anuais do Yahoo Finance, em vez de deixá-las
sem coluna produzível.

## Arquivos

- `analytics/fundamentals.py` (novo) — deriva `ebit`, `interest_coverage`,
  `roic`, `altman_z` e `f_score_annual` a partir de `_balance_sheet`,
  `_income_statement`, `_cashflow`.
- `providers/yahoo.py` — `fetch_symbol` passa a anexar as 3 demonstrações
  anuais brutas (`t.balance_sheet`, `t.financials`, `t.cashflow`) via
  `_safe_statement` (retorna `None` em vez de propagar exceção quando o
  ticker não tem cobertura, ex.: ETFs).
- `run_all.py` — `collect_market_data` roda `compute_fundamentals` logo
  após `enrich_technicals`; o helper descarta as 3 chaves de demonstração
  bruta do row (mesmo padrão de `history`).
- `analytics/mapper.py` — deriva `ev_ebit = enterprise_value / ebit`
  (mesma família de derivação de `net_debt_ebitda`, `fcf_yield`, etc.).
- `scoring/investment.py` — **2 bugs corrigidos em `apply_deal_breakers`**:
  - `min_f_score` lia as chaves `piotroski_min`/`min_piotroski`, que não
    existem em `config/deal_breakers.json` (a chave real é
    `f_score_annual_min`); funcionava por coincidência porque o fallback
    hardcoded (4) bate com o valor do config.
  - `min_current_ratio` tinha o mesmo problema com `current_ratio_min` vs.
    a chave real `current_liquidity_min`.
  - **Bloco de `altman_z_min` não existia** — o deal breaker de Altman Z
    estava morto no código, independente de a coluna existir. Adicionado
    com penalidade 15 (mesma ordem de grandeza de Net Debt/EBITDA e
    Piotroski).
- `analytics/feature_audit.py` — `PRODUCIBLE_COLUMNS` atualizado com
  `ebit`, `roic`, `f_score_annual`, `altman_z`, `interest_coverage`,
  `ev_ebit`.
- `tests/test_feature_contract.py` — `KNOWN_PHANTOM_FEATURES` esvaziado,
  `EXPECTED_PHANTOM_INVESTMENT_SHARE` e `EXPECTED_DEAD_WEIGHT_BY_FACTOR`
  zerados (os `xfail` viram passes reais).
- `tests/test_fundamentals.py` (novo) — valida as 4 fórmulas contra
  números calculados à mão (ROIC, Altman Z, Interest Coverage, Piotroski
  9/9), cobre ausência de demonstrações e ausência de apenas o ano
  anterior.

## Fórmulas

- **Interest Coverage** = EBIT / |Interest Expense| (ano corrente).
- **ROIC** = NOPAT / Invested Capital, NOPAT = EBIT × (1 − alíquota
  efetiva); alíquota = Tax Provision / Pretax Income, com fallback para
  21% (estatutária EUA) quando pretax income ausente ou implausível.
- **Altman Z** = 1.2×(Working Capital/Assets) + 1.4×(Retained
  Earnings/Assets) + 3.3×(EBIT/Assets) + 0.6×(Market Cap/Liabilities) +
  1.0×(Revenue/Assets). Usa o `market_cap` corrente (preço de hoje) contra
  passivos do último balanço anual — mistura de janelas temporais comum
  em ferramentas retail, mas vale ter em mente.
- **F-Score (Piotroski, 0-9)** — compara ano corrente com anterior nos 9
  critérios clássicos (lucro, CFO, ΔROA, CFO > lucro, Δalavancagem,
  Δliquidez corrente, diluição, Δmargem bruta, Δgiro de ativos). Exige as
  duas safras completas; retorna `None` (não um score parcial) se faltar
  qualquer campo do ano anterior.

## Decisões que tomei e valem confirmar

1. **Escopo ampliado para `ev_ebit`**: o PR-017.0 e a sessão anterior só
   citavam roic/f_score_annual/altman_z/interest_coverage, mas isso
   deixaria 4.5% de peso fantasma no fator valuation (`ev_ebit`). Como o
   EBIT já ficou disponível, deriveis também `ev_ebit` no mapper para
   realmente zerar o total, não só a maior fatia.
2. **Corrigi os 2 bugs de chave em `apply_deal_breakers`** mesmo não
   estando no escopo original — sem isso, o deal breaker de Altman Z
   continuaria morto mesmo com a coluna populada, o que teria enganado o
   objetivo do PR ("destravar os deal breakers").
3. **Altman Z usa `market_cap` do dia**, não o market cap na data do
   balanço. Mistura janelas, mas é a prática comum quando não se tem
   preço histórico por data de fechamento contábil.

## Resultado (smoke test real, AMD)

```
ebit: 4271000000.0
interest_coverage: 32.6
roic: 0.051
altman_z: 40.2
f_score_annual: 7.0
ev_ebit: 211.0

PESO FANTASMA NO INVESTMENT SCORE: 5.5% (era 20.0%)
```

Os 5 fantasmas do PR-017.0 (roic, f_score_annual, interest_coverage×2,
ev_ebit) foram para 100% de cobertura. O 5.5% restante vem de
`momentum_12m` (janela de 252 pregões vs. `period="1y"` do provider, que
às vezes não cobre o suficiente) e `shareholder_yield` (AMD não paga
dividendo) — causas diferentes, fora do escopo deste PR. **Resolvido no
PR-017.2** (ver `README_PR0172.md`): peso fantasma real 5.5% -> 0%.

## Testes

```cmd
pytest tests/test_fundamentals.py
pytest tests/test_feature_contract.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-017.1: Derive ROIC, F-Score, Altman Z, Interest Coverage and EV/EBIT from Yahoo financials"
```
