# Atlas SDK (read-only)

A small Python client for the dashboard contract. It mirrors the read-only API
resources and only reads — there are no write operations. Stdlib only, no
third-party dependency.

## Two transports

- **`AtlasClient.for_url(base_url)`** — talks to a running API over HTTP
  (`api.server`). Use when the API is up.
- **`AtlasClient.for_file(path=None)`** — resolves resources in-process from the
  emitted `output/dashboard.json` (or a given path). Works offline, no server.

Both expose the same methods, so code is written once and the transport is a
deployment choice.

## Usage

```python
from sdk import AtlasClient

# Offline, straight from the artifact:
atlas = AtlasClient.for_file()               # reads output/dashboard.json
print(atlas.dashboard()["contract_version"])
for company in atlas.companies():
    print(company["symbol"], company["decision"])
adbe = atlas.company("ADBE")                 # case-insensitive
print(atlas.portfolio(), atlas.outcomes(), atlas.market())

# Against a running API:
atlas = AtlasClient.for_url("http://127.0.0.1:8000")
```

## Methods

| Method | Returns |
|---|---|
| `index()` | service info + `contract_version` |
| `dashboard()` | the full contract |
| `companies()` | `list` of company dicts |
| `company(symbol)` | one company; raises `NotFoundError` if unknown |
| `market()` / `portfolio()` / `outcomes()` | that view (may be `None`) |

## Errors

- `NotFoundError` (404) — unknown resource, e.g. a symbol not analyzed.
- `ServiceUnavailableError` (503) — the artifact was not generated yet
  (run `run_all.py`), or the API is down.
- `AtlasApiError` — any other non-200 status (base class of the two above);
  `status == 0` signals an HTTP connection failure.

## Boundary

Read-only by design. Scheduling, notifications and the AI assistant are separate
increments.
