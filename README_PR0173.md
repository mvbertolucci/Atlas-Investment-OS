# PR-017.3 — Unificar o Fator Valuation com o Config (sem mudar score)

## Objetivo

O fator valuation era o unico dos quatro que **ignorava** o
`config/features.yaml`: era pontuado por um dict hardcoded
(`VALUATION_FEATURES` em `factors/valuation.py`), enquanto business,
financial e timing liam o YAML. Pior: a secao `valuation:` do features.yaml
tinha pesos **divergentes** dos que rodavam de fato, entao qualquer tentativa
de tunar valuation pelo config nao surtia efeito — mesma classe de bug de
config-que-o-codigo-nao-le do PR-017.1 (deal breakers).

Divergencias encontradas (YAML ignorado vs. codigo que rodava):

| feature            | features.yaml | codigo (real) |
|--------------------|---------------|---------------|
| pb                 | 0.15          | 0.10          |
| fcf_yield          | 0.10          | 0.05          |
| shareholder_yield  | 0.10          | 0.05          |
| ev_ebit            | ausente       | 0.15          |
| ev_to_ebitda       | 0.20          | (é ev_ebitda) |

Decisao tomada (confirmada): **unificar preservando o comportamento
atual** — o features.yaml passa a ser a fonte da verdade, espelhando
exatamente os pesos que ja rodavam. Nenhum Investment Score muda; valuation
vira tunavel pelo config como os demais fatores.

## Mudancas

- `config/features.yaml` — secao `valuation:` reescrita para espelhar
  exatamente `VALUATION_FEATURES` (nomes de coluna ja normalizados:
  `ev_ebitda`/`ev_ebit`; labels batendo com as colunas de detalhe do
  scoring; pesos e direcoes identicos ao comportamento pre-017.3).
- `factors/valuation.py` — nova `resolve_valuation_features(features)`:
  le a secao valuation do features.yaml (fonte da verdade), caindo para
  `VALUATION_FEATURES` (agora documentado como fallback) quando ausente.
  Aceita tanto `higher` (dict legado) quanto `higher_is_better` (YAML).
  `score_valuation(df, features=None)` passa a resolver a config por ela.
- `factors/engine.py` — `score_all_factors` passa o `features` ja carregado
  para `score_valuation(result, features)`.
- `analytics/feature_audit.py` — `_valuation_bindings` le a mesma fonte via
  `resolve_valuation_features(features)`, pra o audit de peso fantasma nao
  dessincronizar quando os pesos de valuation forem tunados.
- `tests/test_valuation_config.py` (novo) — trava: (a) o YAML espelha o
  fallback, (b) editar um peso no YAML muda o score (config e autoritativo),
  (c) fallback usado quando a secao some, (d) aceita as duas chaves de
  direcao.

## Prova de que o score nao mudou

Baseline dos scores/confidence/colunas de detalhe de `score_valuation`
capturado em frame sintetico de 8 linhas (com NaNs) ANTES da mudanca, e
recomputado DEPOIS lendo o features.yaml:

```
score igual       : True
conf igual        : True
detail_cols igual : True
detail_vals igual : True
```

Smoke test real (AMD/ATO/ADBE), pipeline completo: Valuation Confidence
100% nos tres (ev_ebit agora entra), peso fantasma 0%.

## Testes

```cmd
pytest tests/test_valuation_config.py
pytest
python run_all.py
```

165 passed.

## Commit

```cmd
git add .
git commit -m "PR-017.3: Make features.yaml authoritative for valuation (behavior-preserving)"
```
