# Rollback

Antes do commit:

```cmd
del reports\report_models.py
del tests\test_report_models.py
```

Depois do commit:

```cmd
git revert HEAD
```
