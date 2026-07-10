# Rollback

Antes do commit:

```cmd
del portfolio\loader.py
del portfolio\csv_schema.py
del portfolio\exceptions.py
del tests\test_portfolio_loader.py
del config\portfolio.example.csv
```

Depois do commit:

```cmd
git revert HEAD
```
