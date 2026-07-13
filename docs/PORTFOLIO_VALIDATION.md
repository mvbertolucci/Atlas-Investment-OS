# Deterministic Portfolio Validation

## Purpose and current boundary

The first bounded PR-034 increment adds a pure, offline validation core in
`backtesting/portfolio_validation.py`. It measures an explicit sequence of
dated target portfolios against explicit total-return observations. It does
not construct a historical portfolio, fetch data, change Atlas scores or claim
that the current model has achieved any real historical performance.

Point-in-time model-portfolio targets can now be built for explicit cutoffs;
the next-session-open execution convention is also executable when attributed
sessions and opening prices are supplied. See
`docs/HISTORICAL_MODEL_PORTFOLIO.md` and `docs/HISTORICAL_EXECUTION.md`.

`backtesting/total_return_evidence.py` adds a pure, offline adapter that
converts already-acquired Yahoo-shaped daily bars (`Close`, `Dividends`) into
the `AssetPeriodReturn` rows this validation runner already consumes --
dividend-inclusive, computed by compounding `(Close[t] + Dividend[t]) /
Close[t-1]` day over day across an explicit, caller-supplied sequence of
period boundaries. It works identically for a portfolio holding or a
benchmark symbol (e.g. SPY); there is no separate benchmark code path. A
period whose start date has no observed close is omitted, never invented --
the runner already reports `MISSING_RETURN`/`MISSING_BENCHMARK_RETURN` for
anything absent. A `DelistingRecord` (PR-032 vocabulary) overrides the one
period containing its `last_trade_on`: `zero` forces exactly -100%; `cash`
combines the compounding multiplier up to the last traded close with
`cash_proceeds` in place of a next Close that will never arrive; `successor`
and `unresolved` are both reported `unresolved` (`total_return=None`) --
this single-symbol adapter has no evidence of a successor security's own
value, so it never fabricates one. `TotalReturnEvidence` wraps a batch of
these rows in the same versioned, retrieval-timestamped artifact pattern as
`backtesting/execution_evidence.py`, so total returns can be computed once
and reused across validation runs. Real calendar/opening-price acquisition
and a broad real total-return/benchmark/delisting dataset remain open.

Each complete period now also reports per-sector return contribution
(`sector_contributions`): `target_weight × asset_return`, summed per sector,
using the exact same explicit `PortfolioRebalance.sectors` mapping already
required for `sector_hhi` -- no new input needed. It is `null` under the
same condition as `sector_hhi`/`maximum_sector_weight` (absent or partial
sector coverage), and its values always sum to exactly `gross_return`, a
useful invariant for spotting a broken sector mapping.

`PortfolioRebalance` also carries an optional `factor_exposures` map
(symbol -> `{business, valuation, financial, timing}`, the same 0-100
cross-sectional scores `factors/engine.py` already produces).
`backtesting/historical_portfolio.py` populates it directly from the
governed scoring pass at each cutoff -- not recomputed, not a new input,
just no longer discarded. Each complete validation period reports the
portfolio's **target-weighted average exposure per factor**
(`ValidationPeriod.factor_exposures`), `null` unless every held symbol has
a value for the exact same set of factors. This is a **composition/tilt
summary, not a return decomposition**: it does not attribute *return* to
each factor the way `sector_contributions` attributes return to sectors.
A regression-based factor-return decomposition (the finance-standard sense
of "factor contribution") is deliberately not implemented here -- it needs
a statistical methodology to validate and document, not just a data join,
and remains a separate, larger increment if ever pursued.

## Run from a versioned local input

The runner performs no provider call. It reads one explicit JSON input and the
governed policy, then writes one report:

```powershell
.\.venv\Scripts\python.exe -m backtesting.portfolio_validation `
  --input path\to\validation_input.json `
  --output output\portfolio_validation_report.json
```

`--policy` may override `config/portfolio_validation.yaml`. The input schema is
pinned as version 1; `config/portfolio_validation_input.example.json` is a
loadable, fully synthetic shape example only. Its symbols and returns are not
research evidence and must never be reported as Atlas performance.

Every input requires a manifest naming the dataset/version, portfolio source,
return source, benchmark source, period convention, terminal-event source and
tested Atlas revision. Each return row still retains its own source so mixed
or transformed inputs remain visible in the output.

## Governed assumptions

`config/portfolio_validation.yaml` pins the initial research assumptions:

- monthly observations (`periods_per_year: 12`);
- SPY total return as the S&P 500 proxy;
- USD as the base currency;
- dividends included in both portfolio and benchmark returns;
- 10 basis points of one-way transaction cost per unit of turnover.

The 10 bps cost is an explicit, configurable research estimate, not a claim
about achievable execution. It does not include taxes or a security-specific
market-impact model. Changing it changes the experiment and must remain
visible in the policy and report.

## Input contract

- `PortfolioRebalance` provides one effective date and positive target weights.
  Cash is implicit as `1 - sum(target_weights)`. An optional explicit sector
  mapping enables sector concentration; absent or partial sector coverage
  produces `null` sector metrics instead of an invented classification. An
  optional per-symbol factor-exposure mapping (same factor set across every
  symbol that has one) enables the weighted-average factor exposure summary;
  absent or partial coverage produces `null` there too.
- `AssetPeriodReturn` provides one attributed total return for a half-open
  evaluation period, including source, currency, dividend treatment and any
  terminal-event treatment.
- Every period begins on a rebalance date, periods are consecutive and every
  held symbol plus the benchmark requires exactly one return.
- Delistings follow the PR-032 vocabulary. `zero` requires exactly -100%;
  `cash` and `successor` require an explicit resolved total return; `unresolved`
  cannot carry an invented return.

Missing returns, currency/dividend mismatches and unresolved delistings are
machine-readable incomplete reasons. If any period is incomplete, aggregate
performance metrics are withheld (`summary: null`) rather than calculated from
a survivorship-biased subset. A missing period also prevents later turnover
reconstruction because the pre-trade weights are no longer known.

## Calculations

For each complete period, Atlas reports:

- gross and transaction-cost-adjusted portfolio total return;
- benchmark and arithmetic period excess return;
- one-way turnover, including the initial move from cash;
- estimated transaction cost;
- position Herfindahl-Hirschman concentration and maximum position weight;
- sector HHI, maximum sector weight and per-sector return contribution when
  every position has an explicit sector;
- target-weighted average factor exposure (composition, not return
  attribution) when every position has one, for the same factor set;
- resolved terminal events used in the calculation.

The complete-run summary compounds portfolio and benchmark returns and reports
relative return, annualized return, sample annualized volatility, maximum
drawdown, average turnover, total estimated cost and concentration summaries.
Costs are removed proportionally at rebalance before the period return, which
preserves the economic -100% return floor.

Every JSON report is advisory-only, includes the input schema version,
manifest, performance disclaimer and row-level return sources, and states
whether validation is `complete` or `incomplete`.

## Remaining PR-034 work

- acquire/version real exchange sessions and opening-price observations for
  the governed execution convention;
- run `backtesting/total_return_evidence.py` against a broad real Yahoo
  dataset (selected symbols plus the benchmark) and acquire real
  `DelistingRecord` evidence for terminal events -- the adapter and its
  versioned artifact are implemented, but no broad real total-return
  artifact is committed or collected by this change;
- sector contribution and weighted-average factor exposure are now
  implemented (see above); a regression-based factor-*return* decomposition
  remains open and would be a separate, larger increment;
- run the report on a broad real dataset and publish coverage before drawing
  any performance conclusion.
