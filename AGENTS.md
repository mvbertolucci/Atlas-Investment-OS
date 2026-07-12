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
- Treat `config/model.yaml`, `config/weights.json` and `config/deal_breakers.json` as governed business configuration; explain any modification.
- Portfolio rebalance output is advisory only.
- Runtime artifacts in `output/`, `logs/` and local SQLite databases must not be committed.
- Never hide failing tests or weaken assertions merely to make CI pass.
- Keep PRs atomic: one primary objective per change set.

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
