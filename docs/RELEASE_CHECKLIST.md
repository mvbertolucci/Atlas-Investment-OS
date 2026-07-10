# Release Checklist — v0.9.0

## Repository

- [ ] Working tree is clean
- [ ] Runtime artifacts are ignored
- [ ] No temporary files remain in the root
- [ ] No patch ZIPs remain in the source tree

## Tests

- [ ] `pytest` passes
- [ ] `python run_all.py` passes

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

## Release

```cmd
git add .
git commit -m "release: Atlas v0.9.0"
git tag -a v0.9.0 -m "Atlas Investment OS v0.9.0"
git status
```

For a configured remote:

```cmd
git push
git push origin v0.9.0
```
