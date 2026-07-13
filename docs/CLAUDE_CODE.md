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
Set-Location "C:\Users\marcu\OneDrive\Documents\Atlas Investimentos\Atlas_Investment_OS_codex"
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
total-return-evidence increment):

- isolated worktree:
  `C:\Users\marcu\OneDrive\Documents\Atlas Investimentos\Atlas_Investment_OS_codex`;
- branch: `codex/pr034-execution-evidence`;
- latest functional commit:
  `4b61387 docs: refresh Claude Code handoff` (docs-only, on top of the six
  below), plus a new, not-yet-committed increment:
  `backtesting/total_return_evidence.py` (versioned, dividend-inclusive
  total-return evidence adapter);
- six prior local atomic functional commits on top of `master`:
  - `246eec2 fix(universe): advance past exhausted failures`;
  - `6129e81 feat(backtesting): add portfolio validation core`;
  - `bb0ab3f feat(backtesting): add versioned validation runner`;
  - `78c079e feat(backtesting): build historical portfolio targets`;
  - `44f559c feat(backtesting): govern historical execution`;
  - `e2016f7 feat(backtesting): version historical execution evidence`;
- none of those local commits has been merged or pushed;
- released version remains `v1.2.0`;
- validation baseline is 585 passing tests and 88.57% production coverage.

A separate Claude Code session is running the long-lived broad-market
collection in the main working directory. From this worktree, do not invoke
`universe.collector`, stop or inspect that process, or read/write its checkpoint
at `data/research_universe_collection_market.json`. Worktree source files are
isolated, but runtime process/checkpoint ownership remains with that session.

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
successor security's own value). Neither adapter makes provider calls, and no
broad real execution or total-return artifact has been acquired yet. Real
`DelistingRecord` evidence and a broad real dataset are still required before
the metric core can produce honest performance evidence.
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

Both offline adapters (`execution_evidence.py`, `total_return_evidence.py`)
are now implemented and tested. What remains in PR-034 is no longer a
bounded offline-code increment on its own -- it splits into two different
kinds of work:

1. **Sector and factor contribution without look-ahead** (still offline,
   still a coding task): attribute each complete period's return to the
   sector/factor exposures known at that cutoff, without projecting a later
   exposure backward. First read `docs/PORTFOLIO_VALIDATION.md`,
   `backtesting/portfolio_validation.py` (`ValidationPeriod`'s existing
   `sector_hhi`/`maximum_sector_weight` fields are the closest existing
   precedent) and their tests.
2. **Real bounded acquisition** (data acquisition, not code): fetch real
   reference/selected-symbol Yahoo bars for `execution_evidence.py` and
   `total_return_evidence.py`, and source real `DelistingRecord` terminal
   events for whatever symbols actually delisted in the sample. This needs
   an explicit go-ahead before making provider calls, mirroring how the
   broad-market universe collection was a separate, explicitly-approved step
   from the code that made it possible.

Preserve the existing incomplete-period rule in either case: missing returns
or unresolved delistings must suppress aggregate metrics, never be silently
imputed.

Preserve the current as-of and multi-period contracts if any point-in-time
code is touched. Do not substitute current data, change governed
configuration, or include PR-034 performance/risk analytics in the same
change.

### Ready-to-paste continuation prompt

```text
Read CLAUDE.md, docs/ATLAS_CONTEXT.md, docs/PORTFOLIO_VALIDATION.md and
docs/BACKLOG.md fully before changing anything. Work only in the isolated
Atlas_Investment_OS_codex worktree. Verify that branch
codex/pr034-execution-evidence is clean and that its history includes both
e2016f7 and the total-return-evidence commit on top of it. Run the full
test/coverage gate; expect 585 tests and 88.57% production coverage. Report
any mismatch before editing.

A separate Claude Code session owns a live long-running broad-market
universe.collector --market process in the main working directory. Do not
invoke or interfere with that collector and do not read or write
data/research_universe_collection_market.json from this worktree.

Then implement the next smallest offline PR-034 increment: sector and factor
contribution for each complete validation period, attributed only from
exposures known at that period's cutoff -- never a later exposure projected
backward. Mirror the existing sector_hhi/maximum_sector_weight precedent in
backtesting/portfolio_validation.py for how partial/absent coverage should
degrade to null rather than an invented classification. Add deterministic
tests, run the focused and full coverage suites, update living documentation
and leave one atomic local commit with a clean tree. Show the diff and
validation summary. Do not merge or push without explicit approval. Do not
make provider calls or change governed weights, thresholds, Deal Breakers,
run_all.py, scheduling or live trading.
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
