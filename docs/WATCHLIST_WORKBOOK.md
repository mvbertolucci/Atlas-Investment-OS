# Watchlist candidates workbook

## Purpose

`watchlist/promote.py`'s CLI (`python -m watchlist.promote SYMBOL "reason"`)
is the only way to write into `config/watchlist.csv`, by design: nothing in
the pipeline writes to it automatically (see `docs/BACKLOG.md`'s PR-021
"propose-only" decision -- inclusion always requires a conscious choice).
Typing exact CLI syntax per symbol is friction for a workflow the user does
repeatedly. This workbook is a friendlier front end for the same gate, not a
new decision path: nothing is promoted until the user explicitly marks a row
and runs the apply step.

## Workflow

1. Generate the workbook (needs the broad screeners already collected --
   `universe.collector --market`/`--adr` -- and `ranking.pipeline` having
   produced `research_ranking_report_market.json`/`_adr.json`):

   ```powershell
   .\.venv\Scripts\python.exe -m watchlist.candidates_workbook
   ```

   Writes `output/relatorios/watchlist_candidates.xlsx`: one row per
   screener candidate not already in `config/watchlist.csv` or held in
   `config/portfolio.csv`, with `Symbol`, `Name`, `Sector`, `Investment
   Score`, `Confidence`, `Candidate Rank`, a derived `Gatilho Sugerido`
   (same trigger-condition logic as the Atlas Report's "Sugestões para a
   watchlist" section) and `Motivo Sugerido`. Unlike that report section,
   this list has no diversification cap (`max_per_sector`) -- it is meant
   for browsing/choosing, not just the top picks. 40 blank rows follow for
   typing any ticker by hand, in or out of the candidate list.

2. Open the file, mark `Incluir` for any row you want (any non-empty value
   works -- "x", "sim", "1", whatever is fastest to type), optionally edit
   `Nota` to override the suggested reason, save.

3. Apply the marks:

   ```powershell
   .\.venv\Scripts\python.exe -m watchlist.apply_candidates_workbook
   ```

   Reads the saved workbook (default path matches step 1's output),
   promotes every marked row via the same `promote_to_watchlist` the manual
   CLI uses (same duplicate refusal, same `included_at`/`note` contract),
   and prints what was added, what was already present (skipped, not an
   error) and any failure. A row with `Gatilho Sugerido` filled carries that
   trigger condition into `config/watchlist.csv`; a hand-typed row with no
   suggested trigger is added with `trigger_condition` blank, exactly like
   today's manual CLI default.

## What this does not change

- `config/watchlist.csv` is still edited by this apply step alone, on the
  user's explicit action -- nothing upstream (screeners, ranking, the
  report) writes to it.
- `config/portfolio.csv` is never touched by either script.
- Symbols already in the watchlist are silently skipped, never duplicated
  or overwritten.
