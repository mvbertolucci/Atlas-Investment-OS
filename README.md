# Atlas Investment OS

Atlas is a modular investment decision platform that transforms market and
fundamental data into transparent scores, decisions, theses, portfolio
intelligence and reports.

## Current release

`v1.0.0`

Development baseline: `PR-019.6`.

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

Portfolio Intelligence is integrated into the main pipeline, Excel outputs and
Morning Brief. Operational coverage is hardened with an enforced 80% CI floor.
Outcome Analytics captures decision snapshots automatically using configurable
evaluation horizons, persists realized returns and calculates directional hit
rate plus Opportunity/Conviction calibration.
Outcome attribution also relates returns to factor-score bands, final decisions
and named Deal Breakers.
Outcome summaries are published to JSON, conditional Excel worksheets and the
Morning Brief without changing scoring or decision semantics.

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

- `AGENTS.md` (coding agents and Codex)
- `docs/ATLAS_CONTEXT.md` (canonical project handoff)
- `docs/CODEX_TRANSITION.md` (step-by-step migration)
- `docs/QUICKSTART.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/BACKLOG.md`
- `docs/CHANGELOG.md`
- `docs/OUTCOME_ANALYTICS.md`
- `docs/RELEASE_NOTES.md`
