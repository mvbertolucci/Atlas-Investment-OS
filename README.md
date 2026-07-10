# Atlas Investment OS

Atlas is a modular investment decision platform that transforms market and
fundamental data into transparent scores, decisions, theses and reports.

## Current release

`v0.9.0`

## Main capabilities

- Market data collection
- Data normalization and validation
- Business, Valuation, Financial and Timing scores
- Investment, Opportunity and Conviction scores
- Deal Breakers and risk penalties
- Decision Engine
- Investment Thesis
- Historical intelligence with SQLite
- Alerts and Morning Brief
- Excel reports
- Health Check, logging and execution metrics
- Automated tests

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
- `docs/ROADMAP.md`
- `docs/CHANGELOG.md`
- `docs/RELEASE_NOTES.md`
