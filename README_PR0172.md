# PR-017.2 — Fechar o Peso Fantasma Residual (momentum_12m e shareholder_yield)

## Objetivo

O smoke test real do PR-017.1 revelou 5,5% de peso fantasma que o teste
sintético não pegava (porque o fixture preenchia as colunas à mão). Duas
causas, ambas bugs reais:

1. **`momentum_12m` era estruturalmente impossível.** `momentum(closes,
   252)` exige `len > 252` (≥253 pregões), mas `history_period="1y"`
   entrega ~251. Resultado: `momentum_12m` **sempre** `None` em produção,
   apesar de ter 20% do peso do fator timing. O fixture sintético mascarava
   isso.
2. **`shareholder_yield` ignorava buybacks e misturava escalas.** O mapper
   copiava `dividend_yield` cru. Problemas:
   - o campo `dividendYield` do Yahoo vem em **percentual** (ATO: `2.27`),
     enquanto qualquer buyback yield seria **fração** — somar os dois
     misturaria grandezas;
   - buybacks eram ignorados: a ADBE recomprou US$ 11,3 bi (12,7% do market
     cap) e aparecia como `NaN`, indo para score neutro;
   - não-pagadores de dividendo (AMD, ADBE) viravam `NaN` → peso fantasma.

## Mudanças

- `config/settings.json` — `history_period` `1y` → `2y`. Defaults de
  fallback também atualizados em `run_all.py` e `providers/yahoo.py` para
  que um settings sem a chave não reintroduza o bug silenciosamente.
- `analytics/fundamentals.py` — nova `_compute_buyback`: valor absoluto da
  recompra do último ano (`Repurchase Of Capital Stock`, fallback
  `Common Stock Payments`). Exposto como coluna `buyback`; `None` quando o
  Yahoo não reporta (a decisão "sem dado vs. não recomprou" fica no mapper).
- `providers/yahoo.py` — `fetch_symbol` passa a emitir `dividend_rate`
  (`info["dividendRate"]`, em dólares/ação, à prova de versão do yfinance).
- `analytics/mapper.py` — `shareholder_yield` recomposto:
  `dividend_rate/price + buyback/market_cap`, ambos em fração. Componente
  ausente conta como 0; empresa sem dividendo e sem recompra dá 0 real (não
  `NaN`), rankeando baixo — economicamente correto.
- `analytics/feature_audit.py` — `PRODUCIBLE_COLUMNS` += `dividend_rate`,
  `buyback`.
- Testes:
  - `tests/test_fundamentals.py` — buyback (valor absoluto e ausência).
  - `tests/test_mapper_shareholder_yield.py` (novo) — 4 casos de escala:
    dividendo+buyback, só buyback, só dividendo, nenhum → 0.
  - `tests/test_feature_contract.py` — `dividend_rate`/`buyback` no schema.

## Decisões que tomei e valem confirmar

1. **`history_period` 1y → 2y dobra o download.** É o custo de ter
   `momentum_12m` funcionando; para uma watchlist de dezenas de tickers é
   irrelevante, mas registro o tradeoff. Alternativa seria fetch de ~14
   meses, mas `2y` é padrão e dá folga (também melhora `sma_200`).
2. **Recalculei o dividendo de `dividend_rate/price` em vez de confiar no
   `dividendYield`.** O `dividendYield` do yfinance troca de escala entre
   versões (fração vs. percentual); `rate/price` é dólar/dólar, inequívoco.
   O `dividend_yield` cru continua no schema, mas não alimenta mais o score.
3. **Sem dividendo e sem buyback = 0, não `NaN`.** Um dado ausente do Yahoo
   é indistinguível de um zero genuíno; tratei como 0 para maximizar
   cobertura e empurrar não-pagadores para o fundo do ranking (a leitura
   econômica mais provável). Assumido como proxy, documentado.

## Resultado (smoke test real, AMD/ATO/ADBE)

```
symbol  momentum_12m  dividend_rate      buyback  shareholder_yield
   AMD    286.99            NaN     1.923e+09           0.0021
   ATO     16.69           4.0           NaN           0.0227
  ADBE    -39.79            NaN     1.128e+10           0.1269

PESO FANTASMA: 0.0% (era 5.5%)
features ainda mortas: nenhuma
```

Combinado com o PR-017.1, o peso fantasma no Investment Score foi de 20%
(diagnóstico do PR-017.0) a **0%**, tanto no teste sintético quanto no
pipeline real.

## Testes

```cmd
pytest tests/test_mapper_shareholder_yield.py
pytest tests/test_fundamentals.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-017.2: Fix momentum_12m window and shareholder_yield (buybacks + scale)"
```
