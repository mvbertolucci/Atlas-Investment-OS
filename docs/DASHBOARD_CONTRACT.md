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
  "contract_version": "1.0",
  "generated_at": "2026-07-13T00:00:00",
  "market": { ... } | null,
  "companies": [ { CompanyReport.to_dict() }, ... ],
  "portfolio": { ... } | null,
  "outcomes": { ... } | null
}
```

- `market` — `MarketSummary.to_dict()` (run-level aggregate) or `null`.
- `companies` — one entry per analyzed company (`CompanyReport.to_dict()`);
  never `null`, empty list when there is nothing to show.
- `portfolio` — the portfolio report `to_dict()` or `null` when no portfolio
  input is present.
- `outcomes` — the Outcome Analytics report `to_dict()` or `null` when no
  outcomes have matured.

`build_dashboard_view` accepts domain objects (anything with `to_dict()`) or
already-serialized dicts, so it stays decoupled from the concrete producer
types.

## Versioning

`contract_version` starts at `1.0`. Bump it **only** on a deliberate change to
the serialized shape, so consumers can reconcile. A contract change is an
explicit decision, never incidental — same governance discipline as scoring
configuration.

## Scope boundary

This increment defines and tests the contract only. Separate, later increments:

- **Expose** it through the pipeline (emit `output/dashboard.json` from
  `run_all.py`).
- REST API, scheduling, notifications, SDK and AI assistant.

Because it is isolated and read-only, adopting it changes no existing behavior.
