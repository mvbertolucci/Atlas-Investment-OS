# Atlas Investment OS — Agent Instructions

Read this file before changing the repository. Then read `docs/ATLAS_CONTEXT.md`.

## Mission

Evolve Atlas as a reproducible, auditable and explainable investment decision system. Preserve existing behavior unless the task explicitly changes it.

## Required workflow

1. Inspect the relevant code, tests and authoritative configuration before editing.
2. Make the smallest coherent change that completes the requested task.
3. Preserve public interfaces and output contracts unless a migration is documented.
4. Add or update tests for every behavioral change and bug fix.
5. Run `python -m pytest tests -q` after changes.
6. If the change touches field-evidence status semantics, the required-feature
   confidence gate, provider reconciliation, or scoring/valuation weights, a
   green synthetic test suite is not sufficient exit criteria — also run
   `python run_all.py --portfolio` against the real portfolio and read the
   resulting `output/dados/portfolio_report.json` decisions before calling the
   task done. Two real incidents motivate this: `df13423` (2026-07-17) added
   `scoring/reference.py::write_scoring_reference` without the already-known
   OneDrive file-lock retry (the same bug had been fixed twice before
   elsewhere in this repo but never extracted to a shared utility), only
   caught when a broad background run failed days later; `92a8b93`
   (2026-07-17) conflated `stale` with `missing` in the required-feature gate,
   which sat undetected in master until 2026-07-20, when the pipeline was
   first run against the real portfolio and 57/57 holdings capped at
   `Model Confidence: 59`, silently disabling the sell/buy engine in
   production. Both bugs passed every synthetic/unit test that existed at
   merge time; neither would have survived one real `--portfolio` run. See
   ADR-032, the "stale" fix in `STATUS.md` §6 (2026-07-20), and ADR-037.
7. Update the living documentation when architecture, status, commands or contracts change.
8. Report changed files, tests run, results, risks and the next recommended step.

## Non-negotiable rules

- Do not silently change scoring semantics, weights, thresholds or Deal Breakers.
- Treat `config/features.yaml` as the authoritative feature registry.
- Treat `config/model.yaml`, `config/features.yaml`, `config/deal_breakers.json`,
  `config/data_quality.yaml` and `config/ranking.yaml` as governed business
  configuration; explain any modification. Their values are pinned by tests.
- Portfolio rebalance output is advisory only.
- Runtime artifacts in `output/`, `logs/` and local SQLite databases must not be committed.
- Never hide failing tests or weaken assertions merely to make CI pass.
- Keep PRs atomic: one primary objective per change set.

## Multi-agent coordination

This repository may be worked on by more than one coding agent or tool (e.g. Claude Code, ChatGPT/Codex) in the same session or across sessions, sometimes without the human relaying context between them. Git is the only reliable handoff -- never assume the working tree is clean or reflects only your own edits.

1. Reconcile before touching anything: `git fetch && git status && git log --oneline -10`. If the working tree already has uncommitted changes you did not make, investigate before editing, reverting or resetting -- it is very likely another agent's in-progress work, not stray or corrupt state.
2. Never run a destructive git command (`reset --hard`, `checkout --`, `clean -f`) without first confirming there is nothing uncommitted that is not yours. When in doubt, stash (`git stash -u`) instead of discarding.
3. Commit before ending a turn, even if the task is not finished. A branch with a WIP commit is visible to the next agent; uncommitted edits sitting in the working tree are invisible until someone happens to run `git status`.
4. One agent per checkout at a time. If two tools need to work concurrently, use `git worktree add ../<name> <branch>` so each has its own working tree against the same repository, instead of sharing one directory.
5. Keep branches and PRs atomic per agent turn (see "Keep PRs atomic" above) -- do not fold an unrelated in-progress change from another agent into your own commit without calling it out explicitly in the message.

## Primary commands

```bash
python -m pip install -r requirements.txt
python -m pytest tests -q
python run_all.py
```

## Workstation-local runtime storage

- `data/raw_snapshots/` is the portable default, but on Marcus's Windows
  workstation `ATLAS_RAW_SNAPSHOT_PATH` points to
  `C:\Users\marcu\AppData\Local\Atlas_Investment_OS\raw_snapshots` so immutable
  provider evidence does not consume the 5 GB OneDrive quota.
- Always resolve the location through
  `storage.raw_snapshots.resolve_raw_snapshot_path`; never assume snapshots are
  inside the checkout or replace the tracked default with a machine-specific
  absolute path.
- The external directory is runtime evidence and is not in Git or OneDrive.
  Back it up separately before disk replacement or Windows reinstallation.
- A process started before the environment variable was configured must be
  restarted before collecting data, otherwise it may use the portable default.

## Source-of-truth documents

- Project state and handoff: `docs/ATLAS_CONTEXT.md`
- Architecture and boundaries: `docs/ARCHITECTURE.md`
- Product rules: `docs/PROJECT_CONSTITUTION.md`
- Feature status: `docs/FEATURES_STATUS.md`
- Backlog and next work: `docs/BACKLOG.md`
- Development process: `docs/DEVELOPMENT_GUIDE.md`
- Testing policy: `docs/TESTING_GUIDE.md`
- Decisions: `docs/DECISIONS.md` and `docs/adr/`

If documents conflict with executable code, verify the code and tests, then update the stale document in the same change.
