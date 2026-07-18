# ADR-032 — Shared retry-on-lock for every atomic JSON write

**Status:** Accepted
**Date:** 2026-07-18

## Context

The repository lives under a OneDrive-synced folder. `Path.replace()` --
the final step of every atomic write pattern in this codebase (write to a
`.tmp` sibling, then rename over the target) -- can transiently raise
Windows `WinError 5` (`PermissionError`) when OneDrive's sync client
briefly locks the file. This was already identified and fixed once, in
`universe/collector.py::write_collection_state` and
`backtesting/sec_edgar_collector.py`'s equivalent (their tests literally
say `raise PermissionError("OneDrive lock")`), but the fix was never
extracted or propagated. It happened again in this session: the
`providers.market_cap_composition_prefetch --all` broad run (ADR-031)
crashed on exactly this error, in `sec_shares_cache.py`, a file that did
not exist when the original fix landed.

An audit found the same unprotected `temporary.replace(path)` pattern in
nine more places: four provider caches
(`massive_cache.py` x3 classes, `fmp_cache.py` x2 methods,
`finnhub_cache.py`, `sec_shares_cache.py`), the shared `_atomic_write`
helper in `massive_prefetch.py` (imported by five other prefetch CLIs:
`finnhub_prefetch`, `massive_float_prefetch`,
`massive_grouped_daily_prefetch`, `sec_public_float_audit`,
`market_cap_composition_prefetch`), and `scoring/reference.py`'s
`write_scoring_reference` -- the official ADR-012 scoring-reference
artifact, which had no retry protection at all.

## Decision

1. Extract the already-proven pattern into `storage/atomic_write.py`:
   `replace_with_retry` (the bounded-retry rename, `PermissionError` only
   -- any other exception propagates immediately, since retrying a real
   error would hide a bug) and `atomic_write_json` (write + retry-replace
   in one call, formatting kwargs passed through so each caller keeps its
   own `json.dumps` style).
2. Apply it at all eleven identified call sites (nine newly protected, two
   pre-existing ones deduplicated). `universe/collector.py` and
   `backtesting/sec_edgar_collector.py` keep their exact public
   `write_collection_state` signature (`replace_attempts`/`retry_delay`/
   `sleeper`) for backward compatibility, now delegating internally
   instead of duplicating the loop.
3. `massive_prefetch.py::_atomic_write` becomes a thin wrapper kept under
   its original name, since five other modules import it by that name --
   renaming would touch all of them for no behavioral gain.

## Consequences

- Newly protected: three `massive_cache.py` classes, `fmp_cache.py`'s two
  save methods, `finnhub_cache.py`, `sec_shares_cache.py`,
  `massive_prefetch.py::_atomic_write` (and its five importers
  transitively) and `scoring/reference.py::write_scoring_reference`.
- Every JSON artifact this repository writes atomically now retries a
  transient lock (10 attempts, 0.2s apart by default -- same defaults the
  original fix already proved live). None of this changes what gets
  written, only whether a rename transiently fails.
- `tests/test_atomic_write.py` covers the shared module directly
  (recovers within budget, re-raises once exhausted, never swallows a
  non-`PermissionError`, rejects a non-positive attempt count). The two
  pre-existing OneDrive-lock regression tests
  (`test_atomic_replace_retries_transient_permission_error` in
  `test_universe_collector.py` and `test_sec_edgar_collector.py`) still
  pass unchanged against the refactored implementation.
- No governed scoring value, weight or threshold changes.

## Rollback

Revert the ten call sites to their inline `temporary.replace(...)` and
delete `storage/atomic_write.py`. Nothing else imports it.
