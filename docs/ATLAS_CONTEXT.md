# Atlas Investment OS — Project Context and Handoff

**Purpose:** canonical entry point for a new developer or coding agent.  
**Last synchronized baseline:** `PR-033` + real SEC EDGAR data acquisition + paired
historical price series + point-in-time `timing` factor derivation + extended
point-in-time valuation coverage (`ev_ebit`, `fcf_yield`, `shareholder_yield`)
plus deterministic PR-034 target, execution-evidence, total-return-evidence,
next-open execution, validation, per-sector return-contribution and
weighted-average factor-exposure cores. Watchlist/portfolio decoupling:
`config/watchlist.csv` is manually curated research symbols again, distinct
from `config/portfolio.csv` (real holdings); `run_all.merge_watchlist_with_portfolio`
merges the two in memory only, per run, and tags every row with an `origin`
(`portfolio` > `watchlist` hierarchy) that decision engines read instead of
recomputing provenance -- `portfolio.rebalance.build_sell_only_plan` refuses
to act on a holding whose verified origin is not `portfolio`, and
`ranking.RankedCompany.already_held` flags a portfolio-origin row so it is
never shown as an ordinary fresh candidate.

**Declared release:** `1.2.0` (v2.0 Platform work is merged to `master`; no version
bump has been cut yet — that is a deliberate release decision, not implied by
this document)
**Validation baseline:** 987 tests passing / 90.64% production coverage

## Current handoff — application boundaries complete

The typed pipeline binds concrete collection, scoring, history, intelligence,
reporting, ticker-analysis and operational-runtime services. `run_all.py` is
limited to governed path definitions, dependency construction, compatibility
wrappers and `main()`; no pipeline stage traverses it as a service locator.

The free FMP and Massive adapters are active with protected personal keys.
Massive Basic Ticker Details supplies targeted market cap without the denied
paid Ratios endpoint. Enterprise value composes that current market cap with
dated SEC debt and cash; short float prefers aligned Massive Float and falls
back to aligned FMP Float. Live checks produced market cap for AAPL, AVAV and
BNTX, EV for AAPL/AVAV, and short float for all three. BNTX EV remained
explicitly unavailable because comparable SEC components were incomplete.

FMP broad prefetch now has persistent TTL/negative caching, an atomic UTC daily
quota ledger, a 25-call interactive reserve and resumable batch/page collection.
The 2026-07-17 live scan used the 225-call prefetch budget and found market-cap
and float evidence for only 67/2,429 eligible symbols; enterprise evidence was
available for 6 before the ceiling. This is an actual Basic-entitlement limit,
not broad confirmation. Remaining fields stay `secondary_unavailable`.

Massive Float now uses a separate atomic, page-resumable market snapshot. The
2026-07-17 live run fetched seven pages and 6,662 records without errors,
covering 2,364/2,429 eligible symbols directly (97.32%). Dotted/hyphenated share
classes are reconciled; FMP contributes one additional dated fallback (`ET`),
for 2,365/2,429 combined availability (97.37%). The remaining 64 gaps are
explicitly unavailable, never replaced by outstanding shares. Their complete
SEC audit found 28 stale monetary values, 30 absent facts, 3 zeros and 3
provider/mapping failures. None can safely become a share count: Company Facts
does not disclose the exact price basis and the newest positive observation was
290 days old. Raw SEC evidence is content-addressed and the classification
report is ignored runtime data. The next work should proceed in this order:

1. **Finnhub added as primary live market_cap/enterprise_value source
   (2026-07-18, ADR-030)** — free tier, 60 calls/minute with no observed
   daily cap, one call returns vendor-computed `market_cap` and
   `enterprise_value` directly (no debt/cash composition needed, unlike
   Massive or FMP). Placed ahead of Massive in
   `application/collection.py`'s live per-symbol reconciliation chain;
   live-verified (AAPL) that it is really queried and recorded as the
   confirming source. Cannot feed Atlas's own Altman Z/ROIC/Interest
   Coverage formulas (no raw debt/cash on the free tier, only ratios) — SEC
   EDGAR is unchanged for those. A bounded 20-symbol broad-prefetch check
   ran with 0 errors; the full 2,429-symbol broad run (~45 minutes) has not
   been executed yet.
