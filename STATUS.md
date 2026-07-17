# STATUS.md — Estado real do sistema Atlas

> **REGRA DE PROCESSO**: este arquivo deve ser atualizado como último passo de toda
> sessão que altere motores de decisão, fórmulas de métricas ou config/thresholds.
> Antes de dar a sessão por encerrada: suíte verde (não deve mudar comportamento),
> commit, push. Specs e docs em `docs/` descrevem intenção; este arquivo descreve o
> que o código faz **hoje**, com citação de arquivo/função.

---

## 1. Motores de decisão ativos

| Motor | O que decide | Onde é chamado | Ativo em produção? |
|---|---|---|---|
| `decision/policy.py::evaluate_decision` (via `decision/engine.py::apply_decision`) | `Decision` (STRONG_BUY…AVOID) a partir de Opportunity+Conviction+Risk | `scoring/investment.py::score_dataframe` → `run_all.py::build_scores` (run_all.py:315-331), roda em `--full`, `--portfolio`, `--ticker` | **Sim** |
| `models/investment_model.py::apply_recommendation` | `Score Band` — faixa **descritiva** do Investment Score (Elite/Alto/Bom/Médio/Baixo), sem estrela nem verbo de compra | mesma cadeia, logo após `Decision` | **Sim, mas NÃO é classificador de compra** — rebaixado de veredicto (`Recommendation` em estrelas) para rótulo descritivo; `Decision` é a voz única de compra (reconciliação do conflito #1) |
| `portfolio/sell_rules.py::evaluate_sell_rules` | SELL/TRIM/HOLD/REVISAR por holding real, via 4 regras (distress, valuation_stretch, fundamental_decay, relative_decay) + confidence gate + escalonamento. `distress` agrupa motivos em famílias de evidência independentes (solvência, alavancagem, liquidez, estresse de mercado, qualidade operacional — `RuleEvaluation.evidence_count`) em vez de contar regras cruas, evitando que dois sintomas do mesmo problema (ex.: Altman Z e Interest Coverage, ambos solvência) inflem a escalação; `distress_review_at`/`distress_sell_at` (default 1/2) exigem 2+ famílias independentes para SELL automático, 1 família vira REVISAR. `relative_decay` é `review_only` por padrão (sinal cross-sectional/comparativo nunca dispara TRIM/SELL sozinho, só REVISAR) | `portfolio/rebalance.py:578-629` → `portfolio.pipeline.build_portfolio_intelligence` → `run_all.py::generate_portfolio_intelligence` (run_all.py:678-745) | **Sim** — único motor de venda para holdings reais (`config/portfolio.csv`). Quando `SellEngineBlockedError` dispara (posição sem tese), `build_portfolio_intelligence` substitui o plano por REVISAR/holding (`_build_blocked_rebalance_plan`) em vez de suprimir a seção Carteira inteira — score/qualidade/alocação continuam visíveis, só a decisão de venda fica indisponível |
| `priority/pipeline.py::build_sell_priority` | **Read-only, sem decisão própria** — copia `action`/`reason`/`triggered_rules`/`priority` verbatim de `PortfolioReport.rebalance.actions` (o rebalance oficial); `deal_breakers` só como contexto explicativo, nunca determina a ação. Sem `PortfolioReport`, a lista de venda fica vazia (nunca fabrica ação) | `run_all.py::generate_priority_report` (run_all.py:636-676), chamado incondicionalmente (`priority_enabled=True` por default) | **Sim** — reconciliado com o rebalance oficial (conflito #2 resolvido) |
| `watchlist/triggers.py::evaluate_watchlist_triggers` | trigger / no-trigger + cleanup-candidate por item da watchlist | `run_all.py::generate_watchlist_report` (run_all.py:748-832) | **Sim** |
| `ranking/pipeline.py::rank_companies` | candidate_rank / safeguard_passed (não é buy/sell, é filtro de screener) | `run_all.py::generate_ranking_report`, só em `mode == "full"` | **Sim**, escopo restrito ao screener |
| `watchlist/promote.py::promote_to_watchlist` | promove símbolo para watchlist (grava no CSV) | só chamado pelo próprio CLI (`__main__`) e por testes | **CLI manual** — `run_all.py` nunca grava; é o passo que o usuário roda para aplicar uma sugestão |
| `watchlist/screening.py::propose_from_broad_reports` + `derive_trigger_condition` | **propõe** (nunca grava) inclusões na watchlist a partir dos screeners AMPLOS (Mercado Amplo/ADR), com `trigger_condition` derivada do perfil (cortes de `ranking.yaml`/`models/investment_model.py`, nenhum inventado) | `reports/atlas_report/context.py::build_report_context` → seção "Sugestões para a watchlist" do relatório, só quando `broad_market_report_path`/`adr_report_path` informados (`mode == "full"`) | **Sim** — read-only, alimenta a watchlist por critério estabelecido sem tocar no CSV curado. `propose_watchlist_candidates` (fonte = `ranking_report` estreito do próprio run) continua existindo mas não é mais chamada pelo relatório — comparar candidatos contra a watchlist da qual eles vieram é tautológico (achado rodando de verdade: 39/39 sempre já watched) |

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

---

## 3. Thresholds e config ativos

| Config | Lido em (produção) | Valores-chave |
|---|---|---|
| `config/model.yaml` | `run_all.py::build_scores` (L320-324); `model_version` gravado no snapshot (L1092-1096) | `model_version: "0.3"`; pesos business 0.35 / valuation 0.30 / financial 0.15 / timing 0.20; confiança limitada a 59 quando falta feature `required` |
| `config/features.yaml` | `factors/engine.py::score_all_factors` via `scoring/investment.py` (L274); `run_all.py::audit_feature_coverage` (L344) | pesos/`required` por métrica, fonte de verdade desde PR-017.3 |
| `config/data_quality.yaml` | `scoring/investment.py::score_dataframe` e `analytics/data_quality.py` | qualidade por fonte; frescor 100 até 7 dias, 70 até 35, 0 depois disso ou sem data |
| `config/deal_breakers.json` | `scoring/investment.py::apply_deal_breakers` (via `build_scores`, L323) | limites observados por risco e penalidade de incerteza de 3 por evidência ausente, limitada a 10 |
| `config/sell_rules.yaml` | `portfolio.sell_rules.load_sell_rules_policy`, chamado em `run_all.py:1105-1106` e default em `portfolio/pipeline.py:22` | `confidence_gate` (score_coverage≥60, confidence≥60); `distress`, `valuation_stretch` (target_upside<-10%), `fundamental_decay` (f_score_drop≥2, roic_drop≥20%), `relative_decay` (percentil<40); `escalation` (trim@1, sell@2 gatilhos, trim_fraction 50%) |
| `config/ranking.yaml` | `run_all.py::generate_ranking_report` (L522-527) | mínimos 70 para confiança, cobertura, qualidade da fonte e frescor; requer features críticas completas e ausência de deal breaker |
| `config/universe.yaml` | `run_all.py::generate_universe_report` (L490-495) | min market cap $1B, min price $5, min volume 100k, EQUITY/USD/US |
| `config/settings.json` | `run_all.py` L114 — raiz de todos os paths/flags | — |
| `config/model_portfolio.yaml` | **só** `portfolio/model_portfolio.py` (CLI standalone), **`run_all.py` não chama** | target_positions 20, max_position_weight 5%, max_sector_weight 20% |
| `config/portfolio_validation.yaml` | **só** default arg de `backtesting/portfolio_validation.py::main` (CLI manual) | — |
| `config/universe_adr.yaml` | **existe mas não é lido em produção** — grep no arquivo/chave sem caller fora de testes | — |
| `config/universe_market.yaml` | **existe mas não é lido em produção** — idem | — |
| `config/historical_execution.yaml` | **existe mas não é lido em produção** — loader só chamado em testes | — |

---

## 4. Gating e cobertura

| Item | Status | Evidência |
|---|---|---|
| cobertura/qualidade/confiança | **Separadas** | `Data Coverage` pondera a contribuição real de cada feature; `Model Confidence` aplica teto 59 se faltar `required`; `Source Quality` e `Data Freshness` são sinais governados independentes. Aliases legados: `Score Coverage` e `Confidence Score`. O ranking canônico exige os quatro gates; ver ADR-013. |
| `model_version` no snapshot | **Existe** | `storage/history_db.py` tabela `snapshots`, coluna `model_version TEXT NOT NULL DEFAULT 'legacy'` (L50/149), populada em `run_all.py:1092-1096` a partir de `model.yaml` |
| Snapshot grava features individuais? | **Sim, não só o score** | Tabela `snapshots` (`storage/history_db.py:36-69`): `business_score, valuation_score, financial_score, timing_score, investment_score, opportunity_score, confidence_score, model_version, altman_z, interest_coverage, target_upside, f_score_annual, roic, score_coverage, earnings_date, quantity, is_candidate, recommendation`. Tabela `outcome_snapshots` (L98-124) espelha estrutura similar |
| Gating setorial | **Existe, mas duplicado em 2 lugares** | `portfolio/sell_rules.py::_distress` (L197-260): `altman_z_exempt_sectors`/`interest_coverage_exempt_sectors` = Utilities/Financial Services/Banks/Insurance (`DEFAULT_SOLVENCY_EXEMPT_SECTORS`); `current_ratio_exempt_sectors` = Software. Replicado independentemente em `scoring/investment.py::apply_deal_breakers`. Não há gating setorial em `decision/` |

---

## 5. Universos e proveniência

| Universo | Config | Membership | Cadência |
|---|---|---|---|
| Portfolio | `config/portfolio.csv` | holdings reais do usuário | manual |
| Watchlist | `config/watchlist.csv` | curadoria manual | manual |
| Research (S&P 500) | `config/universe.yaml` + `research_universe.csv` | scrape Wikipedia S&P 500, min $1B mkt cap | manual, `python -m universe.sources` |
| Broad market | `config/universe_market.yaml` + `research_universe_market.csv` | NASDAQ Trader listas, min $300M mkt cap | manual, `universe.collector --market` |
| ADR | `config/universe_adr.yaml` | reusa snapshot broad-market, filtra `excluded_countries:[United States]` | sem coleta própria |

**Origin**: atribuído em `run_all.py::merge_watchlist_with_portfolio` (L149-243) — default `watchlist`, sobrescrito para `portfolio` se símbolo está em `portfolio.csv`. Prioridade `portfolio > watchlist > universe` (L164); `universe` é constante definida mas **não wireada** neste merge (comentário L156-157: "ainda não wireado"). Propagado read-only por `portfolio/pipeline.py::enrich_portfolio_from_analysis`, checado em `portfolio/rebalance.py` (sell-side) e `ranking/pipeline.py` (`already_held`, buy-side). Contrato coberto por `tests/test_origin_provenance.py`, verificado batendo com a implementação real.

**Cadência não é agendada por código** — nenhum cron/scheduler encontrado; `docs/UNIVERSE_COLLECTION.md:64` e `docs/ROADMAP.md:69`/`docs/BACKLOG.md:336` confirmam: "Scheduling (deferred until analytical validation)". `run_all.py` não tem flag `--universe`; screeners broad/ADR/S&P500 rodam via módulos separados (`universe.collector`, `universe.sources`).

**Resultado de Mercado Amplo/ADR surfaceado (não re-coletado) no Atlas Report** — a coleta em si continua manual/separada (milhares de símbolos, ~horas de runtime, ver acima); `reports/atlas_report/broad_screener.py::load_broad_screener_summary` só LÊ `output/dados/research_ranking_report_market.json`/`_adr.json` (o mesmo arquivo que `ranking/pipeline.py` já persiste para os 3 screeners, consumido também por `reports/research_html.py`) e resume idade da coleta + top candidatos diversificados por setor. `run_all.py::main` passa esses paths para `build_report_context` só em `mode == "full"`. Alerta de "coleta desatualizada" quando `age_days > 35` (folga sobre a cadência mensal pretendida). Arquivo ausente/ilegível vira seção "não incluído", nunca erro.

---

## 6. Pendências conhecidas

- **"Catálogo de venda"**: nenhuma ocorrência do termo em `docs/`. O que existe hoje cobrindo esse espaço: `portfolio/sell_rules.py` + `config/sell_rules.yaml`, `watchlist/triggers.py`, `decision/engine.py`. Se specs recentes assumem 4 pré-requisitos nomeados dessa forma, não foram encontrados documentados sob esse nome — checar se é terminologia de outra sessão/conversa antes de assumir que falta algo.
- ~~Reconciliação priority/ vs decision/~~ **RESOLVIDA** — ver conflito #2 (seção 1) e ADR-011.
- **Conflito Altman Z (clássico vs Z'')**: não existe no código — só uma fórmula clássica é usada, com isenção setorial (não coeficiente alternativo) como mitigação. Nenhuma menção em `docs/` a um conflito de variantes. O que existe de fato é a fórmula clássica aplicada uniformemente mesmo a setores onde ela é estruturalmente enganosa (mitigado só por isenção, não por Z'' apropriado). **A duplicação das listas de setores isentos entre `scoring/investment.py` (`config/deal_breakers.json`) e `portfolio/sell_rules.py` (`config/sell_rules.yaml`) foi reconciliada** (mesmo conteúdo — Utilities/Financial Services/Banks/Insurance/Biotechnology para Altman Z, Software/Tobacco para liquidez, mais `net_debt_ebitda_exempt_sectors`/`f_score_exempt_sectors` novos no lado do score) — continuam sendo dois arquivos com nomes de chave próprios (consumidores diferentes), não uma fonte única, então ainda cabe a um editor futuro atualizar os dois lados manualmente; sem teste de equivalência automática entre eles.
- **ROIC / Interest Coverage live vs backtest**: mesma lógica de tax-rate, mas `invested_capital` e o proxy de EBIT divergem entre `analytics/fundamentals.py` (live) e `backtesting/point_in_time_fundamentals.py` (point-in-time SEC). Diferença é documentada como aproximação intencional no código-fonte, mas não há teste de equivalência entre os dois caminhos — mesma empresa pode pontuar diferente ao vivo vs. em replay de backtest.
- **`watchlist/promote.py`**: módulo funcional mas órfão da automação — só acionável via CLI manual, não integrado a `run_all.py`.

---

## 7. Relatório HTML (Report v0)

| Item | Estado |
|---|---|
| Existe desde | PR-022 (`feat(reports): self-contained HTML report + one-pager, 3 run modes`), **já em produção antes desta sessão** — não foi listado na v1 deste STATUS.md, correção aplicada aqui |
| Módulos | `reports/atlas_report/context.py` (monta `ReportContext` só lendo o que os motores já produziram), `render.py` (HTML self-contido, CSS inline, zero dependência externa), `write.py` (grava arquivo), `one_pager.py` (relatório por ticker, `--ticker`), `diagnostics.py` (extrai alertas de conflito do próprio STATUS.md), `ticker_detail.py`+`formulas.py`+`svg.py` (seção de detalhe por ticker embutida no relatório principal, ver abaixo) |
| Regra central | O relatório não calcula nem decide nada — `Decision`/`action`/scores vêm prontos dos motores; ausência de razão textual cai em fallback `"razão: motor pendente"`, nunca inventado |
| Wiring | `run_all.py::main` chama `build_report_context`+`render_report`+`write_report` para os modos `--full` e `--portfolio`; `--ticker` usa `one_pager.py` à parte |
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
- **Data**: 2026-07-16
- **Commit**: pendente (`fix(backtesting): align point-in-time invested_capital with total debt (measured ROIC divergence fix)`)
