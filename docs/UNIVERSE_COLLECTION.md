# Broad-Universe Collection

PR-030B collects the versioned research universe without changing the personal
watchlist or the normal `run_all.py` flow. One bounded batch is processed per
command and every completed symbol is written to an atomic local checkpoint.

## Run and resume

```powershell
.\.venv\Scripts\python.exe -m universe.collector
```

Without arguments, the collector selects the first batch that still contains
an unresolved symbol. A successful observation resolves a symbol normally. A
provider failure remains retryable until its cumulative attempts reach the
configured budget: the first attempt plus `research_collection_retries`.
After that budget is exhausted, the failure is considered resolved only for
automatic batch advancement, so one permanently unavailable ticker cannot
block every later batch. The failure entry and its attempt count remain in the
checkpoint and are reported when automatic collection has no batches left.
This behavior is shared by the default S&P 500 and `--market` collectors.
Repeating the command therefore resumes the collection. To inspect or rerun a
particular boundary, including exhausted failures:

```powershell
.\.venv\Scripts\python.exe -m universe.collector --batch-number 3
```

The defaults are explicit in `config/settings.json`:

- `research_universe_batch_size`: maximum symbols per command;
- `research_collection_state_path`: local checkpoint location;
- `research_collection_retries`: retries after the first provider attempt.

`--state` and `--retries` may override the last two values for an operational
run. The checkpoint is ignored by Git because it contains runtime market data.

## Checkpoint contract

The JSON checkpoint records its schema version, source snapshot date, expected
constituent count, timestamps, successful observations and provider failures.
It is replaced atomically after each attempted symbol. On resume:

- successful symbols are not requested again;
- failed symbols below the attempt budget are retried and retain cumulative
  attempt counts;
- failures at or above the attempt budget no longer block automatic batch
  advancement, but remain visible in `failures` and can be retried explicitly
  with `--batch-number`;
- a success removes the prior failure entry;
- a checkpoint from another snapshot or constituent count is rejected.

On OneDrive, transient file locks are retried. If a process stops between
writing the temporary checkpoint and replacing the primary file, the next run
recovers the newer valid temporary state instead of discarding that progress.

Each successful observation contains the same technical and derived fundamental
fields used before Atlas scoring. Price history and raw financial-statement
objects are intentionally omitted to keep the checkpoint bounded and JSON-safe.

## Boundaries

- The collector performs no scoring, ranking, decision or portfolio selection.
- It does not run automatically and does not schedule external requests.
- Provider availability and incomplete fundamentals remain observable failures
  or missing fields; they are not silently imputed.
- A current-constituent collection is not point-in-time historical evidence.
  That contract is a later, separate milestone.
