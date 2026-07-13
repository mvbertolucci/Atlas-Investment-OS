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
point-in-time `timing`-factor increment):

- branch: `master`;
- latest functional commits (pushed to `origin/master`):
  - `4fd9e6c fix(backtesting): normalize historical stock splits`;
  - `f1c2c8e feat(backtesting): derive point-in-time annual f-score`;
- a new, not-yet-committed increment on top of these: `backtesting/point_in_time_timing.py`
  (point-in-time `timing` factor derivation), wired into
  `backtesting/walk_forward.py`;
- confirm the current remote relation with `git status --short --branch` before
  any fetch, push or integration action;
- released version remains `v1.2.0`;
- development baseline is PR-033 plus point-in-time data acquisition plus the
  `timing` factor family;
- validation baseline is 515 passing tests and 87.80% production coverage.

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
  score into the unchanged governed `Piotroski baixo` Deal Breaker;
- derives `rsi_14`, `momentum_3m/6m/12m` and `distance_52w_high`
  (`backtesting/point_in_time_timing.py`) from a continuous, split-adjusted
  price series reconstructed per symbol at each cutoff, mirroring
  `analytics/indicators.py`'s exact formulas and trading-day windows; proven
  that forward/reverse splits create no artificial momentum and that a
  not-yet-known split or a future price never leaks into an earlier replay.

No portfolio-performance result or calibration exists yet. Governed score
weights, Deal Breakers, ranking, decisions, the personal watchlist and
`run_all.py` remain unchanged.

The recommended next bounded task is **remaining point-in-time valuation
coverage**: `forward_pe` (needs analyst estimates), `ev_ebitda` (needs a
depreciation/amortization tag, not yet collected), `ev_ebit` (needs a clean
total-debt figure), `peg` (needs a growth estimate) and
`shareholder_yield`/`fcf_yield` (need dividend/FCF tags not yet collected).
`target_upside` also remains unbuilt and needs a genuine point-in-time
analyst-target source, not a current-data substitute. Running the
broad-market/ADR collections (`docs/UNIVERSE_SOURCES.md`) is a valid,
independent alternative next step if data-source acquisition rather than
factor coverage is preferred.

Before implementation, read:

- `docs/SEC_EDGAR_DATA.md`;
- `docs/PRICE_HISTORY_DATA.md`;
- `docs/POINT_IN_TIME_DATA.md`;
- `docs/ANALYTICAL_ROADMAP.md`;
- `docs/BACKLOG.md`;
- `backtesting/point_in_time.py`;
- `backtesting/point_in_time_fundamentals.py`;
- `backtesting/point_in_time_valuation.py`;
- `backtesting/point_in_time_timing.py`;
- `analytics/fundamentals.py` (existing live formulas to mirror, where they
  exist);
- the `valuation` section of `config/features.yaml`.

Preserve the current as-of and multi-period contracts. Do not substitute current
data, change governed configuration or include PR-034 performance/risk analytics
in the same change. Each new ratio must stay assign-if-absent (never overwrite a
value the input frame already supplies) and must leave a ratio missing, not
invented, when its raw components are unavailable at the cutoff -- the same
discipline already proven in `point_in_time_fundamentals.py` and
`point_in_time_valuation.py`.

### Ready-to-paste continuation prompt

```text
Read CLAUDE.md, docs/ATLAS_CONTEXT.md, docs/SEC_EDGAR_DATA.md and
docs/PRICE_HISTORY_DATA.md. Verify that git status is clean and that the
point-in-time timing-factor commit is present. Run the full test/coverage
gate; expect 515 tests and 87.80% production coverage. Then implement one
bounded increment: extend backtesting/point_in_time_valuation.py (or a new,
equally-scoped module) with as many of forward_pe, ev_ebitda, ev_ebit, peg,
shareholder_yield and fcf_yield as the currently collected raw SEC/price
fields honestly support -- state explicitly, per ratio, which remain
impossible without a new data source, rather than approximating them.
Preserve the assign-if-absent, missing-not-invented contract already used by
derive_point_in_time_ratios/valuation/timing. Add deterministic offline tests,
run the full gate, update living documentation and leave one atomic commit
with a clean tree. Do not change governed weights, thresholds, Deal Breakers,
run_all.py, portfolio performance/risk analytics, scheduling or live trading.
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
