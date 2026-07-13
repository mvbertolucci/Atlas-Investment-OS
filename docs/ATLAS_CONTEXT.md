# Atlas Investment OS — Project Context and Handoff

**Purpose:** canonical entry point for a new developer or coding agent.  
**Last synchronized baseline:** `PR-033` + real SEC EDGAR data acquisition (first slice)
**Declared release:** `1.2.0` (v2.0 Platform work is merged to `master`; no version
bump has been cut yet — that is a deliberate release decision, not implied by
this document)
**Validation baseline:** 457 tests passing / 87.24% production coverage

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

- `config/features.yaml`: feature definitions and per-feature weights.
- `config/model.yaml`: `factor_weights` — the scoring weight vector used by the
  current pipeline (business/valuation/financial/timing).
- `config/deal_breakers.json`: risk penalty rules and sector exemptions.
- `config/settings.json`: runtime paths and provider settings.
- `config/watchlist.csv`: analyzed universe.
- `config/research_universe.csv`: dated broad research population, separate
  from the personal watchlist and collected only by explicit batch commands.
- `config/universe.yaml`: research eligibility, benchmark and rebalance policy.
- `config/model_portfolio.yaml`: advisory construction constraints.
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

**v2.0 — Platform (in progress).** Score-integrity hardening landed first
(dead `config/weights.json` removed, `model.yaml` is the single weight source,
governed config pinned by `tests/test_governed_config.py`, cross-sectional
scoring documented with a `watchlist_drift` safeguard — see
`docs/SCORING_MODEL.md` and `docs/OUTCOME_ANALYTICS.md`). Then four bounded,
read-only Platform increments, each its own merged PR:

- Dashboard contract — `dashboard/` (`docs/DASHBOARD_CONTRACT.md`).
- Expose views — `run_all.py` emits `output/dashboard.json` (guarded by
  `dashboard_enabled`).
- REST API — `api/`, stdlib only, read-only (`docs/API_CONTRACT.md`).
- Python SDK — `sdk/`, HTTP or offline-file transport (`docs/SDK.md`).

Every increment is additive/read-only: no score, decision or existing output
changed. The analytical-method track now has priority: PR-027 defines the
market-universe contract; PR-028 integrates provider metadata, publishes
`output/universe_report.json` and exposes it in Dashboard `market`. PR-029 is
complete: it publishes `output/ranking_report.json`, with market/sector ranks
and governed candidate safeguards. PR-030A adds the required broad source:
503 dated S&P 500 share classes in a separate research snapshot. PR-030B adds
checkpointed batch collection. PR-031 constructs a constrained, advisory model
portfolio from the completed checkpoint. PR-032 now defines the executable
point-in-time observation, constituent and delisting boundary. Deterministic
walk-forward execution and a prospective shadow portfolio follow in bounded
increments. Scheduling is deferred; Notifications
and the AI assistant still require explicit external decisions.

Since PR-032, the following are also merged, in parallel to the walk-forward
track (none of it changes governed scoring):

- **Real portfolio wired end to end.** `config/portfolio.csv` (real holdings,
  gitignored -- never committed) is populated and scored via
  `config/watchlist.csv`. `portfolio.rebalance` gained a `sell_only` mode
  (now the default): flags SELL only for AVOID holdings, holds everyone
  else at current weight, never suggests buying more of an existing
  position -- freed cash is meant for new candidates from the screener, not
  internal reallocation. See `docs/BACKLOG.md`'s "Portfolio workflow".
- **On-demand priority classification** (`priority/`): sell priority (current
  holdings, ranked by Investment Score, SELL/HOLD by Deal Breaker presence)
  and buy priority (screener candidates, ranked by `candidate_rank`) --
  pure classification, no target weight, no sector cap. CLI
  (`python -m priority.cli`), `output/priority_report.json`, API
  (`/priority`), SDK. See `docs/PRIORITY_REPORT.md`.
- **Two more screeners**, both infrastructure-only so far (no collection run
  yet): a broad US-market screener (`config/universe_market.yaml`, NASDAQ
  Trader source, USD 300 million floor -- a genuine small-cap floor, unlike
  the S&P 500 screener's USD 1 billion mid-cap-and-up floor) and a US-listed
  ADR screener (`config/universe_adr.yaml`, same floor, reuses the
  broad-market collection via a new `excluded_countries` policy field --
  no separate data source or collection). See `docs/UNIVERSE_SOURCES.md`.

`portfolio/model_portfolio.py` (`build_from_collection`/`main`) now accepts
`--universe-policy` / `--ranking-policy` / `--model-portfolio-policy` and
`--label` (defaults unchanged, so the S&P 500 invocation is byte-for-byte the
same as before) -- so ranking and buy-priority can run over the broad-market
or ADR screener with distinct output filenames the moment their collection
completes. **The collection itself is not started** (deliberately deferred,
expected to take substantially longer than the 503-name S&P 500 collection --
see `docs/UNIVERSE_SOURCES.md`).

**PR-033 (walk-forward) is now merged, but as a mechanism, not a real
backtest.** `backtesting/walk_forward.py` deterministically replays Atlas
decisions at explicit historical cutoffs through the unchanged, governed
`score_dataframe`, using only `PointInTimeDataset.as_of(decision_at)`
evidence visible at that time -- proven with synthetic, offline fixtures
(no network, no live provider). **No real historical point-in-time dataset
exists in this repository** (PR-032 deliberately excluded historical-data
acquisition, and none has been added since); running this engine against
real market history, and PR-034's return/risk validation, both still need
that dataset to be acquired first -- a separate, materially harder problem
most free providers do not solve (they do not expose "value as known on
date X" with revision history). See `docs/WALK_FORWARD_BACKTEST.md`.

**Real progress on (1):** `backtesting/sec_edgar.py` converts SEC EDGAR's
free, public XBRL filing data into real `HistoricalObservation` records --
verified against **live SEC data** for Apple Inc. (2,350 observations
across 15 native fundamental tags, cross-era tag-switch merging, correct
point-in-time reconstruction). `backtesting/sec_edgar_collector.py` adds a
checkpointed, resumable multi-ticker collector mirroring
`universe/collector.py`'s design -- verified against a real batch of
Atlas's own watchlist (`ASML`/`AVAV`/`BNTX` collected; `BEEF3.SA`, a
B3-only listing with no US SEC registration, correctly failed explicitly
rather than being silently dropped -- confirming SEC EDGAR's hard coverage
boundary). Still a small slice, not a complete dataset: roughly 10 of
Atlas's ~25 fundamental fields remain unmapped, no `EBIT`/`Working Capital`
derivation, no valuation multiples (need a paired price series), no
historical index membership, no delistings. See `docs/SEC_EDGAR_DATA.md`
for the full "what is covered / what is not" accounting.

**Open threads, in priority order:** (1) finish widening SEC EDGAR tag
coverage and decide the `EBIT`/`Working Capital` derivation; (2) pair a
historical price series for valuation multiples; (3) run the
broad-market/ADR collections when resumed; (4) PR-034 portfolio validation,
once a real dataset is usable end to end.

See `docs/ANALYTICAL_ROADMAP.md` and `docs/BACKLOG.md` for the full backlog.

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
- Investment and factor scores are cross-sectional percentile ranks within each
  run's watchlist batch, not absolute levels; identical fundamentals score
  differently when watchlist composition changes (measured swing up to ~11–15
  points on small watchlists). Outcome score-calibration pools buckets across
  decision dates and is only strictly comparable when the watchlist is stable —
  treat cross-run calibration as indicative. See `docs/SCORING_MODEL.md`.

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
