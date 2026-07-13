# Development Guide

## 1. Prepare the environment

Windows PowerShell or Command Prompt:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Verify the baseline

```cmd
git status --short
python -m pytest tests -q
```

Do not begin feature work from a failing or unexplained dirty baseline.

## 3. Create an atomic branch

Examples:

```cmd
git switch -c feature/pr-018-3-morning-brief-portfolio
```

Use one primary objective per branch. Avoid a permanent `develop` branch unless the project genuinely needs it; the current recommended model is short-lived branches into protected `main`.

## 4. Implement safely

- Read the existing test closest to the behavior first.
- Prefer domain objects over parallel dictionaries.
- Preserve optional-input behavior.
- Avoid live-network tests.
- Do not change financial configuration as a side effect of code cleanup.
- Keep functions focused and typed where practical.

## 5. Validate

Minimum:

```cmd
python -m pytest tests -q
```

For focused iteration:

```cmd
python -m pytest tests/test_relevant_module.py -q
```

Run the full suite before commit.

## 6. Update living documentation

Update at least the affected entries in:

- `docs/ATLAS_CONTEXT.md`;
- `docs/FEATURES_STATUS.md`;
- `docs/BACKLOG.md`;
- `docs/ROADMAP.md`;
- `docs/CHANGELOG.md`.

## 7. Commit and review

A commit message should identify the logical delivery, for example:

```text
feat: add a read-only dashboard summary
```

Before merging, review:

- diff scope;
- tests and output contracts;
- generated/untracked files;
- documentation consistency;
- rollback implications.
