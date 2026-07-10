# PR-016.4 — Concentration Engine

## Objetivo

Analisar concentração da carteira a partir de um
`AllocationSnapshot`.

## Arquivos

- `portfolio/concentration.py`
- `tests/test_portfolio_concentration.py`

## Funcionalidades

- maior posição;
- concentração das 5 maiores posições;
- concentração por setor;
- concentração por país;
- concentração por moeda;
- verificação de caixa mínimo;
- HHI simplificado;
- score de concentração;
- score de diversificação;
- geração de `PortfolioRisk`;
- herança de warnings do Allocation Engine.

## Uso

```python
from portfolio.allocation import calculate_allocation
from portfolio.concentration import (
    analyze_allocation_concentration,
)

allocation = calculate_allocation(portfolio)
result = analyze_allocation_concentration(allocation)

risk = result.risk
```

## Testes

```cmd
pytest tests/test_portfolio_concentration.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-016.4: Add Portfolio Concentration Engine"
```
