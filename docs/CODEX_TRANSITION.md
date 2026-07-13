# Transition to Codex — Step-by-Step Guide

This guide moves Atlas from ZIP-based handoffs to direct repository work.

## Stage 1 — Publish this prepared baseline

1. Extract the delivered ZIP into a new local folder.
2. Open Command Prompt in that folder.
3. Activate the virtual environment or create one.
4. Run:

```cmd
python -m pytest tests -q
```

5. Confirm all tests pass.
6. Check the repository remote:

```cmd
git remote -v
```

7. Push the prepared branch/commit to GitHub only after reviewing the diff.

## Stage 2 — Open Atlas in Codex

Codex can work through the Codex app, IDE extension, CLI or cloud. Choose the Atlas repository/project and ensure it opens at the repository root.

At the start of the first Codex thread, paste:

> Read AGENTS.md and docs/ATLAS_CONTEXT.md first. Do not modify anything yet. Run git status, show the last 10 commits, run the full test suite, and report whether the repository matches the documented release baseline.

Review its report before asking for feature work.

## Stage 3 — First real Codex task

Use this prompt:

> Inspect docs/BACKLOG.md and propose one bounded task from the next planned milestone. Preserve current financial semantics and output contracts. Add deterministic tests, run the full suite, update the living documents and show a concise diff and validation summary. Do not merge or push without my explicit approval.

## Stage 4 — Review before accepting

Ask Codex to show:

- changed files;
- behavioral changes;
- tests added;
- full-suite result;
- compatibility risks;
- generated files excluded from Git;
- proposed commit message.

Then inspect the diff. Approve commit/push/PR only when satisfied.

## Stage 5 — Ongoing operating model

For each task:

1. Start from clean `main`.
2. Create a short-lived feature branch.
3. Give Codex one atomic objective.
4. Require tests and living-document updates.
5. Review the diff.
6. Let CI pass.
7. Merge deliberately.

## Important context limitation

A new Codex thread should not be assumed to contain the complete ChatGPT conversation history. The repository documents are therefore the official memory. Add durable lessons to `AGENTS.md` or the relevant living document rather than relying on chat history.
