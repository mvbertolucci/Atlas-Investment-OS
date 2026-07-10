# PR-016.5 — Portfolio Quality Engine

## Objetivo

Calcular a qualidade agregada da carteira usando os
`CompanyReport` associados às holdings.

## Arquivos

- `portfolio/quality.py`
- `tests/test_portfolio_quality.py`

## Métricas

- Investment Score ponderado
- Opportunity Score ponderado
- Conviction Score ponderado
- Decision Confidence ponderado
- Portfolio Quality Score
- Rating da carteira
- Cobertura dos relatórios
- Penalidade por concentração
- Penalidade por CompanyReport ausente

## Uso

```python
from portfolio.allocation import calculate_allocation
from portfolio.concentration import (
    analyze_allocation_concentration,
)
from portfolio.quality import calculate_allocation_quality

allocation = calculate_allocation(portfolio)
concentration = analyze_allocation_concentration(
    allocation
)
quality = calculate_allocation_quality(
    allocation,
    concentration=concentration,
)
```

## Testes

```cmd
pytest tests/test_portfolio_quality.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-016.5: Add Portfolio Quality Engine"
```
