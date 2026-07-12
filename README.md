# Atlas Investment OS

Atlas is a modular investment decision platform that transforms market and
fundamental data into transparent scores, decisions, theses, portfolio
intelligence and reports.

## Current release

`v1.0.0`

Development baseline: `PR-018.0`.

## Main capabilities

- Market and fundamental data collection
- Data normalization and validation
- Business, Valuation, Financial and Timing scores
- Investment, Opportunity and Conviction scores
- Deal Breakers and risk penalties, including sector-aware rules
- Decision Engine and Investment Thesis
- Historical intelligence with SQLite
- Alerts and Morning Brief
- Excel reports
- Portfolio import and holdings model
- Allocation and concentration analysis
- Portfolio quality, ranking and advisory rebalance suggestions
- Health Check, logging and execution metrics
- Automated regression tests

## Current integration status

The company-analysis pipeline is integrated end to end through `run_all.py`:

```text
Providers -> Factors -> Scores -> Decision -> Thesis -> History -> Reports
```

Portfolio Intelligence is implemented and tested as a domain module. Its
connection to the main pipeline and presentation outputs is the next delivery
track (`PR-018.1` through `PR-018.3`).

## Quick start

```cmd
.venv\Scripts\activate
pip install -r requirements.txt
pytest
python run_all.py
```

Generated artifacts are stored locally in:

- `output/`
- `logs/`
- `data/atlas_history.db`

These runtime artifacts should not be committed to Git.

## Documentation

Start with:

- `docs/QUICKSTART.md`
- `docs/ARCHITECTURE.md`
- `docs/ATLAS_AUDIT_CURRENT_STATUS.md`
- `docs/ROADMAP.md`
- `docs/BACKLOG.md`
- `docs/CHANGELOG.md`
- `docs/RELEASE_NOTES.md`
