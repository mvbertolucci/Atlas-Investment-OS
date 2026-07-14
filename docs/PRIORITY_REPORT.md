# Priority Report

Classificação individual de prioridade de venda (carteira atual) e de compra
(screener). Camada de consulta read-only: não recalcula score, decisão ou
Deal Breakers, e **não constrói carteira** -- sem peso-alvo, sem teto de
posição ou setor. Isso é responsabilidade de outro instrumento
(`portfolio.model_portfolio`); este apenas ordena e classifica.

## Por que existe

`ranking_report.json` (carteira atual) e `research_ranking_report.json`
(screener amplo) já contêm tudo que é preciso -- mas cada consulta exigia um
script ad-hoc. Este módulo é a camada reutilizável de apresentação sobre
esses artefatos já computados.

## Duas classificações

- **Venda** (`SellPriorityReport`): holdings da carteira atual, ordenados
  por Investment Score decrescente. `action` é `SELL` quando o holding tem
  ao menos um Deal Breaker ativo, `HOLD` caso contrário. `current_weight` é
  informativo (peso real atual), nunca um alvo.
- **Compra** (`BuyPriorityReport`): candidatos do screener (universo amplo),
  ordenados por `candidate_rank` (só quem passou o safeguard governado --
  sem Deal Breaker, confiança mínima). `already_held` sinaliza quando o
  candidato já está na carteira atual (via `held_symbols`, derivado do
  `PortfolioReport` real). `RankedCompany.already_held` (a mesma flag, na
  origem, em `output/ranking_report.json`) usa a mesma ideia mas a coluna
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

Lê `output/ranking_report.json` (venda), `output/research_ranking_report.json`
(compra, opcional -- ausente se o screener amplo ainda não rodou) e
`config/portfolio.csv` (para saber o que já está na carteira). Todos os
caminhos podem ser sobrescritos por flag.

**Artefato**: `output/priority_report.json`, emitido a cada `run_all.py`
(guardado por `priority_enabled`, default `true`).

**API**: `/priority`, `/priority/sell`, `/priority/buy` (read-only, GET).

**SDK**: `AtlasClient.priority()`, `.priority_sell()`, `.priority_buy()`.

## O que NÃO faz (por design)

- Não atribui peso a nenhum candidato.
- Não aplica teto de posição ou setor.
- Não detecta automaticamente classes de ação duplicadas (ex.: GOOG/GOOGL)
  -- o relatório de ranking não carrega o nome da empresa para desambiguar
  com segurança, e uma heurística por sufixo de ticker geraria falsos
  positivos reais (ex.: `AAP` vs `AAPL` são empresas diferentes). Revisão
  manual continua necessária para esse caso específico.
- A prioridade de compra fica vazia (`buy: null`) quando o screener amplo
  ainda não foi coletado (`python -m portfolio.model_portfolio` /
  `portfolio.collector` antes).
