# PR-017.4 — Consertar Deal Breaker de Short Float (escala) + Contrato da Camada

## Objetivo

Fechar o ultimo deal breaker morto e travar a camada inteira contra a
classe de bug que ja apareceu tres vezes na linha PR-017.x.

### Bug encontrado: short_float nunca disparava (escala)

O provider emite `short_float` = `shortPercentOfFloat` do Yahoo, que vem
como **fracao** (0.2449 = 24,49%). O threshold do config e
`short_float_max: 20.0`, em **pontos percentuais**. Como `0.2449 > 20.0` e
sempre falso, o deal breaker "Short float alto" **nunca disparava** — a
BYND, com 24% de short float (bandeira vermelha real), passava batido.

Mesma classe dos bugs anteriores:
- PR-017.1: `min_f_score`/`min_current_ratio` liam chaves inexistentes no
  config;
- PR-017.1: bloco de `altman_z` nao existia;
- PR-017.2: `shareholder_yield` misturava escala fracao/percentual.

## Mudancas

- `analytics/mapper.py` — `normalize_columns` converte `short_float` de
  fracao para percentual (× 100), na fonte, para o threshold em pontos
  percentuais funcionar. `short_float` era consumido apenas pelo deal
  breaker (threshold) e por `validator.py` (contagem notna, escala-
  agnostica); nenhum relatorio o multiplicava, entao nao ha dupla
  conversao. **Efeito colateral (desejado):** `short_float` nos outputs
  (Excel/historico) passa a aparecer legivel em pontos percentuais
  (24.49) em vez de fracao (0.2449).
- `tests/test_deal_breaker_contract.py` (novo) — contrato da camada:
  1. toda chave do `deal_breakers.json` tem regra/bloco reconhecido
     (`test_every_config_key_is_covered`);
  2. a coluna de cada regra e produzivel pelo pipeline
     (`test_rule_column_is_producible`);
  3. cada regra DISPARA quando violada e fica SILENCIOSA quando cumprida,
     exercitando a escala real via `normalize_columns`
     (`test_rule_fires_on_breach_and_is_silent_when_ok`);
  4. regressao direta da escala do short_float.

## Prova (smoke test real)

```
short_float apos mapper (percentual):
symbol  short_float
   AMD         2.56
  BYND        24.49

symbol  Risk Penalty   Deal Breakers
   AMD           0.0   Nenhum
  BYND          40.0   Piotroski baixo; Altman Z baixo ...; Short float alto
```

Antes deste PR, "Short float alto" nunca apareceria para nenhuma empresa.

## As 5 regras, agora todas vivas e travadas

| chave (config)         | coluna           | dispara quando | escala   |
|------------------------|------------------|----------------|----------|
| net_debt_ebitda_max    | net_debt_ebitda  | > 4.0          | ratio    |
| current_liquidity_min  | current_liquidity| < 1.0          | ratio    |
| f_score_annual_min     | f_score_annual   | < 4            | 0-9      |
| altman_z_min           | altman_z         | < 1.8          | z-score  |
| short_float_max        | short_float      | > 20 (p.p.)    | percent  |

## Testes

```cmd
pytest tests/test_deal_breaker_contract.py
pytest
python run_all.py
```

177 passed.

## Commit

```cmd
git add .
git commit -m "PR-017.4: Fix short_float deal breaker scale + add deal-breaker contract"
```
