# Rollback

Antes do commit:

```cmd
del portfolio\quality.py
del tests\test_portfolio_quality.py
```

Depois do commit:

```cmd
git revert HEAD
```
