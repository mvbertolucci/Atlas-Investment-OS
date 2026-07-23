# ADR-043 — Extração SEC de `total_debt` ancora no período da dívida de longo prazo

- **Status**: Accepted
- **Data**: 2026-07-23
- **Relacionado**: `providers/sec_companyfacts.py`, `backtesting/sec_edgar.py` (mapeamento de conceitos), ADR-042 (removeu `total_debt` da concordância crítica; este é o conserto de raiz que ficou como alternativa lá)

## Contexto

A extração SEC de `total_debt` somava `long_term_debt + long_term_debt_current +
short_term_debt` **apenas do último período em que *qualquer* componente
aparece** (`period = debt_periods[-1]`). Quando um emissor para de taguear a
dívida de longo prazo mas continua reportando a parcela circulante, o "último
período" passa a ter só o componente pequeno, e o total sai errado.

Medido no dado real do COP (companyfacts em cache): `LongTermDebtNoncurrent`
parou em **2021-09-30** ($22.797M); `DebtCurrent` continuou até **2026-03-31**
($1.065M). A lógica antiga escolhia 2026-03-31 e retornava **$1.065M** — para
uma petroleira com ~$23B de dívida real (Yahoo: $23.327M).

## Decisão

Ancorar o total no **último período fiscal do `long_term_debt`** (a linha
principal) e somar apenas os componentes de curto/circulante reportados **para
esse mesmo período**. Se o emissor não carrega nenhuma linha de longo prazo,
cair no comportamento anterior (último período de qualquer componente). O
`observed_at` da evidência passa a ser a data-âncora — então um longo-prazo
antigo (COP) resulta num valor **corretamente marcado STALE** a jusante, em vez
de um valor recente porém errado.

Validado no dado real em cache:

| Papel | SEC antigo | SEC novo | Yahoo |
|-------|-----------|----------|-------|
| COP   | $1.065M | **$23.717M** @ 2021-09-30 | $23.327M |
| AVAV  | $729M | $729M (inalterado) | $834,8M |
| AOS   | $616M | $616M (inalterado) | $656,9M |
| CF    | $3.216M | $3.216M (inalterado) | $3.620M |

O conserto é cirúrgico: só o caso de desalinhamento (COP) muda; AVAV/AOS/CF
seguem iguais — a diferença deles para o Yahoo é de **definição** (leases,
porção corrente), não de período, o que reforça o ADR-042 (mesmo consertado, o
SEC não bate a 5% com o Yahoo nesses casos).

## Consequências

- O secundário SEC deixa de produzir um `total_debt` absurdamente baixo quando
  a dívida de longo prazo está desatualizada; produz o valor real (marcado
  stale) ou nada. Beneficia consumidores do valor SEC (ratios point-in-time,
  fallback quando o primário falta) e a opção futura de reativar o cross-check.
- Impacto ao vivo: **nulo por design** — `total_debt` não é campo crítico
  (ADR-042), então o valor primário (Yahoo) é usado. Confirmado por
  `run_all.py --portfolio`: decisões SELL inalteradas (AVAV/CLF/FMC), journal
  intocado.
- Não resolve emissores cuja dívida de longo prazo está sob um conceito XBRL
  não mapeado (COP pós-2021) — apenas evita o total errado; o valor fica stale
  até haver nova evidência de longo prazo.

## Rollback

Reverter o commit em `providers/sec_companyfacts.py`; a lógica volta a "último
período de qualquer componente".
