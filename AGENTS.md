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
6. Update the living documentation when architecture, status, commands or contracts change.
7. Report changed files, tests run, results, risks and the next recommended step.

## Non-negotiable rules

- Do not silently change scoring semantics, weights, thresholds or Deal Breakers.
- Treat `config/features.yaml` as the authoritative feature registry.
- Treat `config/model.yaml`, `config/features.yaml` and `config/deal_breakers.json` as governed business configuration; explain any modification. Their values are pinned by `tests/test_governed_config.py`.
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
