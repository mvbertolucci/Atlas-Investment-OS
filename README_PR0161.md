# PR-016.1 — Portfolio Domain Models

## Objetivo

Criar a base de domínio do Portfolio Intelligence sem alterar
o pipeline atual.

## Arquivos

- `portfolio/__init__.py`
- `portfolio/models.py`
- `portfolio/validators.py`
- `tests/test_portfolio_models.py`

## Modelos incluídos

- Holding
- Portfolio
- AllocationSnapshot
- PortfolioRisk
- RebalanceAction
- RebalancePlan

## Características

- Sem dependência de pandas
- Integração opcional com `CompanyReport`
- Cash tratado como componente do patrimônio
- Validação explícita
- Serialização por `to_dict()`
- Rebalanceamento apenas consultivo

## Instalação

Extraia este pacote na raiz do projeto.

## Testes

```cmd
pytest tests/test_portfolio_models.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-016.1: Add Portfolio Domain Models"
```
