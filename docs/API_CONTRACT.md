# Dashboard API (read-only)

A read-only HTTP layer over the dashboard contract (`docs/DASHBOARD_CONTRACT.md`).
It serves the already-produced `output/dashboard.json` and its sub-resources; it
never triggers a run, changes a decision or writes anything.

## Design

- `api/resources.py` — framework-agnostic, pure routing:
  - `route(path, data)` maps a path to `(status, payload)` over a loaded
    contract (no I/O, fully testable);
  - `dispatch(method, path)` validates the method, loads the contract and
    routes;
  - `load_dashboard(path)` reads the artifact (`ResourceError(503)` if absent).
- `api/server.py` — a thin `http.server` (stdlib) adapter. **No new
  dependency.** If a production stack is wanted later (FastAPI, OpenAPI, auth),
  only this adapter is replaced; the resource layer stays.

## Run

```powershell
.\.venv\Scripts\python.exe -m api.server        # http://127.0.0.1:8000
```

Requires a prior `run_all.py` (which emits `output/dashboard.json`). Before the
first run, every resource returns `503`.

## Resources (GET only)

| Route | Returns |
|---|---|
| `/` | service info + `contract_version` + resource index |
| `/dashboard` | the full contract |
| `/companies` | `{ count, companies[] }` |
| `/companies/{symbol}` | one company (case-insensitive), `404` if unknown |
| `/market` | `{ market }` |
| `/portfolio` | `{ portfolio }` |
| `/outcomes` | `{ outcomes }` |

Responses are `application/json; charset=utf-8`. Any non-GET method returns
`405`; unknown paths return `404`; a missing artifact returns `503`.

## Read-only guarantee

The system is decision support: the API only reads. There are no write, create
or mutate endpoints, and the server exposes only `GET` semantics. Scheduling,
notifications, authentication and an SDK are separate, later increments.
