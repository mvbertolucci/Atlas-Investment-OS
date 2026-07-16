# Priority Report

Classificação individual de prioridade de venda (carteira atual) e de compra
(screener). Camada de consulta read-only: não recalcula score, decisão,
regra de venda ou Deal Breaker, e **não constrói carteira** -- sem
peso-alvo, sem teto de posição ou setor. Isso é responsabilidade de outro
instrumento (`portfolio.model_portfolio`); este apenas ordena e apresenta.

## Por que existe

`ranking_report.json` (carteira atual), `research_ranking_report.json`
(screener amplo) e `portfolio_report.json` (rebalance oficial) já contêm
tudo que é preciso -- mas cada consulta exigia um script ad-hoc. Este
módulo é a camada reutilizável de apresentação sobre esses artefatos já
computados.

## Duas classificações

- **Venda** (`SellPriorityReport`): holdings da carteira atual, ordenados
  por `priority` (a mesma prioridade de escalação do rebalance) e depois
  por Investment Score decrescente. `action`, `reason`, `triggered_rules`
  e `priority` são copiados **verbatim** de
  `PortfolioReport.rebalance.actions` -- o motor oficial de venda
  (`portfolio.sell_rules.evaluate_sell_rules`). Priority nunca deriva uma
  segunda decisão de venda a partir de Deal Breakers; `deal_breakers`
  continua disponível no item só como contexto explicativo (o ranking já
  carregava essa coluna), nunca determina a ação. Sem
  `portfolio_report.json` disponível, a prioridade de venda fica **vazia**
  -- nunca fabrica uma ação a partir de outra fonte. Ver
  `docs/adr/ADR-011-single-sell-voice.md`.
- **Compra** (`BuyPriorityReport`): candidatos do screener (universo amplo),
  ordenados por `candidate_rank` (só quem passou o safeguard governado --
  sem Deal Breaker, confiança mínima). `already_held` sinaliza quando o
  candidato já está na carteira atual (via `held_symbols`, derivado de
  `config/portfolio.csv`). `RankedCompany.already_held` (a mesma flag, na
  origem, em `output/dados/ranking_report.json`) usa a mesma ideia mas a coluna
  `origin` diretamente -- ver `docs/RANKING_METHOD.md#universe-provenance`.

## Como consultar

**Linha de comando:**

```powershell
python -m priority.cli                      # tabelas de venda e compra
python -m priority.cli --top 30             # limita a compra ao top 30
python -m priority.cli --sector Energy       # filtra a compra por setor
python -m priority.cli --exclude-held        # omite candidatos já na carteira
python -m priority.cli --json                # imprime o relatório completo em JSON
python -m priority.cli --output out.json     # também grava em arquivo
```

Lê `output/dados/ranking_report.json` (contexto explicativo de venda + candidatos
de compra), `output/dados/portfolio_report.json` (**fonte oficial das ações de
venda** -- sem ele, a prioridade de venda fica vazia),
`output/dados/research_ranking_report.json` (compra, opcional -- ausente se o
screener amplo ainda não rodou) e `config/portfolio.csv` (para saber o que já
está na carteira). Todos os caminhos podem ser sobrescritos por flag
(`--ranking-report`, `--portfolio-report`, `--research-ranking-report`,
`--portfolio`).

**Artefato**: `output/dados/priority_report.json`, emitido a cada `run_all.py`
(guardado por `priority_enabled`, default `true`) -- `run_all.py` já tem o
`PortfolioReport` da mesma execução em mãos, então a prioridade de venda
sempre reflete o rebalance oficial calculado naquele run.

**API**: `/priority`, `/priority/sell`, `/priority/buy` (read-only, GET).

**SDK**: `AtlasClient.priority()`, `.priority_sell()`, `.priority_buy()`.

## O que NÃO faz (por design)

- Não atribui peso a nenhum candidato.
- Não aplica teto de posição ou setor.
- Não recalcula nem substitui a decisão de venda do rebalance oficial --
  copia `action`/`reason`/`triggered_rules`/`priority` prontos; nunca
  deriva SELL/HOLD a partir de Deal Breakers (comportamento antigo,
  substituído pela reconciliação de ADR-011).
- Não detecta automaticamente classes de ação duplicadas (ex.: GOOG/GOOGL)
  -- o relatório de ranking não carrega o nome da empresa para desambiguar
  com segurança, e uma heurística por sufixo de ticker geraria falsos
  positivos reais (ex.: `AAP` vs `AAPL` são empresas diferentes). Revisão
  manual continua necessária para esse caso específico.
- A prioridade de compra fica vazia (`buy: null`) quando o screener amplo
  ainda não foi coletado (`python -m portfolio.model_portfolio` /
  `portfolio.collector` antes).
- A prioridade de venda fica vazia (`sell.items: []`) quando
  `portfolio_report.json` não está disponível -- nunca fabrica uma ação a
  partir de Deal Breakers ou de outra fonte.
