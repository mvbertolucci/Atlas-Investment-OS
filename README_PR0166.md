# PR-016.6 — Rebalance Engine

## Objetivo

Gerar um plano consultivo de rebalanceamento para a carteira.

## Arquivos

- `portfolio/rebalance.py`
- `tests/test_portfolio_rebalance.py`

## Funcionalidades

- pesos-alvo explícitos;
- pesos-alvo automáticos por qualidade;
- BUY, SELL e HOLD;
- tolerância de rebalanceamento;
- valor mínimo de operação;
- opção para impedir vendas;
- prioridade das ações;
- caixa necessário e caixa liberado;
- estimativa de turnover;
- warnings de caixa e dados ausentes;
- integração opcional com PortfolioQualityResult.

## Uso

```python
from portfolio.rebalance import build_rebalance_plan

plan = build_rebalance_plan(
    portfolio,
    quality=quality,
)
```

## Testes

```cmd
pytest tests/test_portfolio_rebalance.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-016.6: Add Portfolio Rebalance Engine"
```
