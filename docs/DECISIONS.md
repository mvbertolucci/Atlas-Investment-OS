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
| ADR-022 | Give operational runtime behavior a concrete service | Accepted 2026-07-17 |
| ADR-023 | Use Massive as the optional market and ownership secondary | Accepted 2026-07-17 |
| ADR-024 | Compose free FMP and Massive evidence instead of buying ratios | Accepted 2026-07-17 |
| ADR-025 | Bound free FMP broad collection with persistent cache and quota | Accepted 2026-07-17 |
| ADR-026 | Use Massive Basic market cap and SEC-composed enterprise value | Accepted 2026-07-17 |
| ADR-027 | Cache and resume Massive broad details within the Basic rate limit | Accepted 2026-07-17 |
| ADR-028 | Cache the paginated market-wide Massive Float snapshot | Accepted 2026-07-17 |
| ADR-029 | Keep SEC monetary public float separate from free-float shares | Accepted 2026-07-17 |
| ADR-030 | Finnhub as the primary live market-cap/enterprise-value secondary source | Accepted 2026-07-18 |
| ADR-031 | Compose broad market cap from Grouped Daily price x SEC shares | Accepted 2026-07-18 |
| ADR-032 | Shared retry-on-lock for every atomic JSON write | Accepted 2026-07-18 |
| ADR-033 | Massive Grouped Daily as the broad market-cap price source | Accepted 2026-07-18 |

## Recording a new decision

Create `docs/adr/ADR-NNN-short-title.md` with:

- context;
- decision;
- alternatives considered;
- consequences;
- migration/rollback notes;
- date and status.
