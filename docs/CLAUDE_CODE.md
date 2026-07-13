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

Repository state prepared on 2026-07-13:

- branch: `master`;
- latest functional commits:
  - `4fd9e6c fix(backtesting): normalize historical stock splits`;
  - `f1c2c8e feat(backtesting): derive point-in-time annual f-score`;
- both functional commits were local and not pushed when this handoff was
  prepared;
- confirm the current remote relation with `git status --short --branch` before
  any fetch, push or integration action;
- released version remains `v1.2.0`;
- development baseline is PR-033 plus point-in-time data acquisition;
- validation baseline is 506 passing tests and 87.67% production coverage.

The executable point-in-time boundary and deterministic walk-forward mechanism
are complete. Historical inputs now include checkpointed SEC EDGAR fundamentals
and paired Yahoo prices. The implementation:

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
  score into the unchanged governed `Piotroski baixo` Deal Breaker.

No portfolio-performance result or calibration exists yet. Governed score
weights, Deal Breakers, ranking, decisions, the personal watchlist and
`run_all.py` remain unchanged.

The recommended next bounded task is **point-in-time timing-factor coverage**.
Before implementation, read:

- `docs/POINT_IN_TIME_DATA.md`;
- `docs/ANALYTICAL_ROADMAP.md`;
- `docs/BACKLOG.md`;
- `docs/SEC_EDGAR_DATA.md`;
- `docs/PRICE_HISTORY_DATA.md`;
- `backtesting/point_in_time.py`;
- `backtesting/point_in_time_fundamentals.py`;
- `backtesting/price_history.py`;
- `analytics/indicators.py`;
- `tests/test_indicators.py`;
- the `timing` section of `config/features.yaml`.

Preserve the current as-of and multi-period contracts. Do not substitute current
data, change governed configuration or include PR-034 performance/risk analytics
in the same change.

Important unit boundary: `HistoricalObservation(field_name="price")` now stores
the as-traded close because valuation needs the actual price/share units. Do not
feed that raw series directly into momentum across a split. For timing only,
construct a continuous series at each cutoff by dividing each earlier as-traded
price by the cumulative split ratios effective after that price and on or before
the cutoff's latest price date. Use only `snapshot.splits`; a future split must
not alter an earlier replay. Keep the as-traded `price` unchanged for
`market_cap`.

Suggested acceptance boundary:

1. derive `rsi_14`, `momentum_3m/6m/12m` and `distance_52w_high` using the
   existing indicator semantics and explicit trading-day windows;
2. use only price observations and split events visible at the cutoff;
3. prove forward and reverse splits do not create artificial momentum;
4. leave indicators missing when the required history is insufficient;
5. preserve any timing value already supplied and keep `target_upside` missing
   unless a genuine point-in-time analyst-target source is added separately;
6. add deterministic offline tests plus the full 80% coverage gate;
7. synchronize architecture, backlog, changelog and canonical handoff.

### Ready-to-paste continuation prompt

```text
Read CLAUDE.md, docs/ATLAS_CONTEXT.md, docs/POINT_IN_TIME_DATA.md and
docs/PRICE_HISTORY_DATA.md. Verify that git status is clean and that commits
4fd9e6c and f1c2c8e are present. Run the full test/coverage gate; expect 506
tests and 87.67% production coverage. Then implement one bounded increment:
point-in-time timing-factor derivation from the complete price history visible
in each AsOfSnapshot. Preserve the as-traded `price` used by valuation, but
construct a separate continuous timing series normalized only by splits already
effective at that cutoff. Mirror analytics/indicators.py semantics for rsi_14,
momentum_3m/6m/12m and distance_52w_high; do not invent target_upside or values
for insufficient windows. Prove no future price or split leaks backward, cover
forward/reverse splits, preserve preexisting timing fields, run the full gate,
update living documentation and leave one atomic commit with a clean tree.
Do not change governed weights, thresholds, Deal Breakers, run_all.py, portfolio
performance/risk analytics, scheduling or live trading.
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
