# Rollback

Antes do commit:

```cmd
git restore portfolio\__init__.py
del portfolio\models.py
del portfolio\validators.py
del tests\test_portfolio_models.py
```

Depois do commit:

```cmd
git revert HEAD
```
