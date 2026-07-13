# Atlas v1.0 Acceptance Criteria

## Functional

- [ ] Load a valid portfolio CSV
- [ ] Reject invalid holdings
- [ ] Merge duplicate symbols
- [ ] Link holdings to CompanyReport
- [ ] Calculate total portfolio value
- [ ] Calculate current weights
- [ ] Calculate sector allocation
- [ ] Calculate country allocation
- [ ] Generate concentration warnings
- [ ] Calculate portfolio quality
- [ ] Generate rebalance suggestions
- [ ] Generate PortfolioReport
- [ ] Generate portfolio Excel sheet
- [ ] Generate portfolio Morning Brief

## Quality

- [ ] New modules have unit tests
- [ ] Existing tests remain green
- [ ] `python run_all.py` remains compatible
- [ ] No broker integration
- [ ] No silent data loss
- [ ] All warnings are explicit
- [ ] Documentation is updated

## Release

- [ ] `pytest`
- [ ] `python run_all.py`
- [ ] `git status`
- [x] `git tag -a v1.0.0`
