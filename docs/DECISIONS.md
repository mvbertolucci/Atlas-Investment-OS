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
| ADR-034 | A malformed SEC XBRL entry no longer aborts a company's whole extraction | Accepted 2026-07-18 |
| ADR-035 | Wikipedia "Selected changes" table as a real source for historical S&P 500 membership (proof of concept) | Proposed 2026-07-18 |
| ADR-036 | Watchlist auto-curation: run_all.py also writes config/watchlist.csv, additive to the existing manual gate | Accepted 2026-07-21 |
| ADR-037 | PE/ROE absence from a loss-making or negative-equity company is structural (not_applicable), not a fetch gap; EV/EBITDA weight raised as the natural substitute | Accepted 2026-07-21 |
| ADR-038 | General FX/vendor-reconciliation protocol for market_cap/enterprise_value/short_float/total_cash on ADRs and foreign issuers | Accepted 2026-07-22 |
| ADR-039 | ACOMPANHAR status separates a relative_decay-only signal from an actionable REVISAR | Accepted 2026-07-22 |
| ADR-040 | Stable decision identity (symbol\|action\|engine, no timestamp) plus per-run decision-queue snapshots | Accepted 2026-07-22 |
| ADR-041 | Local `POST /journal` write endpoint (hardened, loopback-only) plus derived decision status in the cockpit | Accepted 2026-07-22 |
| ADR-042 | Remove `total_debt` from cross-vendor critical agreement (flaky SEC debt sum was nulling correct Yahoo values on ~48% of holdings) | Accepted 2026-07-22 |
| ADR-043 | SEC `total_debt` extraction anchors on the long-term-debt period (root-cause fix for the period-misaligned sum; COP \$1.07B → \$23.7B) | Accepted 2026-07-23 |
| ADR-044 | Scoring reference includes any issuer domicile (US-listed ADRs join the cross-section; 2,429 → 2,930), so foreign holdings aren't scored against a US-only universe | Accepted 2026-07-23 |
| ADR-047 | Freshness anchors on the issuer's own reporting cadence, and TTM flow metrics are dated by the latest quarter instead of the annual statement (MSFT flow fields were a full year mis-dated; 324 stale fields → 0 across the book) | Accepted 2026-07-24 |

## Recording a new decision

Create `docs/adr/ADR-NNN-short-title.md` with:

- context;
- decision;
- alternatives considered;
- consequences;
- migration/rollback notes;
- date and status.
