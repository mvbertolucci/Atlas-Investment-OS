# Decision Register

Detailed architecture decisions live in `docs/adr/`. This file is the index and operational summary.

| ID | Decision | Status |
|---|---|---|
| ADR-001 | Separate Investment and Opportunity concepts | Accepted |
| ADR-002 | Calculate conviction after opportunity | Accepted |
| ADR-003 | Keep Decision as a separate layer | Accepted |
| ADR-004 | Use presentation domain models | Accepted |
| ADR-005 | Portfolio consumes `CompanyReport` | Accepted |
| ADR-006 | Rebalance is advisory only | Accepted |
| ADR-007 | Cash is a portfolio asset | Accepted |
| ADR-008 | `config/features.yaml` is the authoritative feature registry | Accepted via PR-017.3; formal ADR recommended |
| ADR-009 | Portfolio input is optional and must not break company analysis | Accepted via PR-018.1; formal ADR recommended |
| ADR-010 | `AGENTS.md` is the canonical coding-agent entry instruction | Accepted in Codex transition foundation |
| ADR-011 | Portfolio rebalance is the single sell voice | Accepted 2026-07-15 |
| ADR-012 | Eligible U.S. broad market is the official live-scoring reference | Accepted 2026-07-17 |
| ADR-013 | Separate coverage, provenance, freshness, confidence and risk uncertainty | Accepted 2026-07-17 |
| ADR-014 | Use typed provider boundaries, field evidence and immutable raw snapshots | Accepted 2026-07-17 |
| ADR-015 | Compose execution as typed pipeline stages over a shared context | Accepted 2026-07-17 |
| ADR-016 | Inject narrow typed service facades instead of a module namespace | Accepted 2026-07-17 |
| ADR-017 | Move collection and scoring implementations into application services | Accepted 2026-07-17 |
| ADR-018 | Give history and Outcome Analytics a concrete application service | Accepted 2026-07-17 |
| ADR-019 | Give portfolio, watchlist and Atlas Report a concrete intelligence service | Accepted 2026-07-17 |
| ADR-020 | Give final report publication a concrete application service | Accepted 2026-07-17 |
| ADR-021 | Separate governed ticker analysis from runtime operations | Accepted 2026-07-17 |

## Recording a new decision

Create `docs/adr/ADR-NNN-short-title.md` with:

- context;
- decision;
- alternatives considered;
- consequences;
- migration/rollback notes;
- date and status.
