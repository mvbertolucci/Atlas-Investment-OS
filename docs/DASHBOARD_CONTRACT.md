# Dashboard Contract (v2.0 Platform)

The first bounded increment of the v2.0 Platform milestone: a **read-only,
versioned aggregate** of the outputs Atlas already produces, ready for a future
dashboard, REST API or SDK to consume.

It is pure assembly. It computes no scores, applies no rules and changes no
decisions. Every value is a passthrough of an existing domain object's
`to_dict()`.

## Module

- `dashboard/contract.py` — `DashboardView` (frozen dataclass) and
  `DASHBOARD_CONTRACT_VERSION`.
- `dashboard/builder.py` — `build_dashboard_view(...)` (assembly) and
  `write_dashboard_view(view, path)` (JSON serialization).

## Shape

`DashboardView.to_dict()` produces:

```json
{
  "contract_version": "1.7",
  "generated_at": "2026-07-13T00:00:00",
  "market": { ... } | null,
  "companies": [ { CompanyReport.to_dict() }, ... ],
  "portfolio": { ... } | null,
  "outcomes": { ... } | null,
  "decision_queue": { ... } | null,
  "portfolio_scenario": { ... } | null,
  "decision_journal": { ... } | null,
  "execution_ledger": { ... } | null,
  "execution_reconciliation": { ... } | null,
  "custody_history": { ... } | null
}
```

- `market` — `MarketSummary.to_dict()` (run-level aggregate) or `null`.
- `companies` — one entry per analyzed company (`CompanyReport.to_dict()`);
  never `null`, empty list when there is nothing to show.
- `portfolio` — the portfolio report `to_dict()` or `null` when no portfolio
  input is present.
- `outcomes` — the Outcome Analytics report `to_dict()` or `null` when no
  outcomes have matured.
- `decision_queue` — advisory groups `EXECUTE`, `INVESTIGATE`, `WAIT` and
  `MONITOR`, assembled from official portfolio actions and Active Watchlist
  states without recomputing decisions.
- `portfolio_scenario` — advisory simulation of executing only official
  `SELL`/`TRIM` values, with post-trade cash, turnover and weights.
- `decision_journal` — aggregate counts of explicit human reviews; individual
  reasons remain in the separate append-only journal artifact.
- `execution_ledger` — aggregate evidence of explicitly informed real
  `SELL`/`TRIM` fills; individual fills remain in the append-only ledger.
- `execution_reconciliation` — aggregate custody reconciliation statuses from
  explicit baseline/current snapshots; symbol-level evidence remains separate.
- `custody_history` — snapshot count, latest timestamp and whether two
  consecutive snapshots are available for automatic reconciliation.

`build_dashboard_view` accepts domain objects (anything with `to_dict()`) or
already-serialized dicts, so it stays decoupled from the concrete producer
types.

## Versioning

`contract_version` is `1.7`. Bump it **only** on a deliberate change to
the serialized shape, so consumers can reconcile. A contract change is an
explicit decision, never incidental — same governance discipline as scoring
configuration.

## Pipeline exposure

`run_all.generate_dashboard(df, settings, portfolio_report, outcome_report)`
assembles the view from the objects the run already produced and writes
`output/dados/dashboard.json` after the Excel and Morning Brief steps. It is:

- **guarded** by the `dashboard_enabled` runtime setting (default `true`);
- **additive** — a new artifact that changes no existing output;
- **read-only** — it forwards `to_dict()` output and computes nothing.

`companies` comes from `reports.report_engine.build_company_reports(df)`;
`portfolio` and `outcomes` are the run's reports when present. `market` is the
read-only `UniverseReport` when Market Universe is enabled, containing policy,
coverage, eligibility and exclusion reasons; when disabled it remains `null`.

## Scope boundary

Still separate, later increments: REST API, scheduling, notifications, SDK and
AI assistant. Because the contract is read-only and additive, adopting it
changes no existing behavior.
