# ADR-038 — Protocolo geral de câmbio para market_cap/enterprise_value de ADRs

- **Status**: Accepted
- **Data**: 2026-07-21
- **Relacionado**: ADR-037 (PE/ROE estruturais, `_enterprise_value_implausible` original), `providers/yahoo.py`, `providers/finnhub.py`, `providers/evidence.py::reconcile_critical_fields`

## Contexto

O ADR-037 já tinha uma guarda de plausibilidade absoluta para `enterprise_value`
(`EV/MarketCap` fora de `[-5×, 20×]` → rejeitado). O usuário pediu explicitamente
um **protocolo geral** para ADRs em moeda estrangeira — não um patch pontual
para os holdings de hoje — depois que 7 posições reais (BNTX, BRK-B, BTI, JBS,
PAM, SGML, YPF) ficaram travadas em `REVISAR` por `market_cap`/`enterprise_value`
marcados `invalid` (`reconcile_critical_fields`, "critical sources disagree").

Investigação measure-first (ao vivo, contra as 7 posições reais) mostrou que
**a causa não é uma só**:

1. **`market_cap` já é 100% resolvível sem câmbio nenhum** — `preço(USD) ×
   ações` bate quase exato com o vendor pra 5 dos 7 (BNTX: 23.348.803.818 vs
   23.348.803.584). A ADR cota em dólar; preço e contagem de ações nunca
   precisam de conversão.
2. **Só 1 dos 7 (YPF) tem bug de câmbio de verdade.** Reconstruindo o EV eu
   mesmo com os inputs brutos: `totalDebt`/`totalCash` da YPF batem com o
   `enterpriseValue` que o próprio Yahoo reporta (12,5T vs 12,88T, ratio 1,03)
   — ou seja, o Yahoo usa esses números tal como estão. Convertendo essa
   mesma dívida de ARS→USD pela taxa real (0,000677), o EV cai para US$28,6bi
   — múltiplo de 1,42× sobre o market cap, plausível. `financialCurrency=ARS`
   confirma a origem: dívida reportada em pesos, rotulada como se fosse dólar.
3. **BNTX e BTI nunca tiveram bug de câmbio.** O EV que o Yahoo reporta pra
   BNTX bate exatamente com minha reconstrução própria (9,945bi = 9,945bi,
   ratio 0,43×, plausível). O de BTI (5,27×) também já é plausível — é o
   múltiplo real de um conglomerado alavancado (aquisição da Reynolds
   American), não erro de unidade. O que os invalidava era só o Finnhub
   discordando com um número pior — reconciliação cross-vendor rejeitando
   dado bom porque a segunda fonte, em nomes pouco cobertos, às vezes erra
   mais que a primeira.
4. **BRK-B, JBS, PAM, SGML têm `financialCurrency=USD`** — não são câmbio,
   são discordância genuína entre vendors em nomes de cobertura fina (medido:
   PAM e YPF têm bugs de unidade absurdos no lado do Finnhub, não do Yahoo).
   Ficam **fora** deste protocolo — problema diferente, não abordado aqui.

## Decisão

Dois mecanismos gerais, sem lista de tickers hardcoded — funcionam para
qualquer ADR que entrar no universo amplo no futuro:

### 1. `market_cap` — computado, não mais reconciliado entre vendors

`providers/yahoo.py::_compute_market_cap(price, shares_outstanding)` =
`preço × ações`, currency-neutral por construção. Vira a fonte primária
sempre que `price`/`sharesOutstanding` estão disponíveis (praticamente
sempre, para qualquer símbolo cotado); cai pro `marketCap` do vendor só se
`sharesOutstanding` faltar. `market_cap` sai de
`DEFAULT_CRITICAL_FIELDS`/`config/settings.json::provider_critical_fields`
— não precisa mais de acordo com o Finnhub.

### 2. `enterprise_value` — resolvido em cascata, câmbio corrige em vez de só rejeitar

`providers/yahoo.py::_resolve_enterprise_value`, nessa ordem:

1. Se o `enterpriseValue` que o próprio Yahoo reporta já é plausível
   (`_enterprise_value_implausible` do ADR-037) → usa como está
   (`direct_vendor`) — preserva consistência com `ev_to_ebitda`/
   `ev_to_revenue` do próprio vendor, que não são recalculáveis aqui.
