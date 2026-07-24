# ADR-045 — Persistir os valores da linha de análise para a página da empresa

- **Data**: 2026-07-24
- **Status**: Aceito
- **Contexto de origem**: Fase 1 de usabilidade (porta única, cockpit, página
  por empresa). Pedido explícito do usuário: "quero que o one pager inclua
  absolutamente toda a informação que tenho do ticker".

## Contexto

`field_evidence_json` (ADR-014) registra, por campo, **situação, fonte e
data** — mas não o valor. Os valores brutos ficam no snapshot imutável do
provedor (`storage/raw_snapshots`), o que cobre o que foi *coletado*.

Métricas que o Atlas **deriva em memória** durante a execução não estavam em
lugar nenhum depois que a run terminava. Medido ao vivo em AVAV (83 campos de
evidência): **56 tinham valor localizável e 22 não** — todos derivados:
`rsi_14`, `momentum_3m/6m/12m`, `sma_50`, `sma_200`, `ev_ebitda`, `ev_ebit`,
`net_debt`, `net_debt_ebitda`, `distance_52w_high/low`, `fcf_yield`,
`operating_margin_proxy`, `current_liquidity`, `consensus_target`, entre outros.
Cinco derivados importantes já escapavam por terem coluna própria (`altman_z`,
`roic`, `f_score_annual`, `interest_coverage`, `target_upside`).

A página da empresa (`reports/company_page.py`) mostrava esses campos com
situação `present` mas sem número — contradição visível para o usuário.

Alternativa descartada: reaproveitar os artefatos do screener amplo
(`_ranking_0713.json`, `research_ranking_report_market.json`), que contêm
`rsi_14`/`ev_ebitda`. São de **2026-07-13 e de outro universo** — exibir aquele
número como se fosse o da run corrente seria apresentar dado velho como atual.

## Decisão

Adicionar a coluna **`analysis_values_json`** a `snapshots`, pelo mesmo mecanismo
de **migração aditiva** já usado por todas as colunas posteriores ao schema
original (`HistoryDatabase._ensure_snapshot_columns`).

`HistoryDatabase._analysis_values(row)` serializa os valores **escalares** da
linha do DataFrame de análise. Exclui explicitamente:

- `field_evidence` — tem coluna própria, não se duplica;
- `dict`/`list`/`tuple`/`set` — estruturas com armazenamento próprio (os
  DataFrames de balanço vivem no snapshot bruto);
- `NaN`/`None` — ausência não vira zero.

`reports/company_page.py::_value_for` passa a procurar o valor na cadeia
`raw → analysis → company → snapshot`. Campo derivado que ainda assim não tenha
valor continua marcado **"não persistido"** — a página nunca inventa número.

## Consequências

- **Aditivo e sem efeito no modelo.** Nada em `analysis_values_json` volta para
  scoring, decisão, deal breakers ou política de venda. É evidência de leitura.
  Nenhum motor lê essa coluna.
- **Bancos existentes migram sozinhos** ao abrir. Verificado numa cópia do banco
  real: 33 → 34 colunas, **2.427 linhas preservadas**.
- **Linhas antigas ficam com `NULL`.** O histórico anterior a esta data não
  ganha os derivados retroativamente — eles nunca foram gravados. Só runs a
  partir de agora populam a coluna.
- **Custo de armazenamento** por linha cresce (um JSON de escalares por símbolo
  por run). Aceito: é da ordem do `field_evidence_json` que já existe.

## Verificação

- `tests/test_cockpit_review_and_company_page.py::test_analysis_values_persist_derived_metrics`
  — trava que `rsi_14`/`momentum_3m` são persistidos e que `field_evidence` não
  é duplicado.
- `...::test_adding_the_column_preserves_existing_rows` — trava que um banco
  legado abre, ganha a coluna e não perde linhas.
- Suíte completa verde: **1191 testes**.
