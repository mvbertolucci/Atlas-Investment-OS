# PR-016.3 — Allocation Engine

## Objetivo

Transformar um `Portfolio` em uma visão consolidada de alocação.

## Arquivos

- `portfolio/allocation.py`
- `portfolio/metrics.py`
- `tests/test_portfolio_allocation.py`

## Funcionalidades

- peso por ativo;
- peso por setor;
- peso por país;
- peso por moeda;
- percentual em caixa;
- holdings com peso calculado;
- warnings para preços e CompanyReports ausentes;
- geração de `AllocationSnapshot`.

## Uso

```python
from portfolio.allocation import calculate_allocation

result = calculate_allocation(portfolio)

snapshot = result.snapshot
weighted_portfolio = result.portfolio
warnings = result.warnings
```

## Instalação

Extraia o ZIP na raiz do projeto.

## Testes

```cmd
pytest tests/test_portfolio_allocation.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-016.3: Add Portfolio Allocation Engine"
```