2. Se implausível → reconstrói `market_cap + total_debt - total_cash` com
   os valores brutos reportados (sem câmbio) e testa de novo
   (`reconstructed`).
3. Se ainda implausível **e** `financialCurrency ≠ quoteCurrency` → busca
   taxa de câmbio ao vivo (`{MOEDA}USD=X`, mesmo client Yahoo já em uso,
   `_default_fx_rate_to_usd`, injetável via `fx_rate_fetcher` pra teste) e
   reconverte dívida/caixa (`fx_corrected:{de}->{para}@{taxa}`).
4. Se ainda implausível → fica `None`, protegido corretamente (não é mais
   câmbio, é outro problema real).

Em qualquer caminho que não seja `direct_vendor`, `ev_to_ebitda`/
`ev_to_revenue` (razões pré-computadas do próprio Yahoo, usando o número
antigo/rejeitado) são nulados junto — `ev_ebit` é isento porque
`analytics/mapper.py` o deriva diretamente de `enterprise_value` e herda a
correção automaticamente.

`enterprise_value` também sai de `DEFAULT_CRITICAL_FIELDS`/
`provider_critical_fields` — a checagem de plausibilidade absoluta (mais a
correção de câmbio) é um sinal mais forte que exigir concordância de 5% com
um vendor secundário de cobertura fina, que o measure-first provou rejeitar
dado bom (BNTX, BTI).

## Adendo — `total_cash`: `ev_to_ebitda` re-derivado, e a definição canônica de "caixa"

**`ev_to_ebitda` re-derivado, não só nulado.** Achado ao vivo na primeira
validação (YPF): nular `enterpriseValue`/`ev_to_ebitda`/`ev_to_revenue`
sempre que a proveniência não é `direct_vendor` recuperava `market_cap`/
`enterprise_value`, mas **piorava** a confiança de YPF (57,2→52,2) — porque
`ev_ebitda` (peso 0,30 em valuation, o dominante desde o ADR-037) ficava
`invalid`, um custo maior que o ganho de recuperar dois campos que não são
eles mesmos features pontuadas. Corrigido: `providers/yahoo.py::
_derive_ev_ebitda` recalcula `enterprise_value / ebitda` sempre que a razão
pronta do Yahoo foi rejeitada — espelha exatamente como `ev_ebit` já era
derivado em `analytics/mapper.py`. Precisa acontecer na camada do provider
(não no mapper): o gate de confiança lê `field_evidence`, não a coluna
numérica — derivar o valor rio abaixo sem atualizar a evidência aqui seria
ignorado silenciosamente pelo gate. Resultado ao vivo: YPF 52,2→62,2,
destravou o gate de confiança de verdade.

**Decisão de modelo: `total_cash` = caixa estrito, não "caixa + investimentos
de curto prazo".** Investigando por que `total_cash` da BRK-B ainda
divergia entre Yahoo e SEC ("critical sources disagree"), medi ao vivo que
o próprio Yahoo expõe DUAS linhas diferentes na demonstração financeira:
`Cash And Cash Equivalents` (US$51,9bi) e `Cash Cash Equivalents And Short
Term Investments` (US$373,3bi). `info.get("totalCash")` (US$397,4bi) bate
com a linha AMPLA, não a estrita — o SEC (US$58,8bi) bate com a estrita.
**Não é peculiaridade da Berkshire — é um bug geral de definição**: qualquer
empresa com buffer de liquidez grande (bancos, seguradoras) teria
`total_cash` inflado por investimentos de curto prazo escondidos dentro do
campo agregado do Yahoo, distorcendo `enterprise_value`/`net_debt`/
`net_debt_ebitda` pra baixo (dívida líquida artificialmente mais folgada).
Confirmado que o rótulo `Cash And Cash Equivalents` existe de forma estável
em toda posição real testada (MSFT, JNJ, LMT, ASML, JBS, PAM, BRK-B) — não
é caso especial. `providers/yahoo.py::_cash_and_equivalents` extrai essa
linha estrita do balanço (mesmo padrão de `_stockholders_equity`) e
substitui `info.totalCash` como fonte canônica pra TODO símbolo, antes do
cálculo de `enterprise_value` (a ordem importa: extração de caixa acontece
antes de `_resolve_enterprise_value`).

## Adendo 3 — `short_float`: dupla listagem não deve corromper leitura US-nativa

