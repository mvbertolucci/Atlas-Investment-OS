# Rollback

Antes do commit:

```cmd
del portfolio\rebalance.py
del tests\test_portfolio_rebalance.py
```

Depois do commit:

```cmd
git revert HEAD
```
