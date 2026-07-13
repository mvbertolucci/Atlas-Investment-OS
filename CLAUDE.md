# Atlas Investment OS — Claude Code Entry Point

@AGENTS.md
@docs/ATLAS_CONTEXT.md
@docs/PROJECT_CONSTITUTION.md

## Session startup

Before changing files:

1. Run `git status --short --branch` and `git log -5 --oneline`.
2. Confirm that the working tree is clean or identify pre-existing user changes.
3. Read the relevant architecture, backlog and tests for the requested task.
4. State the intended scope and preserve unrelated work.

## Windows commands

Use the repository virtual environment when it exists:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe run_all.py
```

For the full regression gate:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --cov=. --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=80
```

## Repository safety

- Never use `git push --force`, destructive reset or broad file deletion.
- Do not commit `.env`, local databases, logs, reports, caches or credentials.
- Do not push, merge, tag or publish unless the user explicitly requests it.
- Do not change governed financial configuration without explaining the
  financial effect and adding focused regression tests.
- Keep one primary objective per commit and leave the working tree clean.

## Current handoff

- Released baseline: `v1.2.0` / `PR-019.6`.
- Validation baseline: 271 tests / 87.28% production coverage.
- v1.1 Integrated Portfolio Intelligence and v1.2 Outcome Analytics are
  complete.
- The next planned milestone is v2.0 Platform, beginning with a bounded,
  read-only dashboard contract.
