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
| `models/investment_model.py::apply_recommendation` | `Recommendation` (★★★★★…★) a partir só de `Investment Score`, buckets fixos | mesma cadeia, logo após `Decision` (comentário: "legacy, mantido por compatibilidade") | **Sim** — roda em paralelo ao `Decision` |
| `portfolio/sell_rules.py::evaluate_sell_rules` | SELL/TRIM/HOLD/REVISAR por holding real, via 4 regras (distress, valuation_stretch, fundamental_decay, relative_decay) + confidence gate + escalonamento | `portfolio/rebalance.py:578-629` → `portfolio.pipeline.build_portfolio_intelligence` → `run_all.py::generate_portfolio_intelligence` (run_all.py:678-745) | **Sim** — único motor de venda para holdings reais (`config/portfolio.csv`) |
| `priority/pipeline.py::build_sell_priority` | SELL/HOLD **binário**: `"SELL" if Deal Breakers else "HOLD"` (priority/pipeline.py:49) | `run_all.py::generate_priority_report` (run_all.py:573-622), chamado incondicionalmente (`priority_enabled=True` por default) | **Sim** |
| `watchlist/triggers.py::evaluate_watchlist_triggers` | trigger / no-trigger + cleanup-candidate por item da watchlist | `run_all.py::generate_watchlist_report` (run_all.py:748-832) | **Sim** |
| `ranking/pipeline.py::rank_companies` | candidate_rank / safeguard_passed (não é buy/sell, é filtro de screener) | `run_all.py::generate_ranking_report`, só em `mode == "full"` | **Sim**, escopo restrito ao screener |
| `watchlist/promote.py::promote_to_watchlist` | promove símbolo para watchlist | só chamado pelo próprio CLI (`__main__`) e por testes | **Órfão da automação** — CLI manual, `run_all.py` nunca chama |

### ⚠️ Conflitos sinalizados
1. **`Decision` vs `Recommendation`** — dois classificadores de compra/hold rodando sobre a mesma linha, podem discordar (Decision pondera deal-breakers/risco via Opportunity+Conviction; Recommendation só olha `Investment Score`). Sem reconciliação, expostos lado a lado na tabela de console (run_all.py:856-868).
2. **`priority.build_sell_priority` vs `portfolio.sell_rules.evaluate_sell_rules`** — para a mesma holding, no mesmo run, podem divergir: uma holding com `fundamental_decay` disparado mas sem Deal Breaker recebe `SELL`/`TRIM` do rebalance e `HOLD` do priority. O docstring de `priority/pipeline.py:20-21` afirma ser "o mesmo critério do modo sell-only do rebalance" — **isso é impreciso**: rebalance usa as 4 regras de `sell_rules.py`, priority usa só a presença de Deal Breakers. `docs/PRIORITY_REPORT.md:1-7` afirma que priority "não recalcula score, decisão ou Deal Breakers" — tecnicamente verdade (lê a coluna, não recalcula o Deal Breaker em si), mas **computa sua própria decisão SELL/HOLD** a partir dela, o que já é uma segunda lógica de decisão de venda não documentada como tal.

---

## 2. Fórmulas em produção

