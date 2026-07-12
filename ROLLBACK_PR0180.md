# Rollback — PR-018.0

PR-018.0 changes documentation and repository text-normalization policy only.

## Git rollback

After the PR commit is created:

```cmd
git revert <PR-018.0-commit-hash>
```

## Manual rollback

Remove `.gitattributes`, `README_PR0180.md`, `ROLLBACK_PR0180.md` and
`docs/ATLAS_AUDIT_CURRENT_STATUS.md`, then restore the prior versions of:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/BACKLOG.md`
- `docs/CHANGELOG.md`
- `docs/RELEASE_NOTES.md`
- `docs/ROADMAP.md`

No database or generated-output migration is required.
