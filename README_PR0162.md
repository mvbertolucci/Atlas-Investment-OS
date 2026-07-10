# PR-016.2 — Portfolio Loader

## Objetivo

Carregar uma carteira CSV e convertê-la em um objeto `Portfolio`.

## Arquivos

- `portfolio/loader.py`
- `portfolio/csv_schema.py`
- `portfolio/exceptions.py`
- `tests/test_portfolio_loader.py`
- `config/portfolio.example.csv`

## Funcionalidades

- validação de colunas obrigatórias;
- aliases em português e inglês;
- validação de linhas;
- mesclagem opcional de símbolos duplicados;
- média ponderada do preço médio;
- criação de `Holding`;
- criação de `Portfolio`.

## Uso

```python
from pathlib import Path
from portfolio.loader import load_portfolio_csv

portfolio = load_portfolio_csv(
    Path("config/portfolio.csv"),
    portfolio_name="Minha Carteira",
    cash=10000,
)
```

## Testes

```cmd
pytest tests/test_portfolio_loader.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-016.2: Add Portfolio CSV Loader"
```
