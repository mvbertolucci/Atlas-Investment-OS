# Atlas Investment OS

Atlas is a modular investment decision platform that transforms market and
fundamental data into transparent scores, decisions, theses, portfolio
intelligence and reports.

## Current release

`v1.2.0`

Development baseline: `PR-033` plus point-in-time data acquisition on release
`v1.2.0`.

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
- Explicit market-universe eligibility and data-coverage contract
- Market/sector analytical ranking with governed candidate safeguards
- Dated 503-security research-universe snapshot, separate from the watchlist
- Retriable, checkpointed collection of that universe in bounded batches
- Constrained, equal-weight advisory model portfolio over the broad ranking
- Point-in-time historical-data contract for observations, constituents and
  delistings
- Deterministic walk-forward replay with SEC fundamentals, paired historical
  prices and split-consistent market capitalization
- Two-fiscal-year point-in-time Piotroski F-Score with governed Deal Breaker
- Versioned eligible-U.S.-market percentile reference shared by watchlist,
  portfolio and single-ticker analysis, with governed sector-relative features
- Weighted data coverage, enforced critical features, source/freshness quality
  gates and explicit uncertainty penalties for missing risk evidence
- Typed provider failures with timeout, exponential retries and rate limiting
- Per-field timestamps and explicit present/missing/unavailable/invalid/stale/
  not-applicable evidence states
- Immutable SHA-256 raw snapshots and critical-field second-source
  fallback/confirmation contract
- SEC Company Facts confirmation/fallback for comparable reported fundamentals
  and annual FCF/EBITDA fallback, with period/definition alignment
- Typed `PipelineContext` and explicit execution stages with validated input
  and output contracts
- Narrow typed runtime, ticker, collection, scoring, history, intelligence and
  reporting service facades; no module namespace injection
- Concrete collection and scoring application services outside `run_all.py`,
  with backward-compatible public wrappers
- Concrete historical application service for previous-run context, SQLite
  snapshots and Outcome Analytics
- Concrete intelligence application service for portfolio, watchlist tracking
  and Atlas Report publication
- Concrete reporting application service for Excel, Morning Brief, priority,
  performance validation and dashboard publication
- Concrete ticker-analysis application service for governed single-symbol
  scoring and one-pager publication
- Concrete operational runtime service for settings, Health Check, console and
  execution metrics

## Current integration status

The company-analysis pipeline is integrated end to end through explicit typed
stages in `orchestration/pipeline.py`; `run_all.py` is the stable CLI and
composition root:

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
The analytical track now defines a versioned U.S. liquid-equity research
universe. The Market Mapper publishes `output/universe_report.json` and the
Dashboard market view without filtering the existing scoring pipeline.
Eligible companies are ranked using existing Atlas scores and absolute
Deal-Breaker safeguards in `output/dados/ranking_report.json`.
The broad research snapshot has a resumable batch collector; normal
`run_all.py` executions still use the smaller personal watchlist.
The point-in-time contract feeds a deterministic walk-forward replay mechanism.
Real historical coverage remains incomplete and Atlas does not yet publish
backtest performance.

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

Agent entry points:

- Codex and shared rules: `AGENTS.md`
- Claude Code: `CLAUDE.md` and `docs/CLAUDE_CODE.md`

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
- `docs/POINT_IN_TIME_DATA.md`
- `docs/RELEASE_NOTES.md`
