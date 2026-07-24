# ADR-050 — Materialidade da lacuna: dizer o que ela pode mudar

- **Status**: Aceito
- **Data**: 2026-07-24
- **Relacionado**: `reports/field_materiality.py` (novo),
  `reports/evidence_reasons.py`, `decision/cockpit.py`,
  `application/reporting.py`, ADR-047/048/049 (a sequência que reduziu as
  lacunas falsas e deixou visíveis as verdadeiras)

## Contexto

Depois da ADR-047, os campos `stale` da carteira caíram de 324 para 3 — e
todos os 3 são verdadeiros positivos. Investigando o remanescente
`short_float` do BRK-B, a conclusão foi "está correto e é irrelevante": o
campo não entra no score, governa só o deal breaker `short_float_max: 20.0`,
e o último valor era **0,96%**.

O usuário recusou "aceitar e seguir" com uma exigência melhor:

> "nesse tipo de caso preciso que a informação de que é irrelevante apareça em
> algum lugar"

O ponto é justo. Hoje toda lacuna aparece com o mesmo peso visual, e o leitor
refaz a cada leitura um julgamento que o sistema já tem como responder.

## O que dá para afirmar, e o que não dá

O papel de cada campo é lido da **configuração governada** — `features.yaml`
(o que é pontuado, com que peso), `model.yaml` (peso de cada fator) e
`deal_breakers.json` (limiares e isenções) — não de uma lista paralela que
envelheceria em silêncio.

Medido nos 77 campos de evidência de um papel:

| Categoria | Qtd | O que a lacuna pode fazer |
|---|---|---|
| Nem score nem limiar | **37** | Só reduzir o Data Freshness |
| Entram no score | **27** | Mexer no percentil, sempre |
| Compõem um campo pontuado | **11** | Propagar (`total_cash` → `net_debt_ebitda`) |
| Só limiar rígido | **2** | Acionar deal breaker — distância responde |

### Três descobertas que estreitaram a afirmação

**1. `current_liquidity` é o `current_ratio` renomeado** (`COLUMN_MAP`). Como o
`current_ratio` é pontuado (peso 0,05), ele **não** permite afirmação forte.
Sem resolver o apelido, ele apareceria como "governado só por limiar" — falso.

**2. "Sem efeito na decisão" é overclaim, mesmo para o `short_float`.** O
`Data Freshness` (`analytics/data_quality.py`) itera **todos** os campos do
`field_evidence`, não só os pontuados, e tem gate próprio em 70. Nenhuma
lacuna é literalmente gratuita.

**3. Um campo pode não ser pontuado e ainda assim importar.** `total_cash` não
entra no score nem governa limiar por si, mas compõe `net_debt_ebitda`, que é
as duas coisas. A primeira versão deste módulo declarava `total_cash`
"inconsequente" — falso, e falso na direção que tranquiliza. Corrigido
propagando por `DERIVED_DEPENDENCIES`.

### O teto de oscilação dispensa simulação

A alternativa natural para campos pontuados seria **simular**: recalcular a
decisão com o campo no melhor e no pior valor. Desnecessário. Como os pesos
internos de cada fator somam 1,0 (travado em `test_governed_config`), o
deslocamento máximo que uma feature causa no Investment Score é
`peso_do_fator × peso_da_feature × 100` — aritmética de config. Vai de **9,0
pontos** (`ev_ebitda`) a **1,5** (`fcf_yield`).

**Limite honesto**: esse teto é sobre o **Investment Score**, não sobre a
decisão. Ela sai de Opportunity e Conviction (`decision/policy.py`), que
derivam dele por transformação própria. Então a nota diz "desloca o score em
até N pontos" e **nunca** "a decisão não muda" — isso exigiria a simulação que
este ADR dispensa.

## Decisão

Novo módulo `reports/field_materiality.py` com `materiality_note(campo, valor,
sector)`, devolvendo uma frase ou `None`. Quatro veredictos, nenhum alegando
irrelevância:

