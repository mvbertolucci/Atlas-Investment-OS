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

- Released version: `v1.2.0`; development baseline: `PR-033` + real SEC
  EDGAR data acquisition + paired historical price series, now end to end
  (15 fields, checkpointed collector, ratio derivation, valuation
  derivation).
- Validation baseline: 487 tests / 87.41% production coverage.
- v1.1 Integrated Portfolio Intelligence and v1.2 Outcome Analytics are
  complete.
- v2.0 Platform is in progress. The point-in-time data contract is complete;
  the walk-forward *mechanism* (`backtesting/walk_forward.py`) is merged.
  `backtesting/sec_edgar.py` + `sec_edgar_collector.py` acquire 15 native
  fundamental fields in checkpointed, resumable batches;
  `point_in_time_fundamentals.py` derives the *ratios*
  `config/features.yaml` actually scores on; `price_history.py` +
  `point_in_time_valuation.py` pair a Yahoo daily close series to derive
  `market_cap`, `pe`, `pb` and `altman_z`. **The full loop is proven
  against live SEC + price data**: replaying a real decision for Apple and
  Microsoft produced derived gross margins matching each company's real
  historical range (48.6% / 68.2%), market caps of ~$4.1T / ~$3.1T, Altman
  Z of 10.9 / 8.2 (safe zone), and two genuinely different Investment
  Scores (48.4 AVOID / 58.9 HOLD) with Model Confidence risen to 40.0%.
  Still not a complete historical dataset -- `f_score_annual` (needs two
  fiscal years), the rest of `valuation`, the `timing` factor family, and a
  stock-split correction for `market_cap` before a company's most recent
  split are unbuilt; see `docs/SEC_EDGAR_DATA.md` and
  `docs/PRICE_HISTORY_DATA.md`. In parallel: the real portfolio is wired
  end to end (`portfolio.rebalance_mode = "sell_only"` by default), an
  on-demand sell/buy priority classification exists (`priority/`), two more
  screeners (broad US market, US-listed ADRs) are infrastructure-only, and
  `portfolio/model_portfolio.py` can run ranking over any of the three
  screeners via `--universe-policy`/`--label` — see `docs/ATLAS_CONTEXT.md`
  section 6.
- Open threads, in priority order: (1) correct `market_cap` for stock
  splits (Yahoo's price is retroactively split-adjusted, SEC's
  `shares_outstanding` is not); (2) two-fiscal-year replay for
  `f_score_annual`; (3) extend valuation/timing coverage using the paired
  price series; (4) run the broad-market/ADR collections when resumed; (5)
  PR-034 portfolio validation, once a real dataset is usable at scale
  (today's real verification covers 2 companies, one date).
