# Rollback

Antes do commit:

```
del analytics\feature_audit.py
del tests\test_feature_contract.py
del docs\CHANGELOG_PR0170.md
```

Reverter as edições em `run_all.py`:
- remover o import de `analytics.feature_audit`;
- remover a função `audit_feature_coverage`;
- remover a chamada `audit_feature_coverage(df)` após o scoring.

Depois do commit:

```
git revert HEAD
```
