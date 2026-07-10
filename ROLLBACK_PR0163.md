# Rollback

Antes do commit:

```cmd
del portfolio\allocation.py
del portfolio\metrics.py
del tests\test_portfolio_allocation.py
```

Depois do commit:

```cmd
git revert HEAD
```
