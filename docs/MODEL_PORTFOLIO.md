# Advisory Model Portfolio

## Purpose

PR-031 converts the complete broad-universe checkpoint into an auditable
research portfolio. It is a model output for validation, not a trade order,
personal recommendation or performance promise.

The command is explicit and remains separate from `run_all.py`:

```powershell
.\.venv\Scripts\python.exe -m portfolio.model_portfolio
```

It writes four ignored runtime artifacts:

- `output/research_universe_report.json` — eligibility of all observations;
- `output/dados/research_ranking_report.json` — broad market and sector ranking;
- `output/relatorios/research_candidates.csv` — the full candidate group (every company
  that passed the ranking safeguards), one row each, ordered by
  `candidate_rank` (the model's suggested purchase order), enriched with name,
  sector, industry, the four scores, market/sector rank, price and market cap.
  This goes beyond the 20 selected positions: it is the complete ranked
  shortlist to buy from.
- `output/dados/model_portfolio_report.json` — constrained advisory selection.

## Running over a different screener

By default this runs the S&P 500 screener (`config/universe.yaml`,
`config/research_universe.csv`), with the historical output filenames above.
To run over the broad-market or ADR screener instead once their collection
completes, override the universe policy and give the run a `--label` so it
does not overwrite the S&P 500 output:

```powershell
.\.venv\Scripts\python.exe -m portfolio.model_portfolio `
  --state data/research_universe_collection_market.json `
  --snapshot config/research_universe_market.csv `
  --universe-policy config/universe_market.yaml `
  --label market `
  --allow-exhausted-failures
```

`--allow-exhausted-failures` is required for the broad-market and ADR
screeners: those universes contain warrants, units, rights, preferreds and
suspended tickers with no price history, so a small tail of collection
failures is terminal, not transient. See *Failure behavior* below. The S&P 500
screener needs no such flag — its universe collects with zero residual
failures.

This writes `research_universe_report_market.json`,
`research_ranking_report_market.json` and `model_portfolio_report_market.json`
instead. For the ADR screener, point `--state`/`--snapshot` at the
broad-market collection (ADRs reuse it, see `docs/UNIVERSE_SOURCES.md`) and
use `--universe-policy config/universe_adr.yaml --label adr`.
`--ranking-policy` and `--model-portfolio-policy` are also overridable, but
default to the same canonical files for every screener (the ranking method
and portfolio-construction rules are shared; only the eligible population
differs).

## Latest audited operational runs

Using the completed 7,093-symbol broad-market snapshot/checkpoint:

- market policy: 6,959 observations, 2,429 eligible companies, 794
  safeguarded candidates and 20 selected positions;
- ADR policy: the same 6,959 observations, filtered to 501 eligible companies,
  219 safeguarded candidates and 20 selected positions;
- both runs retain 134 exhausted provider failures in output provenance;
- both portfolios invest 100% at 5% per position and respect the 20% sector
  cap. These current-snapshot outputs are advisory research, not historical
  performance evidence.

## Method

The command loads the completed collection checkpoint, applies the existing
Atlas normalization and governed scoring pipeline, evaluates the existing
universe policy and applies the existing ranking safeguards. It introduces no
new alpha score and does not modify factor weights, Deal Breakers or candidate
thresholds.

Selection follows `candidate_rank` and greedily accepts the best remaining
company whose addition does not breach the sector cap. The first policy is
deliberately simple:

| Constraint | Value |
|---|---:|
| Positions | 20 |
| Weighting | Equal |
| Maximum position | 5% |
| Maximum sector | 20% |
| Structural cash | 0% |
| Maximum initial turnover | 100% |

These values live in `config/model_portfolio.yaml` and are pinned by governance
tests. They are assumptions to validate, not calibrated optimal values.

## Failure behavior

Construction stops explicitly when:

- collection is incomplete or retains provider failures (strict default);
- the policy constraints are internally incompatible;
- too few safeguarded candidates remain to satisfy position and sector limits;
- output types do not match the documented contracts.

### Exhausted vs transient failures

By default the builder demands a collection with every constituent observed
and zero residual failures. With `--allow-exhausted-failures` it distinguishes
two kinds of residual failure:

- **Transient** — a symbol whose retry budget is *not* exhausted
  (`attempts < retries + 1`). This may be a recoverable provider hiccup that
  could still hide a real large cap, so construction still stops.
- **Exhausted / permanent** — a symbol whose retry budget *is* exhausted
  (`attempts >= retries + 1`). These are terminal: instruments with no price
  series (warrants, units, rights, preferreds, suspended tickers) that would
  be dropped by the universe policy's `allowed_quote_types`/thresholds anyway
  if they had ever produced an observation. Construction proceeds and records
  each excluded symbol and its provider error under
  `source.excluded_failures` (with `source.excluded_failure_count` and a
  summary warning) so the exclusion is auditable.

Construction still stops if any snapshot symbol was never attempted, so the
flag relaxes only the terminal-failure tail, never an incomplete run.

The output records source dates, eligible/candidate counts, ranks, existing
scores, target weights, sector weights, reference prices and any higher-ranked
candidate skipped by diversification constraints.

## Validation boundary

The portfolio uses a current constituent snapshot and current provider data.
It therefore cannot establish historical performance and must not be treated
as backtest evidence. PR-032 defines point-in-time data rules before PR-033
implements walk-forward testing. A later prospective shadow portfolio will
freeze recommendations before observing outcomes.
