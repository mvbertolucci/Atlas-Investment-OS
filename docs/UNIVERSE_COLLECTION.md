# Broad-Universe Collection

PR-030B collects the versioned research universe without changing the personal
watchlist or the normal `run_all.py` flow. One bounded batch is processed per
command and every completed symbol is written to an atomic local checkpoint.

## Run and resume

```powershell
.\.venv\Scripts\python.exe -m universe.collector
```

Without arguments, the collector selects the first batch that still contains
an incomplete symbol. Repeating the command therefore resumes the collection.
To inspect or rerun a particular boundary:

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
- failed symbols are retried and retain cumulative attempt counts;
- a success removes the prior failure entry;
- a checkpoint from another snapshot or constituent count is rejected.

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