| Métrica | Fórmula implementada | Arquivo:função | Status |
|---|---|---|---|
| ROIC (live) | `tax_rate = tax_provision/pretax_income` (fallback 0.21); `NOPAT = EBIT*(1-tax_rate)`; `ROIC = NOPAT / invested_capital` (Yahoo "Invested Capital") | `analytics/fundamentals.py::_compute_roic` | Produção |
| ROIC (backtest/point-in-time) | mesmo tax_rate; `NOPAT = operating_income*(1-tax_rate)`; `invested_capital = long_term_debt + total_equity - cash` | `backtesting/point_in_time_fundamentals.py::derive_point_in_time_ratios` | **CONFLITO A RESOLVER (parcial)** — mesma fórmula de tax, `invested_capital` reconstruído de forma diferente (documentado como aproximação SEC intencional) |
| Interest Coverage (live) | `EBIT / abs(Interest Expense)` | `analytics/fundamentals.py::_compute_interest_coverage` | Produção |
| Interest Coverage (backtest) | `operating_income / abs(interest_expense)` | `backtesting/point_in_time_fundamentals.py::derive_point_in_time_ratios` | **CONFLITO A RESOLVER (parcial)** — numerador `EBIT` (Yahoo) vs `operating_income` (proxy SEC documentado) |
| Altman Z | Z clássico (1968, empresa pública): `1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MktCap/TotalLiab) + 1.0*(Rev/TA)` | `analytics/fundamentals.py::_compute_altman_z` **e** `backtesting/point_in_time_valuation.py::derive_point_in_time_valuation` (espelha exatamente) | **Sem conflito de coeficientes** — só EBIT (live) vs operating_income (backtest, proxy documentado). Não existe variante Z''/privada no código — uma única fórmula clássica aplicada a todos os setores; mitigação é isenção setorial (não coeficiente alternativo), duplicada em `scoring/investment.py::apply_deal_breakers` (`altman_z_exempt_sectors`) e `portfolio/sell_rules.py` (~L213-224, `DEFAULT_SOLVENCY_EXEMPT_SECTORS`) — duas listas hardcoded separadas, risco de drift |
| Piotroski F-Score | 9 critérios clássicos, 1 ponto cada, 0-9 | `analytics/fundamentals.py::_compute_f_score` (Yahoo) e `backtesting/point_in_time_fundamentals.py::_compute_f_score_from_filings` (SEC 10-K) | Sem conflito de lógica — só fonte de dado difere |
| Investment Score | **Estágio 1**: `factors/engine.py::score_all_factors` — percentile-rank por feature (`config/features.yaml`), combinado em score por fator, depois `Σ(factor_score*weight)/Σ(weight)` com pesos de `config/model.yaml` (business 0.35, valuation 0.30, financial 0.15, timing 0.20). **Estágio 2**: `scoring/investment.py::apply_deal_breakers` sobrescreve: `Investment Score = clip(Stage1 - Risk_Penalty, 0, 100)` | `factors/engine.py`, `scoring/investment.py` | Pipeline de 2 estágios **por design** — mesma coluna sobrescrita duas vezes na mesma run; downstream (`decision/`, `models/investment_model.py`, `portfolio/quality.py`) só lê o resultado final, nada recalcula |

---

## 3. Thresholds e config ativos

| Config | Lido em (produção) | Valores-chave |
|---|---|---|
| `config/model.yaml` | `run_all.py::build_scores` (L320-324); `model_version` gravado no snapshot (L1092-1096) | `model_version: "0.3"`; pesos business 0.35 / valuation 0.30 / financial 0.15 / timing 0.20 |
| `config/features.yaml` | `factors/engine.py::score_all_factors` via `scoring/investment.py` (L274); `run_all.py::audit_feature_coverage` (L344) | pesos/`required` por métrica, fonte de verdade desde PR-017.3 |
| `config/deal_breakers.json` | `scoring/investment.py::apply_deal_breakers` (via `build_scores`, L323) | `f_score_annual_min:4`, `altman_z_min:1.8` (isenta Utilities/Financial Services/Banks/Insurance), `net_debt_ebitda_max:4.0`, `current_liquidity_min:1.0` (isenta Software), `short_float_max:20.0` |
| `config/sell_rules.yaml` | `portfolio.sell_rules.load_sell_rules_policy`, chamado em `run_all.py:1105-1106` e default em `portfolio/pipeline.py:22` | `confidence_gate` (score_coverage≥60, confidence≥60); `distress`, `valuation_stretch` (target_upside<-10%), `fundamental_decay` (f_score_drop≥2, roic_drop≥20%), `relative_decay` (percentil<40); `escalation` (trim@1, sell@2 gatilhos, trim_fraction 50%) |
| `config/ranking.yaml` | `run_all.py::generate_ranking_report` (L522-527) | `min_confidence_score: 70`, `require_no_deal_breakers: true` |
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
| `score_coverage`/`confidence` | **Existe** | `factors/engine.py::score_all_factors` (L177-196) — `Model Confidence` = média das confidences por fator, aliasado `Confidence Score` e duplicado como `Score Coverage`. Única fonte desde PR-017.6 (implementação antiga em `analytics/validator.py` removida por duplicidade — ver `tests/test_confidence_score.py`). Consumido em `portfolio/sell_rules.py:81-99,425-438` e `ranking/pipeline.py:97-108` |
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

