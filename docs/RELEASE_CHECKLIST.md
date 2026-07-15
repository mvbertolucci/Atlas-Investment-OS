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

- [ ] `output/relatorios/latest.xlsx`
- [ ] `output/relatorios/morning_brief.md`
- [ ] `output/outcome_report.json`
- [ ] `output/dados/portfolio_report.json` when a portfolio is configured
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
- [ ] Outcome Summary
- [ ] Outcome Calibration when mature results exist
- [ ] Outcome Attribution when mature results exist

## Documentation

- [ ] `docs/ATLAS_CONTEXT.md` reflects the delivered baseline
- [ ] `docs/CHANGELOG.md` records the change
- [ ] `docs/FEATURES_STATUS.md` and `docs/BACKLOG.md` are synchronized
- [ ] `VERSION`, README and release notes declare the same version

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
