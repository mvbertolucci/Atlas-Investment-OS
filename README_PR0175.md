# PR-017.5 — Deal Breakers Cientes de Setor (isencao para falsos positivos estruturais)

## Objetivo

Rodar o modelo no universo real (PR-017.4) revelou falsos positivos
setoriais nos deal breakers: metricas cujo threshold universal e
estruturalmente enganoso em certos setores. Os numeros estavam certos; a
regra e que era cega a setor.

Casos confirmados:
- **Altman Z** pune **utilities** (ATO, Z=1.79) e **financeiras**: fluxo de
  caixa regulado/estrutura de balanco diferente tornam o Z baixo sem
  significar risco de insolvencia. O Z de Altman foi calibrado para
  manufatura, nao para esses setores.
- **Current ratio < 1** pune **SaaS/software** (ADBE, 0.75): deferred
  revenue entra como passivo circulante mas nao e obrigacao de caixa.

## Decisao

Isencao por setor (confirmada com o usuario). Implementada de forma que a
metrica so e ignorada onde e comprovadamente enganosa por estrutura -- nao
para "melhorar o score" de nomes alavancados de verdade.

**Importante (honestidade do modelo):** a BUD (cervejaria) tem Altman Z 1.53
e CONTINUA flagada de proposito. Diferente de uma utility, uma cervejaria
com ~US$ 80 bi de divida (heranca do SABMiller) tem risco de alavancagem
real; o Z baixo ali e sinal legitimo, nao artefato. O contraste F-Score 8 vs
Altman Z baixo e o modelo mostrando "lucrativa porem muito alavancada". Por
isso "Beverages" NAO entrou na isencao.

## Mudancas

- `config/deal_breakers.json`:
  - `altman_z_exempt_sectors`: `["Utilities", "Financial Services", "Banks", "Insurance"]`
  - `current_liquidity_exempt_sectors`: `["Software"]`
- `scoring/investment.py` — `apply_deal_breakers` ganha `exemption_mask(terms)`:
  casa cada termo (substring, case-insensitive) contra `sector` OU `industry`
  da empresa. Necessario porque o Yahoo classifica SaaS como sector
  "Technology" (generico) e so o `industry` ("Software - ...") distingue,
  enquanto utilities/financeiras vem no proprio `sector`. As regras de
  Altman Z e current ratio passam a excluir as linhas isentas
  (`condition & ~exempt`).
- `tests/test_deal_breaker_contract.py`: chaves `*_exempt_sectors` sao
  reconhecidas como modificadores (nao regras); novos testes de que utility
  isenta / industrial punido no Altman Z, SaaS isento / hardware punido na
  liquidez, e que a isencao casa sector OU industry.

## Prova (universo real, antes -> depois)

| ticker | setor            | flag antes                | flag depois            | score |
|--------|------------------|---------------------------|------------------------|-------|
| ADBE   | Technology/SaaS  | Liquidez corrente baixa   | Nenhum                 | 57.9 -> 67.9 |
| ATO    | Utilities        | Altman Z baixo            | Nenhum                 | 32.9 -> 47.9 |
| BUD    | Consumer Def.    | Altman Z baixo            | **Altman Z baixo** (mantido) | 31.2 |
| AKAM   | Technology       | Net Debt/EBITDA alto      | Net Debt/EBITDA alto   | 25.7 |

A isencao e cirurgica: so ATO e ADBE (casos estruturais) mudaram; BUD e AKAM
(risco real) seguem flagados.

## Testes

```cmd
pytest tests/test_deal_breaker_contract.py
pytest
python run_all.py
```

180 passed.

## Commit

```cmd
git add .
git commit -m "PR-017.5: Sector-aware deal breakers (exempt structural false positives)"
```
