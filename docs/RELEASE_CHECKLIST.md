# Release Checklist

## Repository

- [ ] Working tree is clean
- [ ] Runtime artifacts are ignored
- [ ] No temporary files remain in the root
- [ ] No patch ZIPs, caches or generated reports remain in the source tree

## Tests

- [ ] `pytest` passes
- [ ] `python run_all.py` passes
- [ ] The declared test baseline in `docs/ATLAS_CONTEXT.md` is current

## Outputs

- [ ] `output/latest.xlsx`
- [ ] `output/morning_brief.md`
- [ ] `data/atlas_history.db`
- [ ] `logs/atlas.log`
- [ ] `logs/execution_metrics.csv`

## Excel

- [ ] Ranking
- [ ] Summary
- [ ] Opportunity Analysis
- [ ] Decision Analysis
- [ ] Explainability
- [ ] Diagnostics
- [ ] Historical Trends
- [ ] History Summary

## Documentation

- [ ] `docs/ATLAS_CONTEXT.md` reflects the delivered baseline
- [ ] `docs/CHANGELOG.md` records the change
- [ ] `docs/FEATURES_STATUS.md` and `docs/BACKLOG.md` are synchronized

## Release

```cmd
git add .
git commit -m "release: Atlas <version>"
git tag -a <version> -m "Atlas Investment OS <version>"
git status
```

For a configured remote:

```cmd
git push
git push origin <version>
```
