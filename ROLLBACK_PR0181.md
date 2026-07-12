# Rollback — PR-018.1

## Git rollback

```cmd
git revert <PR-018.1-commit-hash>
```

## Manual rollback

1. Remove `portfolio/pipeline.py`.
2. Remove `tests/test_portfolio_pipeline.py`.
3. Restore the previous `run_all.py` and `config/settings.json`.
4. Remove the PR-018.1 entries from `docs/ROADMAP.md` and
   `docs/CHANGELOG.md`.
5. Remove `README_PR0181.md` and `ROLLBACK_PR0181.md`.
6. Delete `output/portfolio_report.json` if it was generated.

No database migration is introduced by this PR.
