# ADR-042 — Remover `total_debt` da concordância crítica entre fontes

- **Status**: Accepted
- **Data**: 2026-07-22
- **Relacionado**: `config/settings.json`, `providers/yahoo.py::DEFAULT_CRITICAL_FIELDS`, `universe/collector.py`, `providers/sec_companyfacts.py`, `providers/evidence.py::reconcile_critical_fields`, ADR-038 (mesmo padrão para `market_cap`/`enterprise_value`/`short_float`/`total_cash`)

## Contexto

`reconcile_critical_fields` (`providers/evidence.py:331-345`) anula um campo
crítico (`result[field] = None`, status `INVALID`, "critical sources disagree")
quando a fonte primária (Yahoo) e a secundária (SEC EDGAR) têm o campo presente
no mesmo período fiscal mas divergem além de 5%.

Rodando a carteira real (2026-07-22), a explicação de confiança por campo
(PR-E) revelou que **28 de 58 posições (48%)** perdiam `net_debt_ebitda`, e
**todas** por `total_debt` — 26 por divergência, 2 por dado velho. Entre elas,
nomes grandes e bem cobertos: MSFT, META, GOOGL, GOOG, CVX, COP, INTU, GILD,
PYPL, NEM, MU, FCX.

Comparando os brutos por fonte, a divergência é real e o **secundário (SEC) é
o errado**:

| Papel | Yahoo | SEC EDGAR |
|-------|-------|-----------|
| AVAV  | 834,8M | 729,0M |
| AOS   | 656,9M | 615,8M |
| CF    | 3.620M | 3.216M |
| COP   | **23.327M** | **1.065M** |

O COP é decisivo: uma petroleira com ~$23B de dívida real. O
`totalDebt` do Yahoo (agregado limpo) está certo; a extração SEC está quebrada.

**Causa raiz** (`providers/sec_companyfacts.py:223-238`): a extração soma
`long_term_debt + long_term_debt_current + short_term_debt` **apenas do último
período em que qualquer um dos componentes aparece**. Se os componentes estão
desalinhados no tempo ou parcialmente tagueados no XBRL do emissor (comum), a
soma sai incompleta. Somado às diferenças legítimas de definição (leases,
porção corrente), a concordância <5% com o `totalDebt` do Yahoo é rara — e cada
falha anula o valor **correto** do Yahoo.

Este é exatamente o padrão que o ADR-038 já tratou para `market_cap`,
`enterprise_value`, `short_float` e `total_cash`: um secundário instável
rejeitando dado primário bom. `total_debt` ficou de fora à época.

## Decisão

Remover `total_debt` de `provider_critical_fields` — o `totalDebt` do Yahoo
passa a ser aceito nativamente, sem exigir concordância de 5% com o SEC.
Atualizado em três lugares (a lista de `config/settings.json` é a
autoritativa; os outros dois são defaults de código mantidos em sincronia):

- `config/settings.json` (governado);
- `providers/yahoo.py::DEFAULT_CRITICAL_FIELDS`;
- `universe/collector.py` (default do coletor de universo).

`total_debt` continua com evidência de campo própria (presente/velho/ausente);
só deixa de ser **anulado** por divergência com o SEC.

## Alternativas consideradas

- **Consertar a extração SEC** (alinhar componentes no mesmo período): ataca a
  raiz, mas a marcação XBRL de dívida varia por emissor e as definições
  (leases/porção corrente) diferem do Yahoo — não garante concordância <5% e
  mantém o risco de anulação. Não resolve o problema de forma robusta.
- **Tolerar a divergência sem anular** (manter o valor do Yahoo, marcar
  "não confirmado"): meio-termo, mas ainda trata o SEC como árbitro de um
  campo em que ele é comprovadamente pior. Preferimos remover, consistente
  com o ADR-038.

## Consequências

- `net_debt_ebitda` volta a ser calculado para ~26 posições (as 2 velhas
  seguem velhas até a próxima coleta), restaurando o sinal de alavancagem e
  elevando a confiança/cobertura na maior parte da carteira.
- Perde-se o cross-check de dívida contra o SEC. Aceitável: o `totalDebt` do
  Yahoo é internamente consistente (mesma fonte, mesma data), e o SEC estava
  degradando, não confirmando.
- Semântica de scoring inalterada; muda apenas quais campos exigem acordo
  entre fontes. Validado com `python run_all.py --portfolio` (AGENTS.md §6).

## Rollback

Readicionar `"total_debt"` às três listas. A lógica de reconciliação não mudou.
