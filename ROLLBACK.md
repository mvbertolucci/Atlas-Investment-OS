# Rollback

Antes do commit:

```cmd
git restore reports/morning_brief.py
del tests\\test_morning_brief_domain.py
```

Depois do commit:

```cmd
git revert HEAD
```
