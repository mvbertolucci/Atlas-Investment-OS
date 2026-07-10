# Rollback

Antes do commit:

```cmd
git restore reports/excel.py
del tests\test_excel_domain.py
```

Depois do commit:

```cmd
git revert HEAD
```
