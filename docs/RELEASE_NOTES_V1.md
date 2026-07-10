# Release Notes — Atlas Investment OS v1.0.0

## Destaques

A versão 1.0.0 introduz a camada completa de Portfolio Intelligence.

### Portfolio Core

- `Holding`
- `Portfolio`
- `AllocationSnapshot`
- `PortfolioRisk`
- `RebalanceAction`
- `RebalancePlan`

### Portfolio Loader

- Importação CSV
- Validação de schema
- Aliases em português e inglês
- Mesclagem de posições duplicadas
- Preço médio ponderado

### Allocation Engine

- Peso por ativo
- Peso por setor
- Peso por país
- Peso por moeda
- Peso de caixa

### Concentration Engine

- Maior posição
- Top 5
- Limites por setor, país e moeda
- Score de concentração
- Score de diversificação

### Portfolio Quality Engine

- Investment Score ponderado
- Opportunity Score ponderado
- Conviction Score ponderado
- Decision Confidence ponderado
- Portfolio Quality Score
- Cobertura dos relatórios

### Rebalance Engine

- Ações BUY, SELL e HOLD
- Pesos-alvo automáticos e explícitos
- Tolerância
- Valor mínimo de operação
- Caixa necessário
- Turnover estimado

### Portfolio Report

- Resumo executivo
- Consolidação dos quatro motores
- Serialização para futuras saídas Excel, Markdown, API e Dashboard

## Compatibilidade

O pipeline de análise de empresas da v0.9 permanece compatível.
A camada de portfólio é adicional e consultiva.

## Validação final

```cmd
pytest
python run_all.py
```
