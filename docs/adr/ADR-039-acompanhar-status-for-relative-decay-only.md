# ADR-039 — Status `ACOMPANHAR` separa sinal informativo de REVISAR acionável

- **Status**: Accepted
- **Data**: 2026-07-22
- **Relacionado**: `portfolio/sell_rules.py`, ADR-011 (priority como voz única de venda), ADR-037/ADR-038 (fixes que precederam este)

## Contexto

Depois de destravar o motor de venda (teses preenchidas) e dos protocolos de
PE/ROE/FX (ADR-037/ADR-038), rodando a carteira real de 18 posições, o
usuário questionou o valor prático da ferramenta com **67% das posições em
REVISAR** — "que sentido faz eu ter um programa se terei um percentual tão
grande em revisar". Investigação (não achismo) separou o REVISAR em 3
causas por reason text já existente no código:

1. **Gate de confiança** (dado insuficiente pra confiar na decisão).
2. **Sinal exclusivamente relativo** (`relative_decay`, `review_only:
   true` por padrão em `config/sell_rules.yaml` — percentil comparativo
   caiu abaixo de 40, **nunca** dispara TRIM/SELL sozinho, é sinal de
   oportunidade relativa, não deterioração da empresa).
3. **Distress preliminar** (1 evidência independente, pedindo confirmação
   antes de virar SELL — o núcleo do motor funcionando como projetado).

Medido: **7-13 das 18 posições** caíam em REVISAR só pela causa 2 — o
maior bucket, de longe, e o único puramente informativo. Ele já ocupava o
mesmo rótulo visual/de prioridade que "gate bloqueado" e "distress
pendente", que genuinamente pedem atenção.

## Decisão

Novo valor de `action`, `ACOMPANHAR`, usado **exclusivamente** quando a
única regra disparada é `relative_decay` (`portfolio/sell_rules.py`,
branch `elif triggered:`). Nenhuma lógica de decisão nova — é uma
reclassificação do mesmo caminho de código que já existia isolado (a
mensagem "Sinal exclusivamente relativo/informativo" já era um branch
próprio antes desta mudança).

Propagado em 6 pontos, mapeados por busca exaustiva de `"REVISAR"` no
código de produção antes de tocar em qualquer arquivo (evita o erro já
registrado em memória de mudança de decisão incompleta):

1. `portfolio/models.py` — `RebalanceAction` aceita `ACOMPANHAR`; nova
   property `RebalancePlan.informational_actions`, separada de
   `review_actions` (que continua só REVISAR de verdade).
2. `portfolio/rebalance.py` — prioridade de ordenação `ACOMPANHAR: 35`
   (entre REVISAR=20 e HOLD=50).
3. `priority/pipeline.py::build_sell_priority` — ACOMPANHAR sai da
   prioridade de venda via `continue` explícito, mesmo padrão já usado
   pra `BUY` (não é sobre vender).
4. `reports/atlas_report/context.py` — `required_actions` (que alimenta
   "Ações Requeridas") passa a excluir ACOMPANHAR além de HOLD; nova
   `InformationalSignal`/`ctx.informational_signals`, construída
   reaproveitando `TickerDetail.negative_features` (já computado por
   `compute_symbol_contributions`, sem cálculo novo) pra dar detalhe
   numérico — pedido explícito do usuário ("deve ficar claro inclusive
   numericamente quais os itens que pesam").
5. `reports/atlas_report/render.py` — nova seção "Sinais informativos"
   (entre Ações Requeridas e Carteira), classe CSS `pill-acompanhar` (azul,
   deliberadamente mais neutra que o amarelo de REVISAR ou o vermelho de
   SELL/TRIM).
6. `portfolio/report.py` — novo `summary.acompanhar_actions`, mesmo
   padrão das contagens já existentes.

## Consequências

- REVISAR passa a significar só "gate de confiança bloqueado" ou "distress
  preliminar pedindo confirmação" — medido ao vivo: caiu de 13 pra 6 (das
  18 posições), com as 7 restantes corretamente movidas pra ACOMPANHAR.
- Nenhuma mudança de comportamento de venda/compra — é reclassificação de
  rótulo/exibição sobre uma decisão que já era, por design, informativa.
- `RebalancePlan.review_actions`/prioridade de venda/Ações Requeridas do
  relatório nunca mais incluem ACOMPANHAR — mas nada esconde o sinal: ele
  aparece com o mesmo nível de detalhe (percentil + top-3 features que
  pesam) que a seção de detalhe por ativo já mostrava.
- 1085 testes verdes; verificado ao vivo contra a carteira real
  (`--portfolio`): `<h2>Sinais informativos</h2>` renderiza com
  decomposição numérica real (ex.: BNTX — "Net Debt/EBITDA (percentil 5)
  · Piotroski F-Score (percentil 19) · Momentum 6M (percentil 13)").
