# Atlas Investment OS — Project Context and Handoff

**Purpose:** canonical entry point for a new developer or coding agent.  
**Last synchronized baseline:** `PR-019.6`
**Declared release:** `1.2.0`
**Validation baseline:** 271 tests passing / 87.28% production coverage

## 1. Product mission

Atlas transforms market and fundamental data into transparent investment scores, decisions, theses, portfolio intelligence and reports. It is a decision-support system, not an autonomous trading system and not a promise of investment performance.

Core design properties:

- reproducible calculations;
- explainable decisions;
- auditable inputs and outputs;
- explicit configuration;
- regression-tested behavior;
- advisory portfolio actions.

## 2. Current executable flow

The official entry point is `run_all.py`.

```text
settings.json + watchlist.csv
          ↓
Yahoo provider
          ↓
technical enrichment + derived fundamentals
          ↓
normalization
          ↓
Investment / Opportunity / Conviction scoring
          ↓
Deal Breakers + Decision Engine + Thesis
          ↓
CompanyReport objects
          ↓
optional portfolio.csv enrichment and PortfolioReport
          ↓
SQLite history + Outcome Snapshot capture and evaluation
          ↓
Outcome JSON + Excel + Morning Brief + execution metrics
```

### Portfolio behavior

- `config/portfolio.csv` is optional.
- When absent, the company pipeline continues normally.
- When present and valid, Atlas builds `output/portfolio_report.json`.
- Excel includes six conditional portfolio worksheets.
- Morning Brief includes portfolio allocation, concentration, position
  highlights, warnings and advisory rebalance actions.

## 3. Key modules

| Area | Main locations | Status |
|---|---|---|
| Providers and mapping | `providers/`, `analytics/mapper.py`, `analytics/fundamentals.py`, `analytics/indicators.py` | Integrated |
| Features and fundamentals | `analytics/`, `factors/`, `config/features.yaml` | Integrated |
| Scoring | `scoring/`, `models/`, governed config files | Integrated |
| Decision and thesis | `decision/` | Integrated |
| Company reports | `reports/report_models.py`, `reports/report_engine.py` | Integrated |
| Historical intelligence | `storage/history_db.py`, `analytics/history.py`, `analytics/alerts.py` | Integrated |
| Portfolio Intelligence | `portfolio/` | Integrated into main pipeline and Excel |
| Morning Brief | `reports/morning_brief.py` | Company and portfolio intelligence integrated |
| Operational health | `health/`, `metrics/`, `atlas_logger.py` | Integrated; 100% direct coverage |
| Outcome Analytics | `outcomes/`, `storage/history_db.py` | Capture, returns, attribution and reports operational |

## 4. Authoritative configuration

- `config/features.yaml`: feature definitions and registry.
- `config/model.yaml`: model composition.
- `config/weights.json`: scoring weights used by the current pipeline.
- `config/deal_breakers.json`: risk and exclusion rules.
- `config/settings.json`: runtime paths and provider settings.
- `config/watchlist.csv`: analyzed universe.
- `config/portfolio.csv`: optional real portfolio input; start from `portfolio.example.csv`.

Any change to business configuration must be explicit, tested and documented.

## 5. Stable contracts to preserve

- `python run_all.py` remains the official execution command.
- Missing optional portfolio input does not fail the company-analysis run.
- Existing Excel company worksheets and columns remain compatible.
- Portfolio rebalance suggestions remain advisory.
- History snapshots remain persisted through `storage/history_db.py`.
- Runtime artifacts are local and excluded from Git.

## 6. Current milestone and next task

### v1.1 — Integrated Portfolio Intelligence (complete)

Completed:

- PR-018.0 baseline cleanup and documentation synchronization;
- PR-018.1 portfolio integration into the main pipeline;
- PR-018.2 portfolio worksheets in Excel;
- PR-018.3 portfolio intelligence in Morning Brief;
- PR-018.4 operational coverage hardening;
- PR-018.5 legacy/configuration consolidation.

Latest functional milestone:

- **v1.2 — Outcome Analytics (complete).**
- PR-019.1 decision snapshot and persistence foundation is complete.
- PR-019.2 configurable horizons and automatic decision capture is complete.
- PR-019.3 future-price evaluation and horizon returns is complete.
- PR-019.4 hit rate and score calibration metrics is complete.
- PR-019.5 factor, rule and Deal Breaker attribution is complete.
- PR-019.6 JSON, Excel and Morning Brief outcome reports is complete.
- Next: define the first bounded v2.0 Platform increment before changing
  financial semantics.

## 7. Definition of done

A task is complete only when:

1. requested behavior is implemented;
2. regression and new tests pass;
3. no generated artifacts are committed;
4. relevant documentation is synchronized;
5. rollback or migration implications are stated;
6. the change set has one clear objective.

## 8. Known risks and technical debt

- Documentation created before PR-018.1 may describe Portfolio Intelligence as domain-only; prefer this document and current code.
- Historical persistence has a single owner: `storage/history_db.py`.
- Legacy feature and scoring engines were removed; `factors/engine.py` and
  `scoring/investment.py` are the executable scoring path.
- Scoring semantics are financially material and must not be refactored casually.
- External Yahoo data can be incomplete or unstable; tests should not depend on live network access.
- Outcome returns use the first valid Atlas price observed on or after each due
  date; evaluation lag remains explicit.

## 9. First actions for a new Codex session

1. Read `AGENTS.md` and this document.
2. Run `git status --short` and `git log --oneline -10`.
3. Run `python -m pytest tests -q`.
4. Inspect the current task in `docs/BACKLOG.md`.
5. Before editing, identify affected contracts and existing tests.

Recommended first prompt:

> Read AGENTS.md and docs/ATLAS_CONTEXT.md. Verify the repository baseline,
> coverage gate and tests. Then inspect the backlog and propose the next
> product milestone, preserving existing history and governed financial
> configuration.
