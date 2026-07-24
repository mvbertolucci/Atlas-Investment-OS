# STATUS.md — Estado real do sistema Atlas

> **REGRA DE PROCESSO**: este arquivo deve ser atualizado como último passo de toda
> sessão que altere motores de decisão, fórmulas de métricas ou config/thresholds.
> Antes de dar a sessão por encerrada: suíte verde (não deve mudar comportamento),
> commit, push. Specs e docs em `docs/` descrevem intenção; este arquivo descreve o
> que o código faz **hoje**, com citação de arquivo/função.

---

## 0. Arquitetura de execução (refatorada 2026-07-17)

`run_all.py` deixou de conter a lógica do pipeline e virou **raiz de composição**
(575 linhas): `orchestration/pipeline.py` executa estágios tipados explícitos
(cada estágio declara artefatos de entrada e saída tipada, falha rápido em
dependência ausente) e `orchestration/services.py` define fachadas estreitas. A
implementação real vive em `application/` — `collection.py`, `scoring.py`,
`history.py`, `intelligence.py`, `reporting.py`, `ticker.py`, `runtime.py`. As
funções históricas de `run_all.py` (`build_scores`,
`generate_portfolio_intelligence`, etc.) continuam existindo como **wrappers de
compatibilidade** que delegam ao serviço correspondente — CLI
(`--full`/`--portfolio`/`--ticker`) e contratos de saída inalterados. As
citações abaixo apontam para a implementação real; o wrapper homônimo em
`run_all.py` existe em todos os casos.

## 1. Motores de decisão ativos

