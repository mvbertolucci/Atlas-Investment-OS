# Rollback

Antes do commit:

```cmd
del portfolio\concentration.py
del tests\test_portfolio_concentration.py
```

Depois do commit:

```cmd
git revert HEAD
```
