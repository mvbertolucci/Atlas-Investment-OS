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
local (`api.server`), **único** caminho de escrita da API antes read-only.
Endurecido para ferramenta local pessoal: bind só em `127.0.0.1`, exige
`Content-Type: application/json` (mitiga CSRF simples), corpo limitado, POST só
em `/journal`, append-only e consultivo (nunca envia ordem). O cockpit é servido
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
| `config/data_quality.yaml` | scoring, `analytics/data_quality.py` e `providers/evidence.py` | qualidade por fonte; frescor 100 até 7 dias, 70 até 35; aplicabilidade setorial explícita por campo |
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
| Scoring reference (US_MARKET_ELIGIBLE) | `output/dados/scoring_reference_market.json` (~2.429) | subconjunto elegível do broad market; base cross-sectional dos percentis de score | reconstruído no build de model-portfolio de mercado (`portfolio/model_portfolio.py`) |
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

---

## Última atualização
- **Data**: 2026-07-23
- **Commit**: `fix(sec): anchor total_debt on the long-term-debt period (ADR-043)`
- **Baseline de validação**: 1175 testes verdes
- **Sessão 07-23**: mesa de decisão "Hoje" (roadmap A–E: identidade estável ADR-040, delta run-over-run, cockpit único, journal interativo POST /journal ADR-041, confiança explicável lendo `field_evidence`); consertos de dados que a explicabilidade expôs (`total_debt` fora dos críticos ADR-042; extração SEC ancorada no período ADR-043); documentação das amostras de universo (§5 + `docs/UNIVERSE_SOURCES.md`). 4 runs `--portfolio` reais, decisões SELL estáveis (AVAV/CLF/FMC), journal intocado (0 eventos).

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