| Motor | O que decide | Onde é chamado | Ativo em produção? |
|---|---|---|---|
| `decision/policy.py::evaluate_decision` (via `decision/engine.py::apply_decision`) | `Decision` (STRONG_BUY…AVOID) a partir de Opportunity+Conviction+Risk | `scoring/investment.py::score_dataframe` → `application/scoring.py::ScoringApplicationService.build_scores`, roda em `--full`, `--portfolio`, `--ticker` | **Sim** |
| `models/investment_model.py::apply_recommendation` | `Score Band` — faixa **descritiva** do Investment Score (Elite/Alto/Bom/Médio/Baixo), sem estrela nem verbo de compra | mesma cadeia, logo após `Decision` | **Sim, mas NÃO é classificador de compra** — rebaixado de veredicto (`Recommendation` em estrelas) para rótulo descritivo; `Decision` é a voz única de compra (reconciliação do conflito #1) |
| `portfolio/sell_rules.py::evaluate_sell_rules` | SELL/TRIM/HOLD/REVISAR/ACOMPANHAR por holding real, via 4 regras (distress, valuation_stretch, fundamental_decay, relative_decay) + confidence gate + escalonamento. `distress` agrupa motivos em famílias de evidência independentes (solvência, alavancagem, liquidez, estresse de mercado, qualidade operacional — `RuleEvaluation.evidence_count`) em vez de contar regras cruas, evitando que dois sintomas do mesmo problema (ex.: Altman Z e Interest Coverage, ambos solvência) inflem a escalação; `distress_review_at`/`distress_sell_at` (default 1/2) exigem 2+ famílias independentes para SELL automático, 1 família vira REVISAR. `relative_decay` é `review_only` por padrão (sinal cross-sectional/comparativo nunca dispara TRIM/SELL sozinho) — **desde 2026-07-22, quando é a ÚNICA regra disparada, vira `ACOMPANHAR`, não `REVISAR`** (achado pedido pelo usuário: rodando a carteira real com o protocolo de FX do ADR-038 já ativo, 7-13 das 18 posições ficavam em REVISAR só por esse sinal informativo, inflando o número sem nenhuma pedir decisão de verdade). `ACOMPANHAR` fica de fora de `RebalancePlan.review_actions`/`priority.build_sell_priority`/`RequiredAction` do Atlas Report — tem seção própria "Sinais informativos" no relatório, com a mesma decomposição de top-contribuições negativas já usada na seção de detalhe por ativo (nenhum cálculo novo). REVISAR passou a significar só gate de confiança bloqueado ou distress preliminar (1 evidência, pedindo confirmação) — medido ao vivo: de 13 REVISAR pra 6, com 7 corretamente movidos pra ACOMPANHAR | `portfolio/rebalance.py` → `portfolio.pipeline.build_portfolio_intelligence` → `application/intelligence.py::generate_portfolio_intelligence` | **Sim** — único motor de venda para holdings reais (`config/portfolio.csv`). Quando `SellEngineBlockedError` dispara (posição sem tese), `build_portfolio_intelligence` substitui o plano por REVISAR/holding (`_build_blocked_rebalance_plan`) em vez de suprimir a seção Carteira inteira — score/qualidade/alocação continuam visíveis, só a decisão de venda fica indisponível |
| `priority/pipeline.py::build_sell_priority` | **Read-only, sem decisão própria** — copia `action`/`reason`/`triggered_rules`/`priority` verbatim de `PortfolioReport.rebalance.actions` (o rebalance oficial); `deal_breakers` só como contexto explicativo, nunca determina a ação. Sem `PortfolioReport`, a lista de venda fica vazia (nunca fabrica ação) | `application/reporting.py::generate_priority_report`, chamado incondicionalmente (`priority_enabled=True` por default) | **Sim** — reconciliado com o rebalance oficial (conflito #2 resolvido) |
| `watchlist/triggers.py::evaluate_watchlist_triggers` | trigger / no-trigger + cleanup-candidate por item da watchlist | `application/intelligence.py::generate_watchlist_report` | **Sim** |
| `ranking/pipeline.py::rank_companies` | candidate_rank / safeguard_passed (não é buy/sell, é filtro de screener) | `application/scoring.py::generate_ranking_report`, só em `mode == "full"` | **Sim**, escopo restrito ao screener |
| `watchlist/promote.py::promote_to_watchlist` / `remove_from_watchlist` | inclui/remove símbolo na watchlist (grava no CSV, `source=manual`\|`auto`) | CLI (`__main__`), planilha (`apply_candidates_workbook.py`) — **e agora também** `watchlist/auto_curation.py::run_auto_curation`, chamado por `application/intelligence.py::IntelligenceApplicationService.run_watchlist_auto_curation` dentro de `IntelligenceStage`, em todo run `--full`/`--portfolio` | **CLI/planilha manuais permanecem inalterados** — `run_all.py` agora **também** grava, via o fluxo automático adicional (`config/watchlist_auto.yaml::enabled: true`, ver seção 6 e ADR-036). Inclusão só produz candidatos no modo `--full`, combinando S&P 500, Mercado Amplo e ADR em ordem determinística; exclusão roda em ambos os modos, contra o Investment Score da watchlist já mesclada naquele run |
| `watchlist/screening.py::propose_from_broad_reports` + `derive_trigger_condition` | **propõe** (nunca grava) inclusões na watchlist a partir dos screeners AMPLOS (Mercado Amplo/ADR), com `trigger_condition` derivada do perfil (cortes de `ranking.yaml`/`models/investment_model.py`, nenhum inventado) | `reports/atlas_report/context.py::build_report_context` → seção "Sugestões para a watchlist" do relatório, só quando `broad_market_report_path`/`adr_report_path` informados (`mode == "full"`) | **Sim** — read-only, alimenta a watchlist por critério estabelecido sem tocar no CSV curado. `propose_watchlist_candidates` (fonte = `ranking_report` estreito do próprio run) continua existindo mas não é mais chamada pelo relatório — comparar candidatos contra a watchlist da qual eles vieram é tautológico (achado rodando de verdade: 39/39 sempre já watched) |

### Funil consolidado de oportunidades (2026-07-22)

`watchlist/opportunity_funnel.py` publica
`output/dados/market_opportunity_funnel.json` antes da mutação automática da
Watchlist. O contrato v1.0 consolida S&P 500, Mercado Amplo e ADR, registra
datas/contagens por fonte, deduplica símbolos na mesma precedência da curadoria
e expõe quantos passaram pelos safeguards, quantos qualificaram pela política
governada e quais `top_n` foram selecionados. É read-only e reutiliza
`select_auto_inclusion_candidates`; não cria score nem decisão paralela.

### Watchlist como fila ativa (2026-07-22)

Entradas novas preservam estado-base, origem analítica, rank/score de entrada,
prazo de revisão e condições objetivas de promoção/descarte no CSV. Linhas
legadas carregam com defaults conservadores. `watchlist_report.json` publica
`active_queue` com estado efetivo derivado da evidência corrente:
`promotion_ready`, `waiting_trigger`, `review_required` ou `discard_review`.
Esses estados organizam decisão humana; não executam compra nem transformam
aging em rejeição automática. Ver `docs/ACTIVE_WATCHLIST.md`.

### Decision Queue / base do cockpit (2026-07-22)

`decision/queue.py` consolida, sem recalcular, as ações oficiais do motor de
venda e os estados da Watchlist ativa em `EXECUTE`, `INVESTIGATE`, `WAIT` e
`MONITOR`. O contrato é escrito atomicamente em
`output/dados/decision_queue.json`, incorporado ao Dashboard v1.2 e exposto em
`GET /decision-queue`. Candidato com gatilho disparado recebe
`REVIEW_FOR_PURCHASE`, nunca uma compra automática. Ver
`docs/DECISION_QUEUE.md`.

Desde 2026-07-22 (contrato v1.1, ADR-040): `decision_id` é estável entre
execuções (hash de símbolo|ação|motor, sem timestamp), permitindo que journal
e ledger acompanhem a mesma decisão ao longo de dias; cada execução também
grava snapshot imutável da fila em
`output/dados/history/decision_queue/` — base do diff "o que mudou desde a
última execução".

`decision/delta.py` compara a fila atual com o snapshot anterior e escreve
`output/dados/decision_delta.json` (contrato v1.0), renderizado no topo do
cockpit como "Mudou desde a última execução". Escalação de ação
(REVISAR→SELL no mesmo papel) é pareada por (símbolo, motor) e reportada como
transição, não como saída+entrada; scores movem acima de limiar (5.0),
evidência que aparece/some é sempre material, `current_weight` é ignorado
(ruído de preço). Itens sem mudança são contados, não listados.

Confiança explicável (PR-E, 2026-07-22): itens da fila carregam
`missing_evidence` (união de `missing_required_features` e
`risk_evidence_missing`, sem o placeholder "Nenhum") e
`missing_evidence_detail` (aditivo ao contrato v1.1). Cards com
`decision_confidence` ou `data_coverage` abaixo do piso 60 ganham um bloco que
explica **por que** cada campo falta, lendo o `field_evidence` real do pipeline
(`reports/evidence_reasons.py`): para um campo derivado nomeia a dependência
culpada e seu status (ex.: AVAV → "Net Debt/EBITDA não foi calculado: dívida
total — o valor foi rejeitado"; BRK-B → "F-Score Piotroski (anual): nenhuma
fonte retornou o dado"). A ação sugerida depende da causa: divergência/rejeição
de fonte diz que **recoletar não resolve** (verificar fonte/reconciliação);
gap de coleta ou dado velho sugere recoletar via skill `atualizar-ticker`.

Nem toda confiança baixa é história de dado (ADR-052, 2026-07-24):
`Decision Confidence` é composta — convicção 50%, cobertura 30%, oportunidade
20%, menos metade da penalidade de risco (`decision/engine.py`) — e cai por
construção em empresa mal avaliada. Sem campo ausente **e** com
`data_coverage` acima do piso, o bloco decompõe a nota e nomeia os dois maiores
déficits em vez de alegar cobertura baixa (AVAV 2026-07-24: cobertura 98,3,
confiança 55,6, puxada por convicção 61,4 e oportunidade 14,6). Essa nota pesa
no sinal de qualidade da carteira (`portfolio/quality.py`, 0,15) e **não é
gate** — não segura a ação sugerida no card.

`decision/cockpit.py` renderiza a mesma fila, sem nova consulta a motores, em
`output/relatorios/decision_cockpit.html` — a **página humana única** ("Atlas —
Hoje"). Desde 2026-07-22 (PR-C) é organizada por hierarquia rígida de três
níveis em vez das quatro filas cruas: **Agir agora** (EXECUTE+INVESTIGATE, no
topo), **Oportunidades** (candidatas de compra fora da carteira + gatilhos de
entrada aguardando) e **Acompanhar** (MONITOR, colapsado em `<details>` para não
competir com venda/revisão). Absorveu o conteúdo próprio do antigo
`decision_brief.html` (candidatas de compra, saúde da carteira, evidência
histórica), que foi **aposentado** — `reports/decision_brief.py` e seu teste
removidos, um único ponto de entrada humano. Responsiva, consultiva, sem
controles de mutação ou execução.

`portfolio/scenario.py` publica `output/dados/portfolio_scenario.json` e resume
o resultado no cockpit. O cenário executa matematicamente apenas os
`trade_value` oficiais de `SELL`/`TRIM`, sem sugerir substitutos: caixa pós,
turnover, pesos e concentração são passthrough/aritmética de carteira, nunca
uma nova decisão. Dashboard atualizado deliberadamente para contrato v1.3.

`decision/journal.py` registra eventos humanos explícitos (`ACCEPTED`,
`REJECTED`, `DEFERRED`) por `decision_id`, sempre com justificativa e sem apagar
histórico. Desde 2026-07-22 (PR-D, ADR-041) o cockpit registra revisões
interativamente: botões Aceitar/Adiar/Rejeitar fazem `POST /journal` na API
local (`api.server`). Endurecido para ferramenta local pessoal: bind só em
`127.0.0.1`, exige `Content-Type: application/json` (mitiga CSRF simples),
corpo limitado, escrita só em `/journal` (append-only, consultivo, nunca envia
ordem) e em `/run` (2026-07-24: a home dispara `--portfolio`/`--full` via
`api/runner.py` — allowlist de modos, trava de uma execução por vez,
`GET /run/status` para acompanhamento; só de loopback e removível com
`serve(allow_run=False)`, que é como o visor hospedado da Fase 2 deve subir). O cockpit é servido
pela própria API em `/cockpit` para os botões serem same-origin; aberto via
`file://` os botões ficam desativados com aviso. `decision/status.py` deriva o
status por decisão (`novo`/`em análise`/`decidido`/`executado`/`descartado`) de
journal+ledger a cada render, sem persistir (evita segunda fonte de verdade); o
cockpit mostra o chip por card e contagens agregadas. Dashboard contrato v1.4.
Ver `docs/DECISION_JOURNAL.md`.

`decision/execution.py` registra fills reais informados explicitamente, somente
para `SELL`/`TRIM` cujo último estado humano seja `ACCEPTED`. Quantidade, preço,
taxas, moeda e timestamps ficam no ledger append-only; não há envio de ordem ou
mutação da carteira. Dashboard v1.5. Ver `docs/EXECUTION_LEDGER.md`.

`decision/reconciliation.py` compara fills agregados por símbolo com snapshots
completos anterior/atual e classifica `CONFIRMED`, `PARTIAL`, `NOT_REFLECTED`,
`VARIANCE` ou `UNVERIFIABLE`. `portfolio/custody_history.py` captura snapshots
de quantidade idempotentes em cada relatório completo e reconcilia
automaticamente o último par consecutivo, considerando apenas fills dentro da
janela. Dashboard v1.7. Não corrige custódia nem ledger. Ver
`docs/EXECUTION_RECONCILIATION.md` e `docs/CUSTODY_HISTORY.md`.

### ⚠️ Conflitos sinalizados
1. ~~**`Decision` vs `Recommendation`**~~ **RESOLVIDO (2026-07-14):** eram dois classificadores de compra em paralelo que discordavam em ~8,9% dos nomes analisados (medido em 503 empresas do S&P500: 45 casos, 100% `Decision=Comprar/Acumular` vs `Recommendation=Manter`, sempre nas top candidatas do screener — INTU/ADBE/TROW/NVDA/QCOM etc — porque tinham Investment Score 65–70 mas Opportunity/Conviction altos). Reconciliado tornando **`Decision` a voz única de compra** e rebaixando `Recommendation` → `Score Band` (faixa descritiva, sem estrela/verbo). Motivo raiz: `Recommendation` olhava só o Investment Score final; `Decision` pondera Opportunity+Conviction+risco+deal breakers.
2. ~~**`priority.build_sell_priority` vs `portfolio.sell_rules.evaluate_sell_rules`**~~ **RESOLVIDO:** priority computava sua própria decisão binária SELL/HOLD a partir da presença de Deal Breakers, distinta das 4 regras de `sell_rules.py` — podiam divergir na mesma holding no mesmo run. Reconciliado (ADR-011, `docs/adr/ADR-011-single-sell-voice.md`): priority agora copia `action`/`reason`/`triggered_rules`/`priority` verbatim de `PortfolioReport.rebalance.actions`, nunca deriva uma segunda decisão; `deal_breakers` vira só contexto explicativo. `docs/PRIORITY_REPORT.md` atualizado para refletir o comportamento atual.

---

## 2. Fórmulas em produção

| Métrica | Fórmula implementada | Arquivo:função | Status |
|---|---|---|---|
| ROIC (live) | `tax_rate = tax_provision/pretax_income` (fallback 0.21); `NOPAT = EBIT*(1-tax_rate)`; `ROIC = NOPAT / invested_capital` (Yahoo "Invested Capital") | `analytics/fundamentals.py::_compute_roic` | Produção |
| ROIC (backtest/point-in-time) | mesmo tax_rate; `NOPAT = operating_income*(1-tax_rate)`; `invested_capital = total_debt + total_equity - cash`, `total_debt = long_term_debt + long_term_debt_current + short_term_debt` (as duas últimas ausentes no filing viram zero, não dado faltante) | `backtesting/point_in_time_fundamentals.py::derive_point_in_time_ratios` | **MEDIDO E PARCIALMENTE CORRIGIDO (2026-07-16)** — `invested_capital` reconstruído (não é mais só `long_term_debt`), mas `operating_income` como proxy de EBIT segue sendo aproximação intencional. Medido contra 3 empresas reais (S&P 500) antes/depois de incluir `long_term_debt_current`/`short_term_debt`: MSFT −3,11 p.p. → −2,86 p.p., JNJ −3,93 p.p. → −2,68 p.p. (redução real, não elimina o gap — resíduo vem do proxy de EBIT no NOPAT, não do capital investido). META ficou inalterada (−2,20 p.p.) porque a empresa genuinamente não reporta essas duas linhas separadamente no 10-K — refinamento aditivo, não piora nem ajuda quando a linha simplesmente não existe. |
| Interest Coverage (live) | `EBIT / abs(Interest Expense)` | `analytics/fundamentals.py::_compute_interest_coverage` | Produção |
| Interest Coverage (backtest) | `operating_income / abs(interest_expense)` | `backtesting/point_in_time_fundamentals.py::derive_point_in_time_ratios` | **CONFLITO A RESOLVER (parcial)** — numerador `EBIT` (Yahoo) vs `operating_income` (proxy SEC documentado), sem plano de correção (SEC não tem tag de EBIT). **Medido (2026-07-16)**: para empresas de baixa dívida, o índice pode divergir violentamente em magnitude absoluta entre os dois caminhos (META real: 74,76× ao vivo vs 186,72× point-in-time, Δ −111,96) — mas isso não muda nenhuma classificação de risco na prática hoje: ambos os valores ficam muito acima do `interest_coverage_threshold: 2.5x` de `config/sell_rules.yaml`/`deal_breakers.json`. Risco documentado, não corrigido em código — o instrumento só se torna decisivo perto do threshold, faixa onde a divergência não foi medida. |
| Altman Z | Z clássico (1968, empresa pública): `1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MktCap/TotalLiab) + 1.0*(Rev/TA)` | `analytics/fundamentals.py::_compute_altman_z` **e** `backtesting/point_in_time_valuation.py::derive_point_in_time_valuation` (espelha exatamente) | **Sem conflito de coeficientes** — só EBIT (live) vs operating_income (backtest, proxy documentado). Não existe variante Z''/privada no código — uma única fórmula clássica aplicada a todos os setores; mitigação é isenção setorial (não coeficiente alternativo), duplicada em `scoring/investment.py::apply_deal_breakers` (`altman_z_exempt_sectors`) e `portfolio/sell_rules.py` (~L213-224, `DEFAULT_SOLVENCY_EXEMPT_SECTORS`) — duas listas hardcoded separadas, risco de drift |
| Piotroski F-Score | 9 critérios clássicos, 1 ponto cada, 0-9 | `analytics/fundamentals.py::_compute_f_score` (Yahoo) e `backtesting/point_in_time_fundamentals.py::_compute_f_score_from_filings` (SEC 10-K) | Sem conflito de lógica — só fonte de dado difere |
| Investment Score | **Estágio 1**: `factors/engine.py::score_all_factors` — percentile-rank por feature (`config/features.yaml`), combinado em score por fator, depois `Σ(factor_score*weight)/Σ(weight)` com pesos de `config/model.yaml` (business 0.35, valuation 0.30, financial 0.15, timing 0.20). **Estágio 2**: `scoring/investment.py::apply_deal_breakers` sobrescreve: `Investment Score = clip(Stage1 - Risk_Penalty, 0, 100)` | `factors/engine.py`, `scoring/investment.py` | Pipeline de 2 estágios **por design** — mesma coluna sobrescrita duas vezes na mesma run; downstream (`decision/`, `models/investment_model.py`, `portfolio/quality.py`) só lê o resultado final, nada recalcula |
| Denominador do percentil (ADR-012, 2026-07-17) | Percentil empírico de cada feature contra a distribuição oficial versionada `US_MARKET_ELIGIBLE` (2.429 empresas elegíveis do screener amplo, snapshot 2026-07-13) — **não mais contra o lote da própria run**. Features com `percentile_scope: sector` em `features.yaml` usam a distribuição do setor quando há ≥5 observações (`scoring_reference_min_sector_size`), senão caem para a distribuição de mercado. Cada linha scoreada grava `reference_universe/date/count/version` | `scoring/reference.py::percentile_rank` + `load_scoring_reference`; artefato em `output/dados/scoring_reference_market.json` (path governado por `config/settings.json::scoring_reference_path`); consumido por `scoring/investment.py::score_dataframe` via `application/scoring.py::load_official_reference` | **Produção** — resolve o achado #3 da linha PR-017.x (score era rank cross-sectional relativo ao lote; swing medido de ~11–15 pt em watchlists pequenas). Fallback explícito para `CURRENT_BATCH` (comportamento antigo) se o artefato estiver ausente/incompatível — runs em fallback **não são comparáveis** com histórico de referência oficial. Ver `docs/adr/ADR-012-official-scoring-reference.md` e `docs/SCORING_MODEL.md` |

---

## 3. Thresholds e config ativos

| Config | Lido em (produção) | Valores-chave |
|---|---|---|
| `config/model.yaml` | `application/scoring.py::build_scores`; `model_version` gravado no snapshot por `application/history.py::save_history_snapshot` | `model_version: "0.3"`; pesos business 0.35 / valuation 0.30 / financial 0.15 / timing 0.20; confiança limitada a 59 quando falta feature `required` **de verdade** (status `missing`/`unavailable`/`invalid` — `stale` não conta mais, ver seção 6) |
| `config/features.yaml` | `factors/engine.py::score_all_factors` via `scoring/investment.py`; `application/scoring.py::audit_feature_coverage`; `scoring/reference.py::load_feature_scopes` (`percentile_scope` por feature, ADR-012) | pesos/`required` por métrica, fonte de verdade desde PR-017.3; agora também governa escopo setorial do percentil |
| `config/data_quality.yaml` | scoring, `analytics/data_quality.py` e `providers/evidence.py` | qualidade por fonte; frescor 100 até 7 dias, 70 até 35 (mercado/analista/identidade); **fundamentos usam a cadência do emissor** — `period_cadence_categories`, `default_reporting_period_days: 91`, `filing_lag_days: 45`, `max_reporting_period_days: 400` (ADR-047); aplicabilidade setorial explícita por campo |
| `config/deal_breakers.json` | `scoring/investment.py::apply_deal_breakers` (via `build_scores`) | limites observados por risco e penalidade de incerteza de 3 por evidência ausente, limitada a 10 |
| `config/sell_rules.yaml` | `portfolio.sell_rules.load_sell_rules_policy`, chamado por `application/history.py::load_sell_rules_policy` e default em `portfolio/pipeline.py` | `confidence_gate` (score_coverage≥60, confidence≥60); `distress`, `valuation_stretch` (target_upside<-10%), `fundamental_decay` (f_score_drop≥2, roic_drop≥20%), `relative_decay` (percentil<40); `escalation` (trim@1, sell@2 gatilhos, trim_fraction 50%) |
| `config/watchlist_auto.yaml` | `watchlist.auto_policy.load_watchlist_auto_policy`, chamado por `application/intelligence.py::IntelligenceApplicationService.run_watchlist_auto_curation`, dentro de `IntelligenceStage` (todo run `--full`/`--portfolio`) | `enabled: true`; `selection.top_n: 30`, `selection.qualifying_decisions: [STRONG_BUY, BUY, ACCUMULATE]`, `selection.min_confidence_score: 60.0`; `exit.investment_score_threshold: 40.0`; `safeguards.protect_portfolio_holdings`/`protect_manual_entries: true` |
| `config/ranking.yaml` | `application/scoring.py::generate_ranking_report` | mínimos 70 para confiança, cobertura, qualidade da fonte e frescor; requer features críticas completas e ausência de deal breaker |
| `config/universe.yaml` | `application/scoring.py::generate_universe_report` | min market cap $1B, min price $5, min volume 100k, EQUITY/USD/US |
| `config/settings.json` | `run_all.py`, `application/collection.py` e `universe/collector.py` | timeout 30s, 2 retries exponenciais, 2 req/s, campos críticos, snapshots brutos; **referência oficial de scoring** (`scoring_reference_path` → `output/dados/scoring_reference_market.json`, `scoring_reference_universe_id: US_MARKET_ELIGIBLE`, `scoring_reference_version: 1`, `scoring_reference_min_sector_size: 5`); **fontes secundárias** habilitadas por flag (`sec_secondary_enabled`, `fmp_secondary_enabled`, `massive_secondary_enabled`) + orçamento de prefetch FMP (`fmp_daily_call_limit: 250`, reserva interativa de 25 chamadas) |
| `config/provider_secrets.json` | `application/collection.py` (via builders em `providers/sec_companyfacts.py`, `providers/fmp.py`, `providers/massive.py`) | **gitignored** (linha 54 do .gitignore); contém SEC User-Agent, chave FMP e chave Massive; criar a partir de `provider_secrets.example.json`. Flag secundária habilitada sem segredo correspondente gera warning explícito, nunca falha silenciosa |
| `config/model_portfolio.yaml` | **só** `portfolio/model_portfolio.py` (CLI standalone), **`run_all.py` não chama** | target_positions 20, max_position_weight 5%, max_sector_weight 20% |
| `config/portfolio_validation.yaml` | **só** default arg de `backtesting/portfolio_validation.py::main` (CLI manual) | — |
| `config/universe_adr.yaml` | **sem caller hardcoded** — lido só quando o operador passa `--universe-policy config/universe_adr.yaml` ao CLI `portfolio/model_portfolio.py` (rodado de verdade: 501 elegíveis / 219 candidatos) | mesmo piso $300M do market, `allowed_countries: ["*"]`, `excluded_countries: [United States]` |
| `config/universe_market.yaml` | **sem caller hardcoded** — idem, via `--universe-policy` e `universe.collector --market` (rodado de verdade: 2.429 elegíveis / 794 candidatos no rerun de evidência 2026-07-17; também é a origem do artefato de referência ADR-012) | NASDAQ Trader, min market cap $300M |
| `config/historical_execution.yaml` | **existe mas não é lido em produção** — loader só chamado em testes | — |

---

## 4. Gating e cobertura

| Item | Status | Evidência |
|---|---|---|
| cobertura/qualidade/confiança | **Separadas** | `Data Coverage` pondera a contribuição real de cada feature (`factors/engine.py::metric_available`, ainda desconta `stale` normalmente); `Model Confidence` aplica teto 59 só quando uma feature `required` está genuinamente ausente (`missing`/`unavailable`/`invalid` — `factors/engine.py::metric_has_value`, `stale` não trava mais o teto desde 2026-07-20); `Source Quality` e `Data Freshness` são sinais governados independentes. Aliases legados: `Score Coverage` e `Confidence Score`. O ranking canônico exige os quatro gates; ver ADR-013. |
| `model_version` no snapshot | **Existe** | `storage/history_db.py` tabela `snapshots`, coluna `model_version TEXT NOT NULL DEFAULT 'legacy'`, populada por `application/history.py::save_history_snapshot` a partir de `model.yaml` |
| Snapshot grava features individuais? | **Sim, não só o score** | Tabela `snapshots` (`storage/history_db.py`): `business_score, valuation_score, financial_score, timing_score, investment_score, opportunity_score, confidence_score, model_version, altman_z, interest_coverage, target_upside, f_score_annual, roic, score_coverage, earnings_date, quantity, is_candidate, recommendation`. Tabela `outcome_snapshots` espelha estrutura similar |
| Snapshot grava proveniência e evidência? | **Sim (2026-07-17)** | Colunas novas em `snapshots` (mesmo padrão de migração aditiva): `reference_universe/reference_date/reference_count/reference_version` (qual referência ADR-012 pontuou a linha — distingue run oficial de fallback `CURRENT_BATCH`), `source_quality`, `data_freshness`, `missing_required_features`, `risk_evidence_missing`, `observed_risk_penalty`, `risk_uncertainty_penalty` (decomposição ADR-013 do Risk Penalty), `field_evidence_json`, `raw_snapshot_hash`, `raw_snapshot_path` (evidência imutável por campo, `storage/raw_snapshots.py` — snapshot bruto content-addressed, ADR-014) |
| Gating setorial | **Existe, mas duplicado em 2 lugares** | `portfolio/sell_rules.py::_distress` (L197-260): `altman_z_exempt_sectors`/`interest_coverage_exempt_sectors` = Utilities/Financial Services/Banks/Insurance (`DEFAULT_SOLVENCY_EXEMPT_SECTORS`); `current_ratio_exempt_sectors` = Software. Replicado independentemente em `scoring/investment.py::apply_deal_breakers`. Não há gating setorial em `decision/` |

---

## 5. Universos e proveniência

| Universo | Config | Membership | Cadência |
|---|---|---|---|
| Portfolio | `config/portfolio.csv` | holdings reais do usuário | manual |
| Watchlist | `config/watchlist.csv` | curadoria manual | manual |
| Research (S&P 500) | `config/universe.yaml` + `research_universe.csv` | scrape Wikipedia S&P 500, min $1B mkt cap | manual, `python -m universe.sources` |
| Broad market | `config/universe_market.yaml` + `research_universe_market.csv` (~7.093) | NASDAQ Trader listas, min $300M mkt cap | manual, `universe.collector --market` |
| Scoring reference (US_MARKET_ELIGIBLE) | `output/dados/scoring_reference_market.json` (~2.930) | elegíveis do broad market **de qualquer domicílio** (ADR-044: inclui ADRs/estrangeiros US-listed); base cross-sectional dos percentis | reconstruído no build de model-portfolio de mercado (`portfolio/model_portfolio.py`) |
| ADR | `config/universe_adr.yaml` | reusa snapshot broad-market, filtra `excluded_countries:[United States]` | sem coleta própria |

**Amostras e qual atualizar**: as diferentes amostras (S&P 500 ~503 profundo, broad market ~7.093, referência elegível ~2.429, portfolio+watchlist ~57) e o comando de refresh de cada uma estão consolidados numa tabela em `docs/UNIVERSE_SOURCES.md` ("Sample overview"). O `reference_count` numa empresa (ex.: 2.429) é o tamanho da referência de score, **não** o que foi coletado a fundo naquele run. Broad market + referência foram construídos por último em 2026-07-13/17 — refresh é tarefa periódica.

**Origin**: atribuído em `application/collection.py::merge_watchlist_with_portfolio` (wrapper homônimo preservado em `run_all.py`) — default `watchlist`, sobrescrito para `portfolio` se símbolo está em `portfolio.csv`. Prioridade `portfolio > watchlist > universe`; `ORIGIN_UNIVERSE` é constante definida mas **não wireada** neste merge. Propagado read-only por `portfolio/pipeline.py::enrich_portfolio_from_analysis`, checado em `portfolio/rebalance.py` (sell-side) e `ranking/pipeline.py` (`already_held`, buy-side). Contrato coberto por `tests/test_origin_provenance.py`, verificado batendo com a implementação real.

**Cadência não é agendada por código** — nenhum cron/scheduler encontrado; `docs/UNIVERSE_COLLECTION.md:64` e `docs/ROADMAP.md:69`/`docs/BACKLOG.md:336` confirmam: "Scheduling (deferred until analytical validation)". `run_all.py` não tem flag `--universe`; screeners broad/ADR/S&P500 rodam via módulos separados (`universe.collector`, `universe.sources`).

**Resultado de Mercado Amplo/ADR surfaceado (não re-coletado) no Atlas Report** — a coleta em si continua manual/separada (milhares de símbolos, ~horas de runtime, ver acima); `reports/atlas_report/broad_screener.py::load_broad_screener_summary` só LÊ `output/dados/research_ranking_report_market.json`/`_adr.json` (o mesmo arquivo que `ranking/pipeline.py` já persiste para os 3 screeners, consumido também por `reports/research_html.py`) e resume idade da coleta + top candidatos diversificados por setor. `run_all.py::main` passa esses paths para `build_report_context` só em `mode == "full"`. Alerta de "coleta desatualizada" quando `age_days > 35` (folga sobre a cadência mensal pretendida). Arquivo ausente/ilegível vira seção "não incluído", nunca erro.

---

## 6. Pendências conhecidas

- **Auditoria do ADR-032 (proteção contra o lock de escrita do OneDrive) não foi completa (achado 2026-07-21).** Além dos 11 pontos corrigidos em 2026-07-18, mais 8 escritores gravam com `write_text()` puro em vez de `storage/atomic_write.py`: `backtesting/total_return_evidence.py`, `backtesting/execution_evidence.py`, `backtesting/walk_forward.py`, `analytics/performance_validation.py`, `universe/report.py`, `watchlist/report.py`, `portfolio/model_portfolio.py`, `portfolio/pipeline.py` (todos anteriores a 07-18, nunca pegos pela auditoria original). Um nono ponto (`backtesting/readiness.py`, novo) foi corrigido na mesma sessão em que foi achado. Não corrigido em massa agora — escopo maior que a tarefa em andamento; próxima sessão que tocar esses arquivos deve aplicar `atomic_write_json`/`replace_with_retry`.
- **"Catálogo de venda"**: nenhuma ocorrência do termo em `docs/`. O que existe hoje cobrindo esse espaço: `portfolio/sell_rules.py` + `config/sell_rules.yaml`, `watchlist/triggers.py`, `decision/engine.py`. Se specs recentes assumem 4 pré-requisitos nomeados dessa forma, não foram encontrados documentados sob esse nome — checar se é terminologia de outra sessão/conversa antes de assumir que falta algo.
- ~~Reconciliação priority/ vs decision/~~ **RESOLVIDA** — ver conflito #2 (seção 1) e ADR-011.
- **Conflito Altman Z (clássico vs Z'')**: não existe no código — só uma fórmula clássica é usada, com isenção setorial (não coeficiente alternativo) como mitigação. Nenhuma menção em `docs/` a um conflito de variantes. O que existe de fato é a fórmula clássica aplicada uniformemente mesmo a setores onde ela é estruturalmente enganosa (mitigado só por isenção, não por Z'' apropriado). **A duplicação das listas de setores isentos entre `scoring/investment.py` (`config/deal_breakers.json`) e `portfolio/sell_rules.py` (`config/sell_rules.yaml`) foi reconciliada** (mesmo conteúdo — Utilities/Financial Services/Banks/Insurance/Biotechnology para Altman Z, Software/Tobacco para liquidez, mais `net_debt_ebitda_exempt_sectors`/`f_score_exempt_sectors` novos no lado do score) — continuam sendo dois arquivos com nomes de chave próprios (consumidores diferentes), não uma fonte única, então ainda cabe a um editor futuro atualizar os dois lados manualmente. **Teste de equivalência adicionado (2026-07-18)**: `tests/test_governed_config.py::test_exempt_sectors_match_between_deal_breakers_and_sell_rules` trava os dois arquivos JSON/YAML batendo; `test_sell_rules_python_defaults_match_deal_breakers` trava os fallbacks `DEFAULT_*` hardcoded em `portfolio/sell_rules.py` contra o mesmo JSON. Achado real ao escrever o teste: os fallbacks Python estavam desatualizados (`DEFAULT_SOLVENCY_EXEMPT_SECTORS` sem "Biotechnology", `DEFAULT_LIQUIDITY_EXEMPT_SECTORS` sem "Tobacco", mais dois defaults de `net_debt_ebitda`/`f_score` que eram `()` vazio) — inofensivo hoje porque `sell_rules.yaml` sempre especifica as chaves (o fallback nunca era de fato lido), mas divergiria silenciosamente do `deal_breakers.json` no dia em que alguém remover uma chave do YAML. Corrigido junto com o teste.
- **ROIC / Interest Coverage live vs backtest**: mesma lógica de tax-rate, mas `invested_capital` e o proxy de EBIT divergem entre `analytics/fundamentals.py` (live) e `backtesting/point_in_time_fundamentals.py` (point-in-time SEC). Diferença é documentada como aproximação intencional no código-fonte — mesma empresa pode pontuar diferente ao vivo vs. em replay de backtest. **Teste de equivalência adicionado (2026-07-18)**: `tests/test_live_vs_point_in_time_ratios.py` prova que as duas fórmulas concordam exatamente quando `EBIT == operating_income` (sem gap de proxy) e os componentes de `invested_capital` descrevem o mesmo valor em dólar — isolando a hipótese de que a divergência medida vem só do proxy documentado, não de um bug de fórmula escondido. Segundo teste prova que o gap resultante rastreia exatamente a diferença EBIT vs operating_income introduzida, nada além disso.
- ~~`watchlist/promote.py`: gate manual por design, não lacuna~~ **DECISÃO SUPERSEDIDA (2026-07-21)**: em 2026-07-18 foi confirmado com o usuário que o gate era manual por design. Em 2026-07-21 o usuário pediu explicitamente um fluxo automático **adicional** ao manual — `run_all.py` passou a gravar em `config/watchlist.csv` em todo run `--full`/`--portfolio`, via `watchlist/auto_curation.py::run_auto_curation` (chamado dentro de `IntelligenceStage`, antes de `generate_watchlist_report`). O gate manual (CLI/planilha) continua existindo sem nenhuma mudança de comportamento — o novo caminho é estritamente adicional, não substitui o antigo. Governado por `config/watchlist_auto.yaml` (`WatchlistAutoPolicy`, `watchlist/auto_policy.py`, mesmo padrão de `portfolio/sell_rules.py`): `enabled: true`, `selection.top_n: 30`, `selection.qualifying_decisions: [STRONG_BUY, BUY, ACCUMULATE]` (Decision **estimada** via `decision/policy.py::evaluate_decision(..., risk_penalty=0.0, ...)` — aproximação documentada, pois o risco real só existe para nomes já pontuados na carteira/watchlist, não para o screener amplo lido aqui; `selection.min_confidence_score: 60.0` é a salvaguarda confirmada contra essa aproximação), `exit.investment_score_threshold: 40.0`. Salvaguardas de exclusão (`safeguards.protect_portfolio_holdings`/`protect_manual_entries`, ambas `true`): nunca remove holding real (`origin=="portfolio"` em `historical.frame`) nem entrada `source=="manual"` — só remove o que o próprio fluxo automático incluiu (nova coluna `source: manual|auto` em `config/watchlist.csv`, retrocompatível — as 41 linhas antigas sem essa coluna carregam como `manual`). Resultado surfaceado em 3 lugares (nunca mutação silenciosa): console (`CompletionStage`, linhas `[AUTO-IN]`/`[AUTO-OUT]`), `output/dados/watchlist_report.json::auto_curation`, e a seção "Curadoria Automática da Watchlist" do Atlas Report. Decisão registrada em `docs/adr/ADR-036-watchlist-auto-curation.md`. `watchlist/candidates_workbook.py` + `watchlist/apply_candidates_workbook.py` (planilha Excel, mesmo `promote_to_watchlist` por baixo) seguem existindo sem mudança — ver `docs/WATCHLIST_WORKBOOK.md`.
- ~~Score cross-sectional relativo ao lote da run (achado #3 da linha PR-017.x, ficou DORMANT)~~ **RESOLVIDO (2026-07-17, ADR-012)**: scores ao vivo agora usam a distribuição oficial versionada `US_MARKET_ELIGIBLE` como denominador do percentil (ver seção 2). O `calculate_watchlist_drift` (PR-021) segue existindo, mas o problema estrutural que ele mitigava foi eliminado no caminho oficial; permanece relevante só para runs em fallback `CURRENT_BATCH`. Replay histórico (`backtesting/walk_forward.py`) continua cutoff-local por design.
- **Cobertura de EV amplo travada na cota gratuita do FMP**: o scan real de 2026-07-17 achou market cap/float para 67/2.429 símbolos elegíveis e enterprise evidence para 6 antes do teto de 225 chamadas/dia — limite de entitlement do plano Basic, não bug. Massive Float cobre 2.364/2.429 (97,3%) para short float; os 64 gaps restantes são explicitamente `secondary_unavailable`, nunca substituídos por proxy. Próximo passo já definido em `docs/ATLAS_CONTEXT.md`: compor market cap via Massive Grouped Daily + SEC shares, aposentando o caminho de Ticker Details (~8h de runtime amplo).
- **7 holdings reais (BNTX, BRK-B, BTI, JBS, PAM, SGML, YPF) seguem em REVISAR mesmo após o fix do ADR-037 — investigado, não é bug.** `missing_required_features` é `Nenhum` em todas; o gate de 60/60 barra por `data_coverage`/`confidence` genuinamente baixos (53,5–58,8), causados por dois fatores medidos: (1) volume maior de campos `stale` (24–28 vs 20 no LMT, que passa) — natural do calendário de reporte trimestral de ADRs/empresas estrangeiras; (2) `market_cap`/`enterprise_value` **corretamente invalidados** pela reconciliação (`reconcile_critical_fields`, status `invalid`/`"critical sources disagree"`) quando Yahoo e Finnhub discordam além da tolerância de 5% — medido ao vivo: YPF tem EV Yahoo de US$12,87 **trilhões** (bug de conversão cambial, provavelmente ARS→USD na dívida) vs Finnhub US$46,1bi; PAM tem o inverso, Finnhub retorna US$7 trilhões de market cap contra US$4,7bi do Yahoo; BTI e JBS divergem 3–5×. Ambos os vendors quebram, ora um ora outro, em nomes que reportam em moeda estrangeira — o mecanismo de reconciliação já existente rejeita corretamente o campo em vez de confiar cegamente numa fonte (mesma proteção que evitou o ROE de −193% do IBRX vazar mais cedo hoje). **Decisão: não abaixar o gate nem preferir uma fonte só** — REVISAR é o resultado correto quando duas fontes independentes discordam violentamente, não falta de dado a ser contornada.
  **Protocolo formal para moeda de reporte estrangeira (pedido explícito do usuário, ADR-037 adendo 2):** medi se `financialCurrency` do Yahoo seria um identificador confiável — não é (PAM/JBS/SGML aparecem `financialCurrency=USD` apesar de operar em ARS/BRL; ASML é EUR e nunca teve problema), então não há hoje um sinal de origem confiável para prever quais nomes vão quebrar. A defesa adotada é uma **guarda de plausibilidade absoluta** em `enterprise_value` (`providers/yahoo.py::_enterprise_value_implausible`, rejeita quando `EV/MarketCap` foge de `[-5×, 20×]`, calibrado contra os valores reais dos 18 holdings — BTI 5,36×/FMC 4,0×/BRK-B −0,25× preservados, ASML 53,6×/YPF 639,8× rejeitados), que protege mesmo quando só uma fonte está disponível para o campo — diferente da reconciliação cross-source, que só pega o erro se houver uma segunda fonte para discordar. **Achado real da calibração**: ASML tinha `enterpriseToEbitda=2750×` (EV Yahoo de US$37,1 trilhões) alimentando o fator de valuation **sem estar em REVISAR** — corrompendo o score silenciosamente, sem que ninguém percebesse, porque não havia segunda fonte contradizendo. `ev_ebit` é derivado pelo próprio Atlas (`enterprise_value/ebit`) e herda a correção automaticamente. Terceira fonte como árbitro (Massive/SEC) foi cogitada e descartada por ora — cobertura SEC XBRL de emissores estrangeiros já documentada como fraca acima.
- **Referência ADR-012 congelada no snapshot 2026-07-13**: o artefato `scoring_reference_market.json` tem `reference_date: 2026-07-13`; não há processo automático de renovação (coerente com "scheduling deferred"), mas percentis oficiais envelhecem junto com a coleta ampla — renovar a referência exige rodar a coleta de mercado e regenerar o artefato conscientemente (nova `reference_version` se a política mudar).
- ~~PE ausente por prejuízo travava o gate de confiança igual a falha de coleta~~ **RESOLVIDO (2026-07-21, ADR-037)**: rodando a carteira real com as teses preenchidas (motor de venda destravado), 12/18 posições travavam em `REVISAR` pelo `confidence_gate` (60/60 de `sell_rules.yaml`); a causa dominante era **PE (feature `required`) marcado como `missing`** em 7 nomes deficitários (FMC, IBRX, BNTX, SGML, CLF, AVAV, YPF) — medido no `field_evidence_json`, todos com `ev_ebitda`/`forward_pe` presentes, só sem PE trailing porque o lucro trailing é não-positivo (razão indefinida, não falha de coleta). Corrigido classificando esse caso como `not_applicable` na origem (`providers/yahoo.py::_trailing_pe_structurally_absent`, só quando `trailingEps`/`netIncomeToCommon`/`profitMargins ≤ 0` — ausência sem sinal de earnings permanece `missing`, conservador). O motor já tratava `NOT_APPLICABLE` corretamente (exclui do denominador de cobertura e do laço de required-feature) — nenhuma mudança em `factors/engine.py`. Na mesma decisão, **EV/EBITDA virou o múltiplo de valuation dominante** (`config/features.yaml`+`factors/valuation.py`: `pe 0.20→0.10`, `ev_ebitda 0.20→0.30`, soma do bloco = 1.0), como substituto natural do PE quando ele é indefinido. `tests/test_yahoo_provider_contract.py::test_trailing_pe_marked_not_applicable_when_earnings_non_positive`.
  **Adendo, mesma sessão — `roe` (também `required`) travava JNJ e IBRX por motivos opostos**: JNJ tem `returnOnEquity` ausente do Yahoo por gap de coleta genuíno (patrimônio +US$81,5bi, lucro TTM positivo, ROE real ~26–33%); IBRX tem a mesma ausência mas com patrimônio **negativo** (−US$500mi, déficit acumulado) — dividir lucro por patrimônio negativo produz um número matematicamente enganoso (confirmado ao vivo: Finnhub `roeTTM=-193,29%`, não é gap de coleta, é a razão em si sem sentido econômico). Discriminado por `providers/yahoo.py::_stockholders_equity`: `equity≤0` → `not_applicable` (mesmo mecanismo do PE, nunca reconciliado — `reconcile_critical_fields` não sobrescreve `not_applicable`); `equity>0` → `roe` fica `missing` (reconciliável) e `providers/finnhub.py::FinnhubMarketDataProvider` passa a expor `roe` (`metric.roeTTM`, convertido de percentual→fração), adicionado a `provider_critical_fields` (`config/settings.json` + fallback em `application/collection.py`) para entrar na cadeia de reconciliação já existente (Finnhub é o primeiro secondary fetcher). Ver ADR-037 (adendo).
- ~~`stale` travava o gate de required-feature igual a `missing`~~ **RESOLVIDO (2026-07-20)**: `factors/engine.py::metric_available` tratava status `stale` (valor real, só mais velho que os 35 dias de `data_quality.yaml::freshness.acceptable_days`) exatamente como `missing`/`unavailable` ao montar `Missing Required Features` — bastava **um** dos 9 features `required` (ROE, Net Margin, PE, Price/Book, RSI 14, Momentum 3M/6M/12M, Distance 52W High) ficar `stale` para travar `Model Confidence` em 59, um ponto abaixo do `confidence_gate: 60` de `sell_rules.yaml` — bloqueando toda decisão de venda/compra do holding, mesmo com o resto dos dados bons. **Achado real rodando a carteira em produção (2026-07-20, primeiro `--portfolio` desde 2026-07-16)**: ROE/Net Margin do Yahoo — cadência trimestral/anual, sempre mais velhos que a janela de 35 dias na maior parte de cada trimestre — estavam `stale` para **57/57 símbolos** (50 com só os dois, 7 também com `valuation:pe`), travando `Portfolio Score` em POOR (39,1) e forçando os 18 holdings reais para REVISAR (0 buy/sell/hold/trim). O rastreamento de staleness por campo (ADR-014) só existe desde 2026-07-17 — nunca tinha sido exercitado contra a carteira real antes deste run. Corrigido separando as duas semânticas: `metric_has_value()` (nova, só usada no loop de required-feature) conta `present` **e** `stale` como "tem valor"; `metric_available()` (cobertura/`Data Coverage`) continua descontando `stale` normalmente — frescor baixo ainda reduz `Data Coverage`, só parou de duplicar essa penalidade travando o teto de confiança. `tests/test_confidence_score.py::test_stale_required_feature_does_not_cap_confidence` + `test_missing_required_feature_still_caps_confidence` (regressão: ausência genuína continua travando).

---

## 7. Relatório HTML (Report v0)

| Item | Estado |
|---|---|
| Existe desde | PR-022 (`feat(reports): self-contained HTML report + one-pager, 3 run modes`), **já em produção antes desta sessão** — não foi listado na v1 deste STATUS.md, correção aplicada aqui |
| Módulos | `reports/atlas_report/context.py` (monta `ReportContext` só lendo o que os motores já produziram), `render.py` (HTML self-contido, CSS inline, zero dependência externa), `write.py` (grava arquivo), `one_pager.py` (relatório por ticker, `--ticker`), `diagnostics.py` (extrai alertas de conflito do próprio STATUS.md), `ticker_detail.py`+`formulas.py`+`svg.py` (seção de detalhe por ticker embutida no relatório principal, ver abaixo) |
| Regra central | O relatório não calcula nem decide nada — `Decision`/`action`/scores vêm prontos dos motores; ausência de razão textual cai em fallback `"razão: motor pendente"`, nunca inventado |
| Wiring | Estágio de relatório em `orchestration/pipeline.py` chama `application/intelligence.py::build_report_context` + `render_and_write_report` para os modos `--full` e `--portfolio`; `--ticker` usa `one_pager.py` via `application/ticker.py` |
| Saída | `output/relatorios/atlas_report_AAAA-MM-DD.html` + `output/relatorios/atlas_report_latest.html` |
| Seção Diagnóstico | Lê o texto de STATUS.md em runtime (`run_all.py::_read_status_md`) e conta marcadores que o próprio documento já usa (`### ⚠️ Conflitos sinalizados`, `CONFLITO A RESOLVER` em linhas de tabela) — exibe alerta "N conflito(s) sinalizado(s) em STATUS.md", nunca reinterpreta o conteúdo |
| Seção Detalhe por ativo | Cada símbolo de carteira/watchlist ganha uma seção ancorada (`ticker-SYMBOL`) com: decomposição do score (mesma função `compute_symbol_contributions` do one-pager) + fórmula/inputs brutos/interpretação por threshold já em produção (`formulas.py`, sincronizado a mão com a seção 2 deste arquivo); status de cada regra de venda (`rule_results` do `sell_rules.py`, só quando a posição é holding real); sparkline por métrica só para colunas de fato persistidas em `snapshots` (seção 4); tese da posição com idade e alerta quando `fundamental_decay` disparou. Símbolos nas tabelas de Carteira/Watchlist linkam para a âncora. **Sem link externo** (Yahoo Finance foi cogitado e removido antes do merge — quebrava o contrato de zero dependência externa) |
| Testes | `tests/test_atlas_report_*.py` — fixture renderiza todas as seções, seção sem dado mostra "não incluído neste run", teste de contrato (pill exibido == `action` do motor), teste que falha se houver `http://`/`https://` em `src`/`href` (agora com uma fixture que de fato popula `ticker_details`, senão o teste nunca exercitava a seção), teste de fallback "motor pendente", teste de alerta de conflito |

---

## 8. Separação `output/relatorios/` vs `output/dados/`

O usuário observou que os JSONs em `output/` (contrato interno entre motor e
camada de relatório, alguns chegando a 3-4MB) não são pensados para abrir
direto — só o HTML/Excel/Markdown/CSV são. `output/` passou a ter dois
subdiretórios fixos:

| Diretório | Conteúdo | Quem grava |
|---|---|---|
| `output/relatorios/` | **Para o usuário abrir**: `atlas_report_*.html`, `atlas_report_latest.html`, `atlas_report_{SYMBOL}_*.html` (one-pager), `morning_brief.md`, `latest.xlsx` + `history/atlas_snapshot_*.xlsx`, `research_report*.html`, `research_screeners_combined*.xlsx`, `research_candidates*.csv` | `run_all.py` (`OUTPUT_REPORTS`) e `portfolio/model_portfolio.py` (`reports_dir`) |
| `output/dados/` | **Contrato interno, não pensado para leitura direta**: `portfolio_report.json`, `outcome_report.json`, `dashboard.json`, `priority_report.json`, `performance_validation.json`, `universe_report.json`, `ranking_report.json`, `watchlist_report.json`, `research_universe_report*.json`, `research_ranking_report*.json`, `model_portfolio_report*.json` | `run_all.py` (`OUTPUT_DATA`) e `portfolio/model_portfolio.py` (`data_dir`) |

Consumidores read-only atualizados para o novo local em `output/dados/`:
`watchlist/promote.py::DEFAULT_SOURCE_PATH`, `priority/cli.py` (2 defaults),
`api/resources.py::DEFAULT_DASHBOARD_PATH`. `reports/research_excel.py`
(combina os 3 screeners) lê de `<output_dir>/dados/` e escreve o Excel
combinado em `<output_dir>/relatorios/`.

Efeito colateral corrigido: `reports/excel.py::write_latest_and_history`
derivava o caminho do `atlas_history.db` via `output_dir.parent` (assumia
que `output_dir` era filho direto do ROOT do projeto) — quebraria
silenciosamente ao mover o Excel para `output/relatorios/`. Agora recebe
`database_path` como parâmetro explícito (`run_all.py` passa
`HISTORY_DATABASE`), decoplado da localização do diretório de saída.

- ~~Fundamento no meio do ciclo de divulgação virava `stale` e derrubava a confiança~~ **RESOLVIDO (2026-07-24, ADR-047)**: causa raiz do fenômeno que o `metric_has_value` (2026-07-20, abaixo) só mitigara no gate de required-feature — a cobertura seguia penalizada. Reportado pelo usuário sobre AVAV (Confiança 37,5 e "recolete o ticker" **logo após atualização completa**; 20 dos 83 campos `desatualizado`, todos de 30/04/2026). Medição na carteira real (324 campos `STALE`, 18 posições) mostrou idades **discretas**, não contínuas — 85d (=30/04, trimestre real), **205d (=31/12, exercício ANUAL)**, 208d (JNJ, 52/53 semanas), 389d (MSFT, FY junho) — com mediana em 205: o grosso não era defasagem de publicação, era o quadro **anual**. Dois defeitos: (1) `providers/yahoo.py` datava com `_statement_date(financials/cashflow)` (**anuais**) valores que vinham de `info` e já são **TTM** — verificado no snapshot bruto do MSFT: `ebitda` 184,457bi no registro contra 160,165bi no FY2025, e `net_margin` 0,3934 contra 0,3615 — deixando o fluxo do MSFT carimbado **um ano inteiro** atrás do balanço (2025-06-30 vs 2026-03-31); (2) `providers/evidence.py` aplicava a janela de 35 dias (calibrada pela cadência da **nossa coleta**, conforme o próprio comentário do YAML) a todo campo, sendo que um trimestre dura ~91 dias e um semestral ~182. **Nenhum dos 324 campos era falha de coleta** — inclusive BTI, que reporta semestralmente (Reino Unido) e cuja cadência de **182 dias** o novo `_reporting_period_days` detecta sozinho, sem config por ticker. Corrigido datando o TTM por `mostRecentQuarter` (nenhum **valor** muda — já eram TTM) e medindo a cadência do `quarterly_balance_sheet`, ambos já disponíveis: buscar os quadros trimestrais de resultado/caixa levaria `fetch_symbol` de 6 para 8 requisições por símbolo (+33% sobre a base da ADR-046, com a coleta ampla já no teto de 2 req/s) e, medido em 4 emissores, não acrescentava nada — cadência idêntica, datas idênticas salvo 2 dias no JNJ, e no BTI o quadro trimestral voltou vazio enquanto `mostRecentQuarter` respondeu e trocando, só para `fundamentals`, a janela cronológica por `reporting_period_days + filing_lag_days`, medido do espaçamento entre períodos do próprio emissor. Verificado ao vivo sem escrita em histórico: AVAV/MSFT/BTI/JNJ de 20/20/20/8 campos `stale` para **0**. 1204 testes verdes, 7 novos fixando os casos medidos; pin de `test_governed_config.py` atualizado. **Orientação ao usuário corrigida na mesma sessão**: `decision/cockpit.py::_confidence_explanation` afirmava "recolete {ticker}" para toda baixa confiança sem divergência de fonte — no AVAV, uma ação inútil, porque `missing_evidence` (features obrigatórias + evidência de risco) vinha **vazio** e a mensagem caía num ramo genérico que mesmo assim asseverava o remédio. Novo terceiro ramo: sem campo obrigatório ausente, aponta a página da empresa (`/company/SYM`, ADR-045) em vez de afirmar que recoletar resolve. `reports/evidence_reasons.py::_status_phrase` traduz o `detail` novo — `stale` num fundamento agora significa "o período seguinte já venceu o prazo de divulgação e não foi coletado", que é exatamente o caso em que recoletar resolve.

- ~~`roe` anulado por divergência de definição entre fontes, travando confiança em 59~~ **RESOLVIDO (2026-07-24, ADR-048)**: efeito colateral exposto pela ADR-047 e achado na recoleta real de validação. Enquanto `roe` vivia permanentemente `stale`, `reconcile_critical_fields` **nunca o reconciliava** (trata `STALE` como primário inutilizável) — a divergência existia desde sempre, invisível. Datado corretamente, virou `PRESENT`, entrou na checagem cruzada pela primeira vez e foi anulado como `INVALID` ("critical sources disagree"); e `INVALID`, ao contrário de `STALE`, não conta em `metric_has_value`, disparando o `missing_required_cap: 59`. **Mudou decisão**: ASML 73,0→59,0 e CLF 76,4→59,0, com o **SELL do CLF virando REVISAR**. A divergência é definicional, não erro: ASML Yahoo 0,5394 vs Finnhub 0,4468 (17%), CLF −0,1386 vs −0,2091 (34%) — o `returnOnEquity` do Yahoo é TTM sobre patrimônio, o secundário usa outra base de período/patrimônio; exigir 5% entre definições distintas é inatingível por construção. Mesmo remédio do ADR-042 (`total_debt`) e ADR-038 (`market_cap`/`short_float`): `roe` sai de `provider_critical_fields` — **um lugar só**, `config/settings.json`, já que `yahoo.py::DEFAULT_CRITICAL_FIELDS` e o default do `universe/collector.py` nunca o tiveram. Validado com recoleta real: ASML→94,8, CLF→93,8, SELL do CLF de volta; confiança média 64,8→92,6 (ADR-047)→**94,6**, abaixo do gate 15→2→**1**. 1206 testes verdes, 2 novos (um deles guarda de mecanismo: se alguém redeclarar `roe` crítico, a anulação volta e o teste aponta). **Não confundir com a intermitência do JNJ** (caiu a 59 na mesma recoleta por `roe` ausente): remover campo da reconciliação só evita anulação, nunca cria ausência — medido `present` até 11:36, `missing` às 11:47, e 3 buscas seguidas ao provider devolvendo `None`; é o Yahoo oscilando, o mesmo gap do adendo ADR-037. Fica aberto.

- ~~Lacuna de cobertura do fornecedor travava confiança abaixo do gate~~ **RESOLVIDO (2026-07-24, ADR-049)**: JNJ ficava em confiança 59 (abaixo do gate de 70, bloqueando decisão) por `business:roe` ausente. Causa medida: o `info` do Yahoo para o JNJ tem **173 chaves e não inclui** `returnOnEquity`/`freeCashflow`/`operatingCashflow`/`quickRatio`/`currentRatio` (MSFT tem 180 com todas) — chaves **ausentes do payload**, não nulas, persistentes em 3 buscas seguidas; mesma lacuna do adendo ADR-037, à época sem solução. Escopo: 1/18 da carteira, 6/117 coletados. Os insumos já estavam nas demonstrações baixadas. **Cada fórmula foi medida contra os próprios valores do Yahoo antes de ser adotada**, porque o score compara percentis na seção cruzada (ADR-012/ADR-044) e régua diferente distorce em vez de completar: `roe` por patrimônio **final** errava 5–12% com viés sistemático (o Yahoo usa patrimônio **médio** entre o trimestre atual e o de 4T atrás → erro cai para ≤0,4%); `operating_cashflow` somando 4 trimestres erra ≤0,1%; mas `free_cashflow` somando a linha "Free Cash Flow" erra **17–97%** (MSFT 72,9bi contra 37,0bi — o `freeCashflow` do Yahoo é *levered*) e `quick_ratio` erra 3,6–16,4% (o Yahoo exclui mais que estoque). **3 das 5 fórmulas rejeitadas**; preenchê-las injetaria viés sistemático, pior que a ausência porque ausência é visível. Derivação é **fallback**: só quando a chave do fornecedor está ausente, marcada `source: "Atlas derived"` com fórmula e erro no `detail`. `quarterly_cashflow` é buscado de forma **preguiçosa**, preservando o orçamento de 6 chamadas/símbolo da ADR-046 para ~95% do universo. **Correção achada na validação real**: a 1ª versão derivava também `current_ratio` (fórmula exata!) e **piorava** o campo — ele é crítico e já tinha fallback secundário; o balanço trimestral do Yahoo parava em 2026-03-31 enquanto o SEC tinha o 10-Q de junho, então o derivado deslocava um secundário mais fresco, discordava 5,85% (>5%) e ambos eram descartados (`present`→`invalid`). Princípio: **derivação é para campo SEM outra fonte**. Validado com recoleta real: JNJ 59,0→**94,0**, falta required `Nenhum`; carteira com confiança média 64,8→**96,5** e **0 posições abaixo do gate** (era 15). 1212 testes verdes, 6 novos.

- **Materialidade da lacuna exibida (2026-07-24, ADR-050)**: pedido do usuário ao investigar o `short_float` do BRK-B — "preciso que a informação de que é irrelevante apareça em algum lugar", em vez de eu concluir "aceitar e seguir". Novo `reports/field_materiality.py::materiality_note` lê o papel de cada campo da **config governada** (`features.yaml` = o que é pontuado e com que peso, `model.yaml` = peso de fator, `deal_breakers.json` = limiares/isenções), sem lista paralela que envelheceria em silêncio. Dos 77 campos de evidência: **37** não entram no score nem em limiar (só reduzem Data Freshness), **27** entram no score, **11** propagam por dependência (`total_cash`→`net_debt_ebitda`), **2** (`altman_z`, `short_float`) são governados só por limiar rígido. Para campo pontuado, o teto de deslocamento no Investment Score é `peso_fator × peso_feature × 100` — aritmética de config, **dispensa simulação** (9,0 pts em `ev_ebitda`, 1,5 em `fcf_yield`). **Três overclaims corrigidos durante a construção**: (1) `current_liquidity` é o `current_ratio` renomeado no `COLUMN_MAP`, logo é pontuado e NÃO permite afirmação forte; (2) "sem efeito na decisão" é falso mesmo para o `short_float`, porque `Data Freshness` itera todos os campos do `field_evidence` e tem gate próprio em 70; (3) `total_cash` não é pontuado nem governa limiar por si, mas compõe `net_debt_ebitda` — a 1ª versão o declarava inconsequente, falso na direção que tranquiliza, corrigido propagando por `DERIVED_DEPENDENCIES` (o teste que quebrou foi o meu próprio, que usava `dividend_rate` como exemplo de campo inócuo, quando ele alimenta `shareholder_yield`). **Limite explícito**: o teto é sobre o Investment Score, não sobre a decisão — ela sai de Opportunity/Conviction por transformação própria, então nenhuma frase diz "a decisão não muda"; só simulação daria isso. Vocabulário sem "irrelevante"/"não muda", com teste travando. Renderizado na **página da empresa** (sítio que importa: o cockpit só lista features obrigatórias/risco ausentes, e o `short_float` do BRK-B é `stale`, nunca entra nessa lista — ligar só ao cockpit deixaria o caso relatado sem cobertura), e no cockpit via `build_missing_reasons` (campo `materiality`, aditivo). Só em linha COM lacuna, para não virar ruído em ~60 das 83 linhas. **4º bug corrigido**: unidade — limiar em pontos percentuais contra valor persistido em fração (o mapper só multiplica por 100 dentro do pipeline), o BRK-B saía como "crescer 2083x" em vez de 20,8x. 1225 testes verdes, 13 novos.

- **Flake conhecido: `test_post_journal_requires_json_content_type` (2026-07-24, NÃO resolvido, NÃO atribuído)**. Falha com `ConnectionAbortedError: [WinError 10053]` em `socket.py` (caminho de leitura do cliente), **1 vez em 19 execuções da suite completa**; 0 falhas em 25 execuções do arquivo isolado. Não é asserção falhando — é a conexão caindo antes da resposta. **Duas hipóteses investigadas e REFUTADAS, não repetir**: (1) corrida no encerramento do servidor — a fixture já faz `shutdown()` + `server_close()` + `thread.join(timeout=5)`, por teste, está correta; (2) resposta antes de drenar o corpo — `api/server.py::do_POST` de fato responde 415 e retorna sem ler `self.rfile`, o que é o padrão clássico de RST no Windows, mas teste direto mostrou 415 limpo mesmo com corpo de **2 MB**: o `BaseHTTPRequestHandler` lida com isso, não há bug de drenagem. Hipótese restante é **ambiental**, fora do repositório: `WinError 10053` é literalmente "software no computador anfitrião anulou uma ligação estabelecida", e em loopback no Windows a causa usual é antivírus/software de segurança interpondo-se — o que explicaria só aparecer sob a suite completa (mais conexões) e não reproduzir sob demanda. **Ação se recorrer**: capturar o traceback completo no momento (é o dado que falta); NÃO reinvestigar as duas hipóteses acima. Correção candidata, quando houver evidência: retry único escopado a `ConnectionAbortedError` — não mascara, porque a asserção do 415 é exercitada na segunda tentativa e um problema determinístico falharia nas duas. Não implementado agora por não haver como validar sem reproduzir.

- **Lacuna de risco provadamente inócua não paga penalidade (2026-07-24, ADR-051)**: auditando a execução da carteira, CVX aparecia sem `net_debt_ebitda`/`net_debt`/`total_cash`. Causa raiz é a de sempre — **divergência definicional**: `total_cash` do CVX vinha 5,323 bi (Yahoo) contra 6,316 bi (SEC), 18,7% contra tolerância de 5%, mesmo padrão de ADR-042/ADR-048; a cascata derruba `net_debt` e `net_debt_ebitda`, que é insumo de deal breaker. **O motor NÃO fica cego** (verificado: registra `risk_evidence_missing` e cobra `risk_uncertainty_penalty: 3.0`) — quem é cega é a penalidade. Como `net_debt = total_debt − total_cash` e caixa nunca é negativo, `net_debt ≤ total_debt`; com `ebitda > 0` a razão tem teto `total_debt/ebitda`. Para o CVX o teto é **1,198** contra limiar de **4,0**: nenhum valor de caixa aciona o deal breaker, e a penalidade era por incerteza inexistente. Medido no universo coletado, dos 4 casos de `net_debt_ebitda` ausente, **3 eram provadamente inócuos** (CALM teto 0,000; HIG 0,783; CVX 1,198) e 1 indeterminado (AMP, sem insumo). Novo `_gap_cannot_breach_ceiling` em `scoring/investment.py`, conservador por construção: devolve False (penaliza) sem insumo, com denominador ≤ 0 (onde a divisão inverte a desigualdade e o teto deixa de valer) e com teto **igual** ao limiar. Aplica-se hoje só a `net_debt_ebitda` — `f_score_annual` é discreto e um ausente pode estar abaixo de 4, `altman_z` é composto sem insumos individuais, `short_float` não tem o que limitar. Validado com recoleta real: CVX de `risk_evidence_missing: net_debt_ebitda`/penalidade 3,0/Investment 41,5 para `Nenhum`/0,0/**44,5**, único símbolo alterado; **nenhuma decisão mudou** (SELL AVAV/CLF/FMC/SGML, REVISAR IBRX/JNJ/YPF). 1234 testes verdes, 7 novos. **LIMITAÇÃO ABERTA, deliberadamente fora do ADR**: a assimetria maior segue — campo de risco desconhecido custa 3,0 pontos, conhecido-e-ruim custa 15 **+ `AVOID` forçado**. Não saber é estruturalmente mais barato que saber a má notícia e escapa do portão de AVOID. Este ADR reduz falso positivo de penalidade, NÃO fecha o falso negativo; corrigir exigiria encarecer a lacuna indeterminada, o que muda decisão para cima e pede medição própria.

- **Página da empresa deixa de dizer "presente" sem mostrar número (2026-07-24, refina ADR-045)**: o `_value_for` procurava o valor só pelo nome do campo, mas o Atlas persiste vários deles sob o nome gêmeo do `COLUMN_MAP` (`current_ratio`/`current_liquidity`, `ev_to_ebitda`/`ev_ebitda`/`enterprise_to_ebitda`). A linha aparecia com situação `present` e valor vazio — contradição visível que o próprio ADR-045 registrava como pendente. Novo `FIELD_ALIASES` (grupos transitivos derivados do `COLUMN_MAP`, não lista paralela) faz a busca cobrir os gêmeos, e `displayable_evidence` tira os campos de procedência (`raw_snapshot_path`, `secondary_raw_snapshots`) das tabelas de indicadores — eles são metadado de auditoria, não métrica, e inflavam a contagem de campos. O apelido **não resgata** campo que o motor declarou ausente: se a evidência diz `missing`, a linha continua dizendo isso (travado em teste). 8 testes novos, incluindo um parametrizado sobre todo o `COLUMN_MAP` para que um gêmeo novo não escape da formatação.

- **Executar o pipeline pelo visor (2026-07-24, ADR-053)**: a Fase 1 fechou a porta de entrada mas a costura seguia aberta na ação mais frequente — atualizar dados exigia sair do visor, achar um terminal e colar o comando que a home apenas imprimia. `POST /run` dispara os MESMOS dois modos do menu (`--portfolio`/`--full`) via `api/runner.py`, com três invariantes: **uma execução por vez** (trava; segundo clique recebe 409 e nunca é enfileirado, porque enfileirar esconderia que o clique não fez o esperado — duas runs simultâneas corromperiam `atlas_history.db`); **modo por allowlist** (o cliente manda uma chave, o argv é montado no servidor — não é validação de entrada, é ausência de caminho); e **local por construção** (bind em 127.0.0.1, mais checagem explícita de origem como defesa em camada, para um bind acidental em `0.0.0.0` não virar execução remota de processo). `serve(allow_run=False)` remove as rotas — é como o visor hospedado da Fase 2 sobe —, respondendo **404, não 403**, porque "proibido" revelaria um recurso que aquele modo não tem. `SystemExit` do Health Check lê como falha com causa nos logs, não como shutdown do visor; a trava é liberada em `finally` inclusive em `BaseException`. 13 testes.

---

## Última atualização
- **Data**: 2026-07-23
- **Commit**: `feat(scoring): scoring reference includes any issuer domicile (ADR-044)`
- **Baseline de validação**: 1175 testes verdes
- **Sessão 07-23**: mesa de decisão "Hoje" (roadmap A–E: identidade estável ADR-040, delta run-over-run, cockpit único, journal interativo POST /journal ADR-041, confiança explicável lendo `field_evidence`); consertos de dados que a explicabilidade expôs (`total_debt` fora dos críticos ADR-042; extração SEC ancorada no período ADR-043); metodologia: referência de score passa a incluir qualquer domicílio (ADR-044, 2.429→2.930, +501 ADRs/estrangeiros US-listed, rebuild do checkpoint 07-13 sem recoleta); documentação das amostras de universo (§5 + `docs/UNIVERSE_SOURCES.md`). 5 runs `--portfolio` reais, decisões SELL estáveis (AVAV/CLF/FMC), journal intocado (0 eventos).
- **Impacto medido do ADR-044** (antes US-2429 → depois 2930, `--portfolio`): holdings estrangeiras mal moveram (|Δopportunity| médio 0,43), nenhuma mudou de recomendação; shift das US (1,62) na verdade maior — sinal de que o movimento é dominado por dado fresco, não pela referência. 6 decisões mudaram de banda adjacente (SNA/CF BUY↔ACCUMULATE, PHM/GOOG/DHI ACCUMULATE→HOLD, FCX HOLD→WATCH), todas US, dentro da variação run-a-run. Correção de método, não de decisões.

### Integração de validação histórica (sessão atual)

`application/reporting.py::ReportingApplicationService.generate_performance_validation`
agora lê o artefato opcional governado por
`config/settings.json::portfolio_validation_report_path` e o incorpora como
`historical_validation` em `performance_validation.json`. A integração é
read-only e mantém `not_available` quando não há validação histórica completa;
não recalcula performance nem altera scoring, decisões ou políticas.

O contrato `backtesting/portfolio_validation.py::ValidationSummary` agora
expõe retorno anualizado do benchmark, excesso anualizado, Sharpe e Sortino.
O diagnóstico operacional usa `INCONCLUSIVE` abaixo de 12 períodos completos;
acima desse mínimo, compara o excesso anualizado ao benchmark sem alterar o
modelo.

`backtesting/readiness.py` adiciona auditoria offline da prontidão histórica.
Executada em 2026-07-21 sobre `output/dados/backtest_2026-01-01`, encontrou
498 arquivos de preços, 99,2% de cobertura do universo e janela
2024-12-02—2026-07-16. O resultado é `BLOCKED` por
`POINT_IN_TIME_FUNDAMENTALS_MISSING` e `EXECUTION_EVIDENCE_MISSING`; nenhum
`PASS/FAIL` de performance foi produzido. **`write_readiness_report` grava via
`storage/atomic_write.py::atomic_write_json`** (achado ao terminar este WIP:
grafava com `write_text()` puro, o mesmo padrão de bug do lock do OneDrive já
documentado no ADR-032 — corrigido antes de rodar contra o dataset real).
Reexecutado ao vivo pós-fix contra o mesmo dataset de 498 símbolos: números
idênticos aos acima, confirma que o fix não alterou comportamento.
**Achado maior da mesma auditoria**: mais 8 escritores pré-existentes
(`total_return_evidence.py`, `execution_evidence.py`, `walk_forward.py`,
`performance_validation.py`, `universe/report.py`, `watchlist/report.py`,
`portfolio/model_portfolio.py`, `portfolio/pipeline.py`) ainda usam
`write_text()` puro — a auditoria do ADR-032 (2026-07-18) não foi completa.
Não corrigido nesta sessão (fora do escopo deste WIP); registrado como
pendência aberta abaixo.

`backtesting/total_return_batch.py` materializa os CSVs de preços em
`output/dados/total_return_evidence.json`, com 9.437 observações mensais
dividend-inclusive e benchmark `SPY`. O auditor reconhece esse artefato; a
evidência de retorno total deixou de ser um bloqueio.

### Manutenção local do OneDrive (2026-07-22)

- Enviados para a Lixeira apenas os caches recriáveis em
  `data/provider_cache/`: `finnhub.json`, `fmp.json`, `massive_float.json`,
  `massive_grouped_daily.json`, `massive_ticker_details.json` e
  `sec_shares.json` (830,3 MB no total).
- Preservados `data/provider_cache/fmp_quota.json`, `data/raw_snapshots/`,
  `.venv/`, bancos e relatórios.
- Impacto esperado: a próxima coleta pode ser mais lenta e reconstruirá os
  caches conforme necessário; nenhuma configuração, regra de negócio ou
  evidência imutável foi alterada.

### Migração dos raw snapshots para armazenamento local (2026-07-22)

- `ATLAS_RAW_SNAPSHOT_PATH` passa a selecionar, nesta estação Windows,
  `C:\Users\marcu\AppData\Local\Atlas_Investment_OS\raw_snapshots` sem tornar
  `config/settings.json` específico da máquina; o default portátil permanece
  `data/raw_snapshots`.
- Todos os pontos de coleta resolvem o caminho pela função compartilhada
  `storage.raw_snapshots.resolve_raw_snapshot_path`.
- A migração operacional copia e valida integralmente os arquivos antes de
  remover a origem do OneDrive, e atualiza os caminhos persistidos no banco
  local `data/atlas_history.db` preservando hashes e conteúdo.
- A evidência externa não é sincronizada nem versionada; requer backup próprio
  antes de troca de disco ou reinstalação do Windows.
