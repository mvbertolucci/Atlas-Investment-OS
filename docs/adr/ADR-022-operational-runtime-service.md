# ADR-022 — Operational runtime service

**Status:** Accepted
**Date:** 2026-07-17

## Context

After ADR-021, ticker analysis had left `RuntimeServices`, but `run_all.py`
still implemented settings loading, safe console encoding and summary-table
presentation. Health Check and execution metrics were also bound as unrelated
module functions. The composition root therefore retained operational
behavior despite every domain workflow having a concrete application owner.

## Decision

1. `application/runtime.py` owns `OperationalRuntimeService`.
2. The service receives root, config and metrics paths plus logger, Health
   Check, metrics and output ports explicitly.
3. It owns settings loading, Health Check delegation, console-safe text and
   summary-table presentation, and metrics persistence/presentation.
4. `RuntimeServices` retains shared `PipelinePaths` and logger for stage access
   but binds its operational callbacks directly to one concrete service.
5. Historical `run_all.load_settings()`, `_safe_console_text()` and
   `print_console_table()` remain thin compatibility wrappers constructed from
   current module paths and ports.
6. `run_all.py` remains the stable CLI and composition root; no output text,
   settings contract, health rule or metric format changes.

## Consequences

- Every pipeline responsibility now has a concrete owner outside `run_all.py`.
- Operational behavior is independently testable with injected output and
  persistence ports.
- Runtime paths are captured once per pipeline composition.
- Public CLI, helpers, console behavior and generated artifacts remain
  compatible.
- No scoring, portfolio, decision or provider semantics change.

## Migration and rollback

No caller, configuration or persisted-artifact migration is required.
Rollback can restore the thin implementations and direct function bindings in
`run_all.py`; settings, metrics and report files require no conversion.