3. **Grouped Daily price mechanism landed (2026-07-18, ADR-033)** —
   `MassiveMarketDataProvider.fetch_grouped_daily` reads one Basic-plan bulk
   endpoint per trade date instead of the 8-hour per-symbol Ticker Details
   scan; live-verified against the real eligible universe: one call matched
   2,423/2,429 symbols (99.75%). The cache never expires (a past date's bars
   are immutable) and a prefetch CLI publishes coverage. Composing this price
   with SEC `shares_outstanding` into a broad `market_cap` snapshot is now
   implemented (2026-07-18, ADR-031) — `providers/market_cap_composition.py`
   + `market_cap_composition_prefetch`, with a 140-day alignment window
   (not 45; share count only moves via deliberate buybacks/issuance and is
   filed quarterly, unlike debt/cash -- widened from an initial 100 days
   after measuring the real age distribution of the broad run's gaps,
   consistent with SEC's worst-case quarterly filing cadence). Also found
   and fixed a real bug while investigating the gap: `backtesting/
   sec_edgar.py::extract_observations` aborted a company's entire
   extraction over one malformed XBRL entry in an unrelated field (ADR-034)
   -- now skips only that entry. Full 2,429-symbol broad run: **1,944
   composed (80.03%)**, no external vendor beyond Massive+SEC. Remaining
   gap (323 shares_unavailable, mostly closed-end funds with no 10-K/10-Q
   XBRL) needs a second shares-outstanding source, tracked in
   `docs/BACKLOG.md`.
4. Run the implemented historical execution and total-return adapters against
   a broad real dataset with explicit delisting evidence.
5. Run broad portfolio validation and publish coverage limitations before any
   calibration claim. Do not change governed scoring semantics without
   versioned out-of-sample evidence.

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

`run_all.py` is now the composition root rather than the owner of execution
order. It creates a typed `PipelineContext` and executes explicit stages from
`orchestration/pipeline.py`. Every stage declares its required input artifacts
and typed output; the runner fails fast on a missing dependency or an invalid
output contract. `orchestration/services.py` groups runtime, ticker,
collection, scoring, history, intelligence and reporting operations into
narrow typed facades. `run_all.py` binds functions to those facades explicitly
and no longer injects its module namespace into the pipeline. Collection and
scoring
implementations now live in `application/collection.py` and
`application/scoring.py`; the corresponding historical `run_all` functions are
compatibility wrappers only. Historical context, SQLite snapshots and Outcome
Analytics now have the same boundary in `application/history.py`. Portfolio
intelligence, watchlist tracking and Atlas Report publication are owned by
`application/intelligence.py`. Final Excel, Morning Brief, priority,
performance-validation and dashboard publication is owned by
`application/reporting.py`; the composition root binds one concrete instance
directly to `ReportingServices`. Governed single-symbol analysis and one-pager
publication are composed in `application/ticker.py` and exposed separately by
`TickerServices`, rather than as a runtime operation.

See `docs/ARCHITECTURE.md`'s "Integrated company-analysis pipeline" diagram
for the full step-by-step flow, including exactly where each governed
config file enters (that diagram is the single source for this -- it used
to be duplicated here in prose form, with its own drift risk; consolidated
2026-07-18). In short: `settings.json` + `watchlist.csv` in, Yahoo +
evidence-tracked secondary providers, factor scoring, Deal Breakers,
Decision Engine, `CompanyReport`, optional portfolio enrichment, SQLite
history/Outcome capture, then Excel/Morning Brief/execution metrics out.

### Portfolio behavior

- `config/portfolio.csv` is optional.
- When absent, the company pipeline continues normally.
- When present and valid, Atlas builds `output/dados/portfolio_report.json`.
- Excel includes six conditional portfolio worksheets.
- Morning Brief includes portfolio allocation, concentration, position
  highlights, warnings and advisory rebalance actions.

## 3. Key modules

| Area | Main locations | Status |
|---|---|---|
| Pipeline orchestration | `orchestration/pipeline.py`, `orchestration/services.py`, `run_all.py` | Typed stages and narrow service facades integrated; CLI preserved |
| Application services | `application/collection.py`, `application/scoring.py` | Concrete collection/scoring services integrated; `run_all` wrappers preserved |
| Historical application service | `application/history.py` | Previous-run context, snapshots and Outcome Analytics integrated; wrappers preserved |
| Intelligence application service | `application/intelligence.py` | Portfolio, watchlist and Atlas Report integrated; wrappers preserved |
| Reporting application service | `application/reporting.py` | Excel, Morning Brief, priority, performance validation and dashboard integrated; wrappers preserved |
| Ticker application service | `application/ticker.py` | Broad-reference single-symbol analysis and one-pager publication integrated; wrapper preserved |
| Providers and mapping | `providers/`, `storage/raw_snapshots.py`, `analytics/mapper.py`, `analytics/fundamentals.py`, `analytics/indicators.py` | Typed boundary, SEC confirmation, Massive Basic market cap/SEC-composed EV and market-wide cached Massive/FMP short-float composition integrated |
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
  current pipeline (business/valuation/financial/timing), plus the confidence
  cap applied when a required feature is missing.
- `config/data_quality.yaml`: source-quality, freshness and sector
  applicability policy.
- `config/deal_breakers.json`: observed-risk rules, sector exemptions and the
  missing-risk-evidence penalty.
- `config/ranking.yaml`: candidacy gates for confidence, required evidence,
  data coverage, source quality and freshness.
- `config/settings.json`: runtime paths plus provider timeout, retry, backoff,
  pacing, critical fields and raw-snapshot location.
- `config/provider_secrets.json`: ignored local provider identity and keys;
  create from `provider_secrets.example.json`. Never commit its SEC User-Agent
  contact, Massive API key or FMP API key.
- `config/watchlist.csv`: manually curated research symbols -- assets the
  user chose to track, not the real portfolio. Edited by hand only; never
  written to by the pipeline.
- `config/research_universe.csv`: dated broad research population, separate
  from the personal watchlist and collected only by explicit batch commands.
- `config/universe.yaml`: research eligibility, benchmark and rebalance policy.
- `config/model_portfolio.yaml`: advisory construction constraints.
- `config/portfolio.csv`: optional real portfolio input (gitignored,
  populated from the user's real holdings); start from
  `portfolio.example.csv`. Distinct file from `watchlist.csv` -- neither
  overwrites the other. `run_all.merge_watchlist_with_portfolio` merges the
  two **only in memory**, for the duration of one run, so every real holding
  gets a scored `CompanyReport` (required for the sell-only rebalance
  engine) without polluting the manually curated watchlist on disk.

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
- Expose views — `run_all.py` emits `output/dados/dashboard.json` (guarded by
  `dashboard_enabled`).
- REST API — `api/`, stdlib only, read-only (`docs/API_CONTRACT.md`).
- Python SDK — `sdk/`, HTTP or offline-file transport (`docs/SDK.md`).

Every increment is additive/read-only: no score, decision or existing output
changed. The analytical-method track now has priority: PR-027 defines the
market-universe contract; PR-028 integrates provider metadata, publishes
`output/universe_report.json` and exposes it in Dashboard `market`. PR-029 is
complete: it publishes `output/dados/ranking_report.json`, with market/sector ranks
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
  gitignored -- never committed) is populated and scored: `run_all.py`
  merges its symbols into the manually curated `config/watchlist.csv`
  **only in memory** for the duration of one run (see section 4 above),
  never overwriting either file, so every holding gets a `CompanyReport`.
  `portfolio.rebalance` gained a `sell_only` mode
  (now the default): flags SELL only for AVOID holdings, holds everyone
  else at current weight, never suggests buying more of an existing
  position -- freed cash is meant for new candidates from the screener, not
  internal reallocation. Every row in the merged, analyzed DataFrame also
  carries an explicit `origin` (`portfolio` > `watchlist`, and eventually
  `> universe`); `enrich_portfolio_from_analysis` verifies each `Holding`'s
  origin against that column, and `build_sell_only_plan` refuses to emit
  SELL or HOLD for any holding whose verified origin is not `portfolio` --
  a real regression test proved this was previously unguarded (a
  Portfolio built incorrectly from a non-portfolio symbol would have acted
  on it silently). See `docs/BACKLOG.md`'s "Portfolio workflow".
- **On-demand priority classification** (`priority/`): sell priority (current
  holdings, `action`/`reason`/`triggered_rules`/`priority` copied verbatim
  from the official `portfolio.sell_rules` rebalance -- never a second
  SELL/HOLD derived from Deal Breaker presence, per ADR-011) and buy
  priority (screener candidates, ranked by `candidate_rank`) -- pure
  presentation, no target weight, no sector cap. CLI
  (`python -m priority.cli`), `output/dados/priority_report.json`, API
  (`/priority`), SDK. See `docs/PRIORITY_REPORT.md`.
- **Two more screeners**: the broad US-market screener
  (`config/universe_market.yaml`, NASDAQ Trader source, USD 300 million
  floor) has completed its 7,093-symbol snapshot/collection and model run;
  6,959 observations produced 2,429 eligible companies. The 2026-07-17
  evidence-quality rerun produced 794 safeguarded
  candidates and a 20-position advisory portfolio, while 134 exhausted
  provider failures remain explicitly attributed. The US-listed ADR screener
  (`config/universe_adr.yaml`, same floor) reuses that collection; its
  completed policy pass produced 501 eligible companies, 219 candidates and
  a distinct 20-position portfolio. See `docs/UNIVERSE_SOURCES.md`.

`portfolio/model_portfolio.py` (`build_from_collection`/`main`) now accepts
`--universe-policy` / `--ranking-policy` / `--model-portfolio-policy` and
`--label` (defaults unchanged, so the S&P 500 invocation is byte-for-byte the
same as before) -- so ranking and buy-priority run over the broad-market or
ADR screener with distinct output filenames. The broad-market run now writes
the ignored `*_market` universe, ranking, full-candidate and model-portfolio
artifacts. The completed ADR pass writes the corresponding ignored `*_adr`
artifacts without overwriting the market or S&P 500 outputs.

**PR-033 (walk-forward) is now merged, but as a mechanism, not a real
backtest.** `backtesting/walk_forward.py` deterministically replays Atlas
decisions at explicit historical cutoffs through the unchanged, governed
`score_dataframe`, using only `PointInTimeDataset.as_of(decision_at)`
evidence visible at that time -- proven with synthetic, offline fixtures
(no network, no live provider). **No complete, broad point-in-time dataset
exists in this repository.** The bounded real SEC/price evidence described
below proves individual paths, but running the engine and PR-034 validation at
scale still needs historical membership, terminal events and complete return
coverage -- a separate, materially harder problem most free providers do not
solve. See `docs/WALK_FORWARD_BACKTEST.md`.

**PR-034 now has a bounded deterministic calculation core, not a real
performance result.** `backtesting/portfolio_validation.py` consumes explicit
dated weights and attributed total returns and calculates net/benchmark return,
volatility, drawdown, turnover, estimated costs and position concentration.
Missing returns or unresolved delistings suppress the aggregate summary. The
versioned offline runner requires explicit provenance and also reports sector
concentration when every sector is supplied. Point-in-time portfolio targets
now reuse the exact walk-forward scoring route plus governed universe/ranking/
portfolio policies, retain coverage gaps and config hashes, and require an
explicit execution date. A governed next-session-open layer now requires an
attributed session and every USD opening price before creating a rebalance.
An offline adapter now versions observed SPY-session/open-price evidence from
existing Yahoo bars with DST and split-unit correction. A second offline
adapter (`backtesting/total_return_evidence.py`) now versions
dividend-inclusive total-return evidence for holdings and the benchmark alike
from the same kind of Yahoo bars, compounding `(Close+Dividend)/previous_close`
day over day and applying PR-032 `DelistingRecord` terminal treatment
(`zero`/`cash` resolved explicitly; `successor` deliberately left `unresolved`
-- this single-symbol adapter has no evidence of a successor security's own
value). Each complete validation period now also reports per-sector return
contribution (`target_weight × asset_return`, summed per sector, always
adding up to exactly `gross_return`), reusing the existing
`PortfolioRebalance.sectors` mapping, and the portfolio's target-weighted
average exposure per scoring factor (`business`/`valuation`/`financial`/
`timing`), read directly from the governed scoring pass at each cutoff by
`backtesting/historical_portfolio.py` -- neither needed a new data source.
The factor summary is composition/tilt, not return decomposition: a
regression-based factor-*return* attribution remains a separate, larger
increment, needing a statistical methodology to validate and document. The
broad real artifacts (execution bars, total-return bars, delisting records)
and a broad run remain open; see `docs/HISTORICAL_MODEL_PORTFOLIO.md`,
`docs/HISTORICAL_EXECUTION.md`, `docs/EXECUTION_EVIDENCE.md` and
`docs/PORTFOLIO_VALIDATION.md`.

**Real progress on (1), now end to end:** `backtesting/sec_edgar.py` +
`backtesting/sec_edgar_collector.py` acquire 17 native fundamental fields
in checkpointed, resumable batches (verified against a real batch of
Atlas's own watchlist; `BEEF3.SA`, a B3-only listing with no US SEC
registration, correctly failed explicitly rather than being silently
dropped). `backtesting/point_in_time_fundamentals.py` derives the *ratios*
`config/features.yaml` actually scores on (`gross_margin`, `current_ratio`,
`roic`, `roe`, ...) from those raw fields, and
`backtesting/price_history.py` + `backtesting/point_in_time_valuation.py`
pair a historical Yahoo price series in to derive `market_cap`, `pe`, `pb`
and `altman_z` -- **and the full loop is proven**: replaying a real
walk-forward decision over real SEC + price data for Apple and Microsoft
produced derived gross margins of 48.6% / 68.2%, market caps of ~$4.1T /
~$3.1T, Altman Z of 10.9 / 8.2 (both safe zone), and two genuinely
different Investment Scores (48.4 AVOID / 58.9 HOLD) with Model Confidence
risen to 40.0% now that `valuation` factors are partially populated. Two
complete, consecutive 10-Ks now derive `f_score_annual` at each cutoff and
feed the governed Piotroski rule. `backtesting/point_in_time_timing.py` now
derives the `timing` factor family (`rsi_14`, `momentum_3m/6m/12m`,
`distance_52w_high`) from the same paired price series: it reconstructs a
continuous, split-adjusted close series per symbol at each cutoff (dividing
each earlier as-traded price only by split ratios effective after that price
and on or before the cutoff's latest visible price date, using only
`snapshot.splits`), then mirrors `analytics/indicators.py`'s exact formulas
and trading-day windows. Proven not to leak: a split not yet known at the
cutoff never adjusts the series, and a price beyond the cutoff never enters
it. Two new SEC EDGAR tags (`capital_expenditures`, `dividends_paid`) now
also unlock `enterprise_value`, `ev_ebit`, `free_cash_flow`, `fcf_yield`
and `shareholder_yield`, each mirroring the exact formula
`analytics/mapper.py` already uses live, with one documented adaptation:
`shareholder_yield`'s dividend leg divides aggregate `dividends_paid` by
`market_cap` (the live mapper instead uses a per-share
`dividend_rate / price`, since no clean per-share dividend tag is
collected). Still not complete: `forward_pe`/`peg` (need analyst
estimates, no free point-in-time source integrated) and `ev_ebitda` (the
live pipeline has no formula to mirror -- it passes through Yahoo's own
`enterpriseToEbitda` directly). `target_upside` (needs a genuine
point-in-time analyst-target source), historical index membership
and delistings all remain unbuilt. See `docs/SEC_EDGAR_DATA.md`
and `docs/PRICE_HISTORY_DATA.md` for the full "what is covered / what is
not" accounting.

The historical price layer now restores as-traded closes and applies explicit
point-in-time split events to the observed share count. `market_cap`, `pe`,
`pb`, `altman_z`, `ev_ebit`, `fcf_yield`, `shareholder_yield` and now the
`timing` factors therefore remain dimensionally consistent before and after
forward or reverse splits without leaking the event into an earlier cutoff.

**Open threads, in priority order:** (1) `forward_pe`/`peg`
(need analyst estimates), `ev_ebitda` (needs a live formula to mirror first)
and `target_upside` remain unbuilt -- each needs a new data source or design
decision, not just a tag addition; (2)
complete PR-034 by running the now-implemented execution/total-return
adapters against a broad real dataset (reference/selected-symbol bars plus
real `DelistingRecord` evidence, neither acquired yet) and running
validation at scale (today's real walk-forward verification covers 2
companies, one date).

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
- Live Investment and factor scores are percentile ranks against the versioned
  eligible U.S. broad-market reference, not the run's watchlist. Every scored
  row records universe/date/count/version; sector-sensitive governed features
  use sector distributions. Historical replay remains cutoff-local. A missing
  or incompatible artifact falls back explicitly to `CURRENT_BATCH`, which is
  not comparable with official-reference history. See `docs/SCORING_MODEL.md`
  and ADR-012.

## 9. First actions for a new Codex session

1. Read `AGENTS.md` and this document.
2. Run `git status --short` and `git log --oneline -10`.
3. Run `python -m pytest tests -q`.
4. Inspect the current task in `docs/BACKLOG.md`.
5. Before editing, identify affected contracts and existing tests.

Recommended first prompt:

> Read AGENTS.md and docs/ATLAS_CONTEXT.md. Verify the clean working tree and
> test baseline. Then inspect the leading open evidence task in BACKLOG.md,
> preserving public interfaces and governed financial configuration.
