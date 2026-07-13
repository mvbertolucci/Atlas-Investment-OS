# Deterministic Portfolio Validation

## Purpose and current boundary

The first bounded PR-034 increment adds a pure, offline validation core in
`backtesting/portfolio_validation.py`. It measures an explicit sequence of
dated target portfolios against explicit total-return observations. It does
not construct a historical portfolio, fetch data, change Atlas scores or claim
that the current model has achieved any real historical performance.

Point-in-time model-portfolio targets can now be built for explicit cutoffs;
see `docs/HISTORICAL_MODEL_PORTFOLIO.md`. Converting those targets into return
periods still requires an explicit execution calendar and complete real total
returns. Factor contribution also remains open until historical factor
exposures and subsequent returns can be joined without look-ahead bias.

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
  produces `null` sector metrics instead of an invented classification.
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
- sector HHI and maximum sector weight when every position has an explicit
  sector;
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

- govern the execution-date/price convention and convert historical targets
  into dated validation rebalances;
- acquire complete total-return and benchmark series with dividends and
  delisting treatment;
- add sector and factor contribution based on exposures known at each cutoff;
- run the report on a broad real dataset and publish coverage before drawing
  any performance conclusion.
