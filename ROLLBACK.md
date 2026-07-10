# Rollback

Para desfazer o PR antes do commit:

```cmd
git restore scoring/investment.py reports/excel.py reports/morning_brief.py run_all.py
del tests\test_thesis_integration.py
```

Depois do commit:

```cmd
git revert HEAD
```
