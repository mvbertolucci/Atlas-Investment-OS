# Working with Atlas in Claude Code

## What is already prepared

Claude Code automatically loads the root `CLAUDE.md`. That file imports the
shared agent rules, current project handoff and product constitution so Codex
and Claude work from the same repository-owned source of truth.

Personal authentication and machine-specific settings must remain outside the
repository. Never store an Anthropic API key in this project.

## Windows prerequisites

Claude Code supports Windows through WSL or Git for Windows. This repository is
already a normal Git working tree and can be opened directly from its root.

After installing Claude Code and authenticating, verify the installation:

```powershell
claude --version
claude doctor
```

If native Windows cannot locate Git Bash, configure the standard Git for
Windows path for the current PowerShell session:

```powershell
$env:CLAUDE_CODE_GIT_BASH_PATH="C:\Program Files\Git\bin\bash.exe"
```

## Open the project

In PowerShell:

```powershell
Set-Location "C:\Users\marcu\OneDrive\Documents\Atlas Investimentos\Atlas_Investment_OS"
claude
```

Claude Code should load `CLAUDE.md` automatically. Use `/memory` inside Claude
Code to confirm the project memory files that were loaded.

## Safe first prompt

```text
Read CLAUDE.md and its imported project documents. Do not change files yet.
Verify git status, the v1.2.0 baseline and the full test gate. Then summarize
the architecture, current capabilities, governed financial configuration and
the next bounded backlog task.
```

## Current historical-validation handoff

Repository state prepared on 2026-07-13 (updated the same day after the
weighted-average factor-exposure increment). Codex is not in use for this
line of work right now -- everything below happens directly in Claude Code,
and pushes are being held back deliberately until explicitly requested:

- branch: `master`, **1 commit ahead of `origin/master`, not pushed** --
  confirm the current remote relation with `git status --short --branch`
  before assuming otherwise;
