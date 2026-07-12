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

## Recording a new decision

Create `docs/adr/ADR-NNN-short-title.md` with:

- context;
- decision;
- alternatives considered;
- consequences;
- migration/rollback notes;
- date and status.