- **Inconsequente**: "não entra no score nem em deal breaker; o único efeito é
  reduzir o Data Freshness"
- **Propaga**: "não entra direto no score, mas compõe `net_debt_ebitda`, que
  entra — a lacuna se propaga"
- **Só limiar**: "último valor 0,96 contra limite de 20: precisaria crescer
  20,8x para acionar o deal breaker; não entra no score"
- **Pontuado**: "entra no score pelo fator valuation e desloca o Investment
  Score em até 9,0 pontos"

Regras de honestidade embutidas:

- A folga só vira adjetivo com **≥100% de margem** (`SAFE_MARGIN`); abaixo
  disso mostra a distância e cala sobre o conforto.
- A frase é **ciente da direção**: limite máximo é acionado quando o valor
  *cresce*; mínimo, quando *cai*.
- Sem último valor conhecido, não inventa distância.
- **Isenção setorial é o único veredicto definitivo** — não é estimativa, é a
  configuração dizendo que o limiar não se aplica àquele setor.

Renderizado na **página da empresa** (`reports/company_page.py`), ao lado do
status de cada campo, e no cockpit via `build_missing_reasons` (campo novo
`materiality`, opcional — chamadores antigos seguem funcionando).

A página da empresa é o sítio que importa: o cockpit só lista *features
obrigatórias e evidência de risco ausentes*, e o `short_float` do BRK-B —
o caso que originou o pedido — é `stale`, nunca entrou nessa lista. Ligar a
nota só ao cockpit teria deixado o caso relatado sem cobertura. A anotação
aparece **somente em linha com lacuna** (`stale`/`missing`/`unavailable`/
`invalid`): num campo presente a pergunta não se coloca, e a nota viraria
ruído em ~60 das 83 linhas.

## Alternativas consideradas

- **Simular a decisão campo a campo.** Único caminho para afirmar "a decisão
  não muda", mas custa um recálculo por campo por papel para melhorar uma
  resposta que o teto de oscilação já dá em aritmética.
- **Lista manual de campos irrelevantes.** Envelheceria em silêncio a cada
  mudança de `features.yaml` — exatamente o tipo de duplicação que o
  `test_governed_config` existe para impedir.
- **Só marcar o `short_float`.** Resolveria o caso relatado e ignoraria que 37
  dos 77 campos têm o mesmo problema.

## Consequências

- Um leitor deixa de refazer o julgamento "isso muda alguma coisa?" a cada
  lacuna; a resposta vem escrita e derivada da config vigente.
- **Risco**: a nota pode dar conforto indevido se alguém a ler como "a decisão
  não muda". Mitigado pelo vocabulário — nenhum veredicto usa "irrelevante" ou
  "não muda", e há teste travando isso.
- Se `features.yaml`, `model.yaml` ou `deal_breakers.json` mudarem, as notas
  acompanham sozinhas: nada é duplicado.

## Verificação

- `tests/test_field_materiality.py` — 13 testes, sobre casos reais medidos:
  folga e direção do `short_float` do BRK-B, isenção setorial do `altman_z`,
  teto de 9,0 do `ev_ebitda`, apelido `current_ratio`/`current_liquidity`,
  propagação do `total_cash`, silêncio sem valor conhecido, e uma guarda
  explícita de que nenhuma frase afirma irrelevância.
- **Bug de unidade achado na renderização real**: o limiar está em pontos
  percentuais (`short_float_max: 20`) e o valor persistido é fração —
  `analytics/mapper.py` só multiplica por 100 dentro do pipeline, não no que
  a página lê. Sem converter, o BRK-B saía como "precisaria crescer 2083x" em
  vez de 20,8x: errado por 100x, e errado na direção que tranquiliza. Travado
  por teste que renderiza a página de verdade.
- Suíte completa: **1225 testes verdes**.
