# Release Rollback

## Before tagging

Restore individual files:

```cmd
git status
git restore <file>
```

## After the release commit

```cmd
git log --oneline
git revert <release_commit>
```

## Remove a local tag

```cmd
git tag -d v0.9.0
```

## Remove a remote tag

Use only when necessary:

```cmd
git push origin :refs/tags/v0.9.0
```

Runtime data under `data/`, `logs/` and `output/` is local and is not changed
by Git rollback.
