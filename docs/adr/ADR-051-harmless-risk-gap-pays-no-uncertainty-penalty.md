# ADR-051 — Lacuna de risco provadamente inócua não paga penalidade de incerteza

- **Status**: Aceito
- **Data**: 2026-07-24
- **Relacionado**: `scoring/investment.py`, ADR-050 (mesmo princípio, aplicado
  à exibição; aqui ao **cálculo**), ADR-042/ADR-048 (divergência definicional
  entre fontes, a causa da lacuna deste caso), ADR-013 (decomposição do Risk
  Penalty)

## Contexto

Auditando a execução da carteira, o CVX apareceu sem `net_debt_ebitda`,
`net_debt` e `total_cash`. A cadeia:

```
total_cash        invalid   <- "critical sources disagree"
  └─ net_debt        invalid
      └─ net_debt_ebitda  invalid   <- insumo de deal breaker
```

A causa da raiz é a de sempre: **divergência definicional**. `total_cash` do
CVX vinha 5,323 bi do Yahoo contra 6,316 bi do SEC — 18,7% de distância contra
tolerância de 5%. Ambos plausíveis para a Chevron (caixa estrito contra caixa
mais aplicações de curto prazo), o mesmo padrão de ADR-042 e ADR-048.

O motor **não fica cego** — isso foi verificado: ele registra
`risk_evidence_missing: net_debt_ebitda` e cobra
`risk_uncertainty_penalty: 3.0`. O problema é outro.

### A penalidade é que é cega

Com `total_debt` de 45,43 bi e `ebitda` de 37,91 bi, o **pior caso possível**
para o CVX — caixa igual a zero — dá `net_debt_ebitda` de **1,198**. O limiar
do deal breaker é **4,0**. Para quebrar, a Chevron precisaria de mais de
151 bi de dívida.

O valor desconhecido **não pode acionar o deal breaker**, e isso não é
estimativa: `net_debt = total_debt − total_cash`, caixa nunca é negativo,
logo `net_debt ≤ total_debt`; com `ebitda > 0`, a razão tem teto
`total_debt/ebitda`. É o conhecido respondendo pelo desconhecido.

Aplicando aos casos de `net_debt_ebitda` ausente no universo coletado:

| | teto | veredicto |
|---|---|---|
| CALM | 0,000 | não pode quebrar |
| HIG | 0,783 | não pode quebrar |
| CVX | 1,198 | não pode quebrar |
| AMP | — | indeterminado (insumo ausente) |

**Três de quatro pagavam por uma incerteza que o dado disponível já
resolvia.**

## Decisão

`record_missing` passa a aceitar, junto das isenções setoriais, uma máscara de
**lacuna provadamente inócua**. Novo `_gap_cannot_breach_ceiling` calcula o
teto da razão a partir dos insumos conhecidos e o compara com o limiar.

Conservador por construção — devolve `False` (penaliza) sempre que os insumos
não sustentam a conclusão:

- numerador ou denominador ausente;
- **denominador ≤ 0**, onde a divisão inverte a desigualdade e o teto deixa de
  ser teto (a guarda não é formalidade: EBITDA negativo é comum entre os
  papéis penalizados);
- teto **igual** ao limiar — igualdade não é folga.

Aplica-se hoje a um único campo, `net_debt_ebitda`, porque é o único insumo de
deal breaker que é uma razão com numerador limitável. Os demais não são
demonstráveis: `f_score_annual` é discreto de 0 a 9 e um valor ausente pode
estar abaixo de 4; `altman_z` é composto sem os insumos individuais
disponíveis; `short_float` não tem o que limitar.

## Alternativas consideradas

- **Deixar como está.** Três de quatro casos seguiriam penalizados por uma
  incerteza inexistente, e o efeito é silencioso — não aparece como erro,
  aparece como score um pouco pior.
- **Remover `total_cash` da concordância crítica** (padrão ADR-042/048). Trata
  a causa desta lacuna específica, mas não o problema geral: qualquer futura
  indisponibilidade de caixa voltaria a cobrar penalidade indevida. Continua
  sendo uma opção separada e legítima.
- **Estimar o valor ausente** (imputar caixa por mediana setorial, por
  exemplo). Substituiria uma incerteza honesta por um número inventado, com o
  agravante de entrar num deal breaker.

## Consequências

- Lacuna que o dado disponível já refuta deixa de custar 3,0 pontos. O efeito
  é estritamente na direção de **reduzir falsa penalidade**: nenhuma linha
  passa a ser penalizada por esta mudança.
- Nenhum deal breaker novo dispara nem deixa de disparar — a mudança é sobre
  o `risk_uncertainty_penalty`, não sobre `add_penalty`.

### Limitação conhecida, deliberadamente fora deste ADR

Este ADR trata **um lado** de uma assimetria maior:

| situação | custo |
|---|---|
| Campo de risco **desconhecido** | 3,0 pontos |
| Campo de risco **conhecido e ruim** | 15 pontos **+ `AVOID` forçado** |

Não saber é estruturalmente mais barato que saber a má notícia — e, sobretudo,
**escapa do portão de `AVOID`**. Para uma empresa genuinamente em breach, a
indisponibilidade do dado vale muito mais do que a diferença de pontos.

Corrigir esse lado significaria encarecer a lacuna indeterminada, o que muda
decisão para cima e exige medição própria. Fica registrado como aberto: este
ADR reduz falso positivo de penalidade, **não** fecha o falso negativo.

## Verificação

- `tests/test_harmless_risk_gap.py` — 7 testes, com os números reais medidos:
  teto do CVX (1,198 contra 4,0), teto acima do limiar, EBITDA negativo,
  denominador zero, insumo ausente nas três combinações, empresa sem dívida,
  e teto exatamente igual ao limiar.
- Suíte completa: **1234 testes verdes**.
- Validado com recoleta real da carteira.
