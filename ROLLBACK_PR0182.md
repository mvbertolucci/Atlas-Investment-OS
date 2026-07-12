# Rollback — PR-018.2

## Git rollback

```cmd
git revert <PR-018.2-commit-hash>
```

## Manual rollback

1. Restore the previous `reports/excel.py`.
2. Restore the previous `run_all.py`.
3. Remove the PR-018.2 tests from `tests/test_excel_domain.py`.
4. Revert the PR-018.2 documentation entries.
5. Remove `README_PR0182.md` and `ROLLBACK_PR0182.md`.

No database migration or portfolio-input schema change is introduced by this
PR.
