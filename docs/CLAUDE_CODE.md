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

## Current handoff — PR-032 to PR-033

Repository state prepared on 2026-07-13:

- branch: `master`;
- PR-032 implementation commit:
  `529a901 feat(backtesting): define point-in-time data contract`;
- confirm the current remote relation with `git status --short --branch` before
  any fetch, push or integration action;
- released version remains `v1.2.0`;
- development baseline is `PR-032`;
- validation baseline is 370 passing tests and 87.43% production coverage.

PR-032 is complete. It added the executable point-in-time boundary in
`backtesting/point_in_time.py`, its tests in `tests/test_point_in_time.py` and
the canonical contract in `docs/POINT_IN_TIME_DATA.md`. The implementation:

- rejects timezone-naive decision and availability timestamps;
- excludes observations unavailable at the decision cutoff;
- preserves source revisions without projecting restatements backward;
- reconstructs constituents from non-overlapping half-open intervals;
- retains delistings with explicit `cash`, `zero`, `successor` or `unresolved`
  return treatment.

No historical-data provider, walk-forward engine, portfolio-performance result
or calibration was added. Governed score weights, Deal Breakers, ranking,
decisions, the personal watchlist and `run_all.py` remain unchanged.

The next bounded task is **PR-033 — deterministic walk-forward backtesting**.
Before implementation, read:

- `docs/POINT_IN_TIME_DATA.md`;
- `docs/ANALYTICAL_ROADMAP.md`;
- `docs/BACKLOG.md`;
- `docs/MODEL_PORTFOLIO.md`;
- `backtesting/point_in_time.py`;
- `tests/test_point_in_time.py`.

PR-033 should consume `PointInTimeDataset.as_of(decision_at)` and recreate each
decision using only evidence visible at that cutoff. Keep it deterministic and
offline-testable. Do not use the current 2026-07-13 constituent snapshot for
earlier dates, silently drop unresolved delistings, invent unavailable
fundamentals, tune governed configuration or include PR-034 performance/risk
analytics in the same change.

Suggested acceptance boundary for PR-033:

1. versioned historical input manifest with source/config/code provenance;
2. explicit decision calendar and timezone;
3. deterministic as-of replay through existing Atlas analytical contracts;
4. incomplete decisions reported with machine-readable reasons;
5. reproducible local output that makes no performance promise;
6. focused tests plus the full 80% coverage gate;
7. synchronized architecture, backlog, changelog and canonical handoff.

### Ready-to-paste continuation prompt

```text
Read CLAUDE.md, docs/ATLAS_CONTEXT.md and docs/POINT_IN_TIME_DATA.md. Verify
that git status is clean and that commit 529a901 is present as the PR-032
baseline. Run the full test and coverage gate; expect 370 tests and 87.43%
production coverage. Then implement only PR-033: a deterministic,
offline-testable walk-forward engine that consumes
PointInTimeDataset.as_of(decision_at), recreates decisions using only evidence
available at each cutoff, records provenance and reports incomplete decisions
explicitly. Preserve all governed financial configuration and existing
public/output contracts. Do not add performance/risk analytics, calibration,
scheduling, live trading or silently substitute current data. Add focused
tests, synchronize living documentation and leave one atomic commit with a
clean working tree.
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