- latest commits:
  - `9298866 merge: integrate PR-034 deterministic validation core and
    offline evidence adapters` -- merges the seven-commit
    `codex/pr034-execution-evidence` line (portfolio validation core,
    versioned offline runner, historical targets, next-session-open
    execution, the execution-evidence and total-return-evidence adapters,
    plus the `universe.collector` auto-batch-selection fix);
  - `cd17d8e docs: fix post-merge handoff to reflect master, not the codex
    worktree`;
  - `e94ab07 feat(backtesting): add per-sector return contribution to
    portfolio validation`;
  - `fe555ce feat(backtesting): add weighted-average factor exposure to
    portfolio validation`;
  - `160e6ea fix(run_all): decouple the research watchlist from the real
    portfolio` -- restored `config/watchlist.csv` to its intended manually
    curated research symbols (it had been overwritten with the real
    portfolio's 24 symbols earlier the same day) and added
    `run_all.merge_watchlist_with_portfolio`, merged in memory only, never
    written back to either CSV;
  - a new, not-yet-committed increment, unrelated to PR-034: universe
    provenance. `merge_watchlist_with_portfolio` now tags every row's
    `origin` (`portfolio` > `watchlist` hierarchy), propagated through
    `collect_market_data`. `ranking.RankedCompany.already_held` flags a
    portfolio-origin row so it is never shown as an ordinary fresh
    candidate. `portfolio.rebalance.build_sell_only_plan` now verifies
    `Holding.origin` (filled by `enrich_portfolio_from_analysis` from the
    analyzed row) and refuses to act on anything not confirmed
    `portfolio` -- a real, previously unguarded gap, found and fixed by a
    regression test in the same change. See `docs/CHANGELOG.md`'s "Add
    universe provenance to the pipeline" and
    `docs/RANKING_METHOD.md#universe-provenance`;
- released version remains `v1.2.0`;
- validation baseline is 604 passing tests and 88.61% production coverage.

The broad-market universe collection (`universe.collector --market` against
`config/universe_market.yaml`) finished on 2026-07-14: 6,959/7,093 NASDAQ
Trader symbols collected (`data/market_collection_run.log`). Ranking over
that screener (`portfolio.model_portfolio --universe-policy
config/universe_market.yaml --label market`) has not been run yet -- that
and the ADR screener's own ranking pass are the natural next data-side
steps, independent of the code changes above.

The executable point-in-time boundary and deterministic walk-forward mechanism
are complete. Historical inputs now include checkpointed SEC EDGAR fundamentals
(17 native fields) and paired Yahoo prices. The implementation:

- rejects timezone-naive decision and availability timestamps;
- excludes observations unavailable at the decision cutoff;
- preserves source revisions without projecting restatements backward;
- reconstructs constituents from non-overlapping half-open intervals;
- retains delistings with explicit return treatment;
- restores Yahoo closes to as-traded prices and aligns SEC share counts through
  explicit forward/reverse `StockSplitRecord` events;
- retains the complete observation history visible at each cutoff;
- derives `f_score_annual` only from two complete, consecutive 10-K periods;
- merges partial 10-K/A amendments without erasing unaffected annual fields;
- normalizes the share-count comparison for splits and feeds the resulting
  score into the unchanged governed `Piotroski baixo` Deal Breaker;
- derives `rsi_14`, `momentum_3m/6m/12m` and `distance_52w_high`
  (`backtesting/point_in_time_timing.py`) from a continuous, split-adjusted
  price series reconstructed per symbol at each cutoff, mirroring
  `analytics/indicators.py`'s exact formulas and trading-day windows; proven
  that forward/reverse splits create no artificial momentum and that a
  not-yet-known split or a future price never leaks into an earlier replay;
- derives `enterprise_value`, `ev_ebit`, `free_cash_flow`, `fcf_yield` and
  `shareholder_yield` (`backtesting/point_in_time_valuation.py`), each
  mirroring the exact formula `analytics/mapper.py` already uses live, with
  one documented adaptation (`shareholder_yield`'s dividend leg uses
  aggregate `dividends_paid / market_cap`, not a per-share rate, since no
  clean per-share dividend tag is collected).

No real portfolio-performance result or calibration exists yet. The PR-034
chain now includes a deterministic metric core, versioned offline runner,
governed historical targets, next-session-open execution and two versioned,
offline adapters: `backtesting/execution_evidence.py` converts
already-acquired Yahoo-shaped bars into observed reference sessions and
split-restored opening prices, and `backtesting/total_return_evidence.py`
converts the same kind of bars (`Close`/`Dividends`) into dividend-inclusive
`AssetPeriodReturn` rows -- compounding `(Close+Dividend)/previous_close` day
over day across an explicit sequence of period boundaries, and applying
PR-032 `DelistingRecord` terminal treatment to the one period containing
`last_trade_on` (`zero`/`cash` resolved explicitly; `successor` always
reported `unresolved`, since a single-symbol adapter has no evidence of a
successor security's own value). Each complete validation period now also
reports per-sector return contribution (`target_weight × asset_return`,
summed per sector, always adding up to exactly `gross_return`), reusing the
existing `PortfolioRebalance.sectors` mapping, and the portfolio's
target-weighted average exposure per scoring factor (`business`/
`valuation`/`financial`/`timing`), read directly from the governed scoring
pass `backtesting/historical_portfolio.py` already runs at each cutoff --
`null` under the same absent/partial-coverage rule as `sector_hhi` in both
cases. The factor summary is composition/tilt, not a return decomposition;
see the boundary note below. Neither evidence adapter makes provider calls,
and no broad real execution or total-return artifact has been acquired yet.
Real `DelistingRecord` evidence and a broad real dataset are still required
before the metric core can produce honest performance evidence.
Governed score weights, Deal Breakers, ranking, decisions, the personal
watchlist and `run_all.py` remain unchanged.

**Remaining valuation gaps are no longer a bounded "extend coverage" task --
each needs a new data source or design decision, not a tag addition:**
`forward_pe`/`peg` need analyst estimates (no free point-in-time source
integrated), `ev_ebitda` has no live formula in `analytics/mapper.py` to
mirror (the live pipeline passes through Yahoo's own `enterpriseToEbitda`
directly -- inventing a from-scratch EBITDA definition with no live reference
to validate against would be a new, undocumented approximation), and
`target_upside` needs a genuine point-in-time analyst-target source.

Both offline adapters (`execution_evidence.py`, `total_return_evidence.py`),
per-sector return contribution and weighted-average factor exposure are all
now implemented and tested; only the adapters and sector contribution are
merged into `master` so far (factor exposure is the latest, not yet
committed at the top of this section). What remains in PR-034 is no longer
a bounded, purely offline coding increment -- both open threads need
something this session does not have on its own:

1. **Real bounded acquisition** (data acquisition, not code, needs an
   explicit go-ahead before provider calls): fetch real reference/
   selected-symbol Yahoo bars for `execution_evidence.py` and
   `total_return_evidence.py`, and source real `DelistingRecord` terminal
   events for whatever symbols actually delisted in the sample.
2. **Rank over the broad-market/ADR screeners** once the background
   collection completes: `portfolio.model_portfolio --universe-policy
   config/universe_market.yaml --label market`, then the same with
   `config/universe_adr.yaml --label adr` -- both commands are ready, no
   new code needed.

A regression-based factor-*return* decomposition (as opposed to the
exposure/composition summary just added) remains explicitly out of scope:
it needs a statistical methodology to validate and document, not just a
data join -- treat it as a separate, later design decision, not a bounded
increment to pick up casually.

Preserve the existing incomplete-period rule for (1): missing returns or
unresolved delistings must suppress aggregate metrics, never be silently
imputed.

Preserve the current as-of and multi-period contracts if any point-in-time
code is touched. Do not substitute current data, change governed
configuration, or include PR-034 performance/risk analytics claims in the
same change.

### Ready-to-paste continuation prompt

```text
Read CLAUDE.md, docs/ATLAS_CONTEXT.md, docs/PORTFOLIO_VALIDATION.md and
docs/BACKLOG.md fully before changing anything. Verify git status and that
master includes the PR-034 merge, per-sector return contribution,
weighted-average factor exposure (PortfolioRebalance.factor_exposures,
ValidationPeriod.factor_exposures), the watchlist/portfolio decoupling
(run_all.merge_watchlist_with_portfolio) and universe provenance
(origin column, RankedCompany.already_held, Holding.origin). Run the full
test/coverage gate; expect 604 tests and 88.61% production coverage. Report
any mismatch before editing. Do not push without explicit approval, even
after committing.

The broad-market universe collection (universe.collector --market against
config/universe_market.yaml) finished on 2026-07-14 -- 6,959/7,093 symbols
(data/market_collection_run.log). Ranking over that screener
(portfolio.model_portfolio --universe-policy config/universe_market.yaml
--label market) has not been run yet.

PR-034's remaining offline-coding thread (factor exposure) is done. What's
left needs either an explicit go-ahead for live provider calls (real
execution/total-return bar acquisition and delisting-record sourcing) or the
broad-market collection to finish first (ranking runs). Do not start either
without asking first -- summarize the current state and ask which of the two
threads to pursue, or whether to wait.
```

## Parallel work with Codex

Do not let both tools edit the same branch and working directory at the same
time. Use one of these operating modes:

1. Sequential work: finish, test and commit in one tool before opening the
   next tool.
2. Parallel work: give each tool a separate Git worktree and branch.

Before switching tools, always run:

```powershell
git status --short --branch
git log -3 --oneline
```

Commit only one logical objective at a time. Fetch and compare histories before
integrating work. Never solve divergence with a force push.

## Project validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --cov=. --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=80
```

The operational command is:

```powershell
.\.venv\Scripts\python.exe run_all.py
```

The operational command accesses configured market data and writes ignored
runtime artifacts under `data/`, `logs/` and `output/`.
