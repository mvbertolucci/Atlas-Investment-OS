# PR-018.0 — Baseline Cleanup and Documentation Synchronization

## Objective

Create a clean and trustworthy development baseline before integrating
Portfolio Intelligence into the main Atlas pipeline.

## Changes

- Added `.gitattributes` to normalize text files as LF and retain CRLF only for
  Windows command files.
- Corrected the release displayed in `README.md` from v0.9.0 to v1.0.0.
- Updated Architecture, Roadmap, Backlog, Changelog and Release Notes.
- Added the current-state technical audit to `docs/`.
- Documented that Portfolio Intelligence is implemented and tested but not yet
  connected to the principal execution and presentation flows.

## Functional impact

No scoring, decision, portfolio or reporting algorithm is changed by this PR.
It is a baseline and documentation-only change.

## Validation

```cmd
pytest
```

Expected result: the complete existing suite passes without regression.

## Next PR

PR-018.1 — Integrate `PortfolioReport` generation into the main pipeline.