Investigando por que JBS ainda travava (`short_float invalid`, "critical
sources disagree") depois dos adendos acima, medi ao vivo os dois lados da
reconciliação: `short_interest` do Massive (33.642.565, 2026-06-30) é
**idêntico** ao `sharesShort` do Yahoo — mesma fonte de fato (FINRA),
mesma data de liquidação. O numerador nunca foi o problema. O denominador
diverge muito: `free_float` do Massive = 527.082.698 (67,9% do total) vs
`floatShares` do Yahoo = 327.591.941 (42,2%) — uma diferença de 61%. A JBS
N.V. tem uma reestruturação de listagem dupla complexa (holding holandesa +
NYSE) que aparentemente confunde a metodologia de free float do Massive,
contando como "livre" parte da participação controladora da família
Batista que o Yahoo corretamente exclui.

**Regra decidida (pedido explícito do usuário): a leitura de short float
deve refletir o mercado americano; listagem dupla não pode corrompê-la.**
Como o Yahoo já entrega `shortPercentOfFloat` nativamente — mesma fonte,
mesma data, já escopado ao mercado americano por construção, sem depender
de nenhuma composição entre feeds — `short_float` sai de
`DEFAULT_CRITICAL_FIELDS`/`config/settings.json::provider_critical_fields`,
mesmo tratamento dos dois campos anteriores. Massive deixa de arbitrar
`short_float` na reconciliação ao vivo (`fetch_watchlist`) — continua
existindo e sendo usado normalmente nos pipelines separados de composição
de mercado amplo (`providers/market_cap_composition.py`,
`universe/collector.py --market`), que não passam por esse loop de
reconciliação.

**Efeito colateral notado**: como os 3 campos que o Massive suporta
(`market_cap`, `enterprise_value`, `short_float`) saem todos de
`critical_fields`, o `MassiveMarketDataProvider` fica **inerte** dentro do
loop de reconciliação de `fetch_watchlist` (interseção com `critical_fields`
vira vazia) — decisão consciente, não descoberta depois. Papel dele nos
pipelines de universo amplo é intocado.

## Adendo 4 — `total_cash` ainda travava a BRK-B: bug de timestamp, não de magnitude

Rodando de novo depois do Adendo 2, `total_cash` da BRK-B continuava
`invalid`/"critical sources disagree" — mas agora por um motivo diferente
do original. Medido ao vivo: `_cash_and_equivalents` lia do balanço
**anual** (`t.balance_sheet`), cuja coluna mais recente era FY2025
(31/12/2025, US$51,9bi) — mas `observed_at_by_field` carimba esse campo com
`info["mostRecentQuarter"]` (31/03/2026) **independente de qual
demonstração realmente forneceu o valor**. Ou seja: um número de um
trimestre atrás estava sendo rotulado como se fosse do trimestre corrente,
e nesse intervalo a posição de caixa real da Berkshire mudou o suficiente
(US$51,9bi→US$58,1bi) pra estourar a tolerância de 5% contra o SEC
(US$58,8bi) — um artefato de rótulo de data, não um erro de fonte. Corrigido
lendo `t.quarterly_balance_sheet` primeiro (mesma linha `Cash And Cash
Equivalents`), caindo pro balanço anual só se o trimestral não existir.
Verificado ao vivo: coluna de 31/03/2026 do trimestral = US$58,12bi — bate
com o SEC a 1,2% de diferença, dentro da tolerância.

## Consequências

- Generaliza para qualquer ADR futuro do screener amplo — não depende de
  lista de símbolos, só de `financialCurrency`/`quoteCurrency` (já vêm do
  Yahoo) e de uma checagem econômica absoluta já calibrada.
- `roe` continua reconciliado via Finnhub normalmente — só `market_cap`/
  `enterprise_value` saíram do conjunto de campos críticos.
- BRK-B/JBS/PAM/SGML **não** são resolvidos por este protocolo — ficam como
  próximo item de investigação separado (discordância de vendor em nomes
  pouco cobertos, não câmbio).
- `ev_to_ebitda` (peso dominante em valuation desde o ADR-037, 0.30) fica
  `None` sempre que `enterprise_value` precisou de reconstrução/correção —
  aceito conscientemente: usar a razão pré-computada do Yahoo contra um EV
  diferente do que ela foi calculada seria pior que não ter o dado.