**Resultado de Mercado Amplo/ADR surfaceado (não re-coletado) no Atlas Report** — a coleta em si continua manual/separada (milhares de símbolos, ~horas de runtime, ver acima); `reports/atlas_report/broad_screener.py::load_broad_screener_summary` só LÊ `output/research_ranking_report_market.json`/`_adr.json` (o mesmo arquivo que `ranking/pipeline.py` já persiste para os 3 screeners, consumido também por `reports/research_html.py`) e resume idade da coleta + top candidatos diversificados por setor. `run_all.py::main` passa esses paths para `build_report_context` só em `mode == "full"`. Alerta de "coleta desatualizada" quando `age_days > 35` (folga sobre a cadência mensal pretendida). Arquivo ausente/ilegível vira seção "não incluído", nunca erro.

---

## 6. Pendências conhecidas

- **"Catálogo de venda"**: nenhuma ocorrência do termo em `docs/`. O que existe hoje cobrindo esse espaço: `portfolio/sell_rules.py` + `config/sell_rules.yaml`, `watchlist/triggers.py`, `decision/engine.py`. Se specs recentes assumem 4 pré-requisitos nomeados dessa forma, não foram encontrados documentados sob esse nome — checar se é terminologia de outra sessão/conversa antes de assumir que falta algo.
- **Reconciliação priority/ vs decision/**: sem plano documentado em `docs/DECISIONS.md`. `docs/PRIORITY_REPORT.md` afirma que priority é somente leitura e não recalcula decisão — na prática (`priority/pipeline.py::build_sell_priority`) ele computa um SELL/HOLD binário próprio a partir de Deal Breakers, distinto da decisão de `decision/policy.py` e de `portfolio/sell_rules.py`. **Documentação desatualizada em relação ao código** — ver conflito #2 na seção 1.
- **Conflito Altman Z (clássico vs Z'')**: não existe no código — só uma fórmula clássica é usada, com isenção setorial (não coeficiente alternativo) como mitigação. Nenhuma menção em `docs/` a um conflito de variantes. O que existe de fato é: (a) fórmula clássica aplicada uniformemente mesmo a setores onde ela é estruturalmente enganosa (mitigado só por isenção, não por Z'' apropriado), e (b) a lista de setores isentos duplicada em dois arquivos (`scoring/investment.py` e `portfolio/sell_rules.py`) sem fonte única — risco de drift, não conflito de fórmula em si.
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
| Saída | `output/atlas_report_AAAA-MM-DD.html` + `output/atlas_report_latest.html` (formato de nome mudou de timestamp completo para data nesta sessão) |
| Seção Diagnóstico | Lê o texto de STATUS.md em runtime (`run_all.py::_read_status_md`) e conta marcadores que o próprio documento já usa (`### ⚠️ Conflitos sinalizados`, `CONFLITO A RESOLVER` em linhas de tabela) — exibe alerta "N conflito(s) sinalizado(s) em STATUS.md", nunca reinterpreta o conteúdo |
| Seção Detalhe por ativo | Cada símbolo de carteira/watchlist ganha uma seção ancorada (`ticker-SYMBOL`) com: decomposição do score (mesma função `compute_symbol_contributions` do one-pager) + fórmula/inputs brutos/interpretação por threshold já em produção (`formulas.py`, sincronizado a mão com a seção 2 deste arquivo); status de cada regra de venda (`rule_results` do `sell_rules.py`, só quando a posição é holding real); sparkline por métrica só para colunas de fato persistidas em `snapshots` (seção 4); tese da posição com idade e alerta quando `fundamental_decay` disparou. Símbolos nas tabelas de Carteira/Watchlist linkam para a âncora. **Sem link externo** (Yahoo Finance foi cogitado e removido antes do merge — quebrava o contrato de zero dependência externa) |
| Testes | `tests/test_atlas_report_*.py` — fixture renderiza todas as seções, seção sem dado mostra "não incluído neste run", teste de contrato (pill exibido == `action` do motor), teste que falha se houver `http://`/`https://` em `src`/`href` (agora com uma fixture que de fato popula `ticker_details`, senão o teste nunca exercitava a seção), teste de fallback "motor pendente", teste de alerta de conflito |

---

## Última atualização
- **Data**: 2026-07-14
- **Commit**: pendente (feat(reports): screeners de Mercado Amplo/ADR surfaceados no Atlas Report)
