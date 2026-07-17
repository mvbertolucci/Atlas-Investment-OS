# Feature Status

**Release:** v1.2.0
**Baseline:** PR-033 + point-in-time acquisition/derivation (including `timing` and extended `valuation`) + deterministic PR-034 target/execution-evidence/total-return-evidence/execution/validation cores
**Test baseline:** 828 passing / 87.90% production coverage

| Capability | Domain | Main pipeline | Excel | Morning Brief | Status |
|---|---:|---:|---:|---:|---|
| Market/fundamental collection | Yes | Yes | Yes | Yes | Operational |
| Provider resilience and raw evidence | Yes | Yes | No | No | Timeout/retry/rate-limit contract, typed errors, field timestamps and immutable SHA-256 snapshots operational; independent secondary adapter not configured by default |
| Technical enrichment | Yes | Yes | Yes | Yes | Operational; 100% direct coverage |
| Investment scoring | Yes | Yes | Yes | Yes | Operational |
| Opportunity and conviction | Yes | Yes | Yes | Yes | Operational |
| Deal Breakers and penalties | Yes | Yes | Yes | Yes | Operational |
| Decision Engine and thesis | Yes | Yes | Yes | Yes | Operational |
| Historical snapshots and alerts | Yes | Yes | Partial | Yes | Operational |
| Portfolio import and validation | Yes | Yes | Yes | Yes | Operational |
| Allocation and concentration | Yes | Yes | Yes | Yes | Operational |
| Portfolio quality and ranking | Yes | Yes | Yes | Yes | Operational |
| Advisory rebalance | Yes | Yes | Yes | Yes | Operational |
| Health check and execution metrics | Yes | Yes | N/A | N/A | Operational; 100% direct coverage |
| Outcome Analytics | Yes | Yes | Yes | Yes | Operational; JSON, Excel and Morning Brief reports |
| Market-universe eligibility | Yes | Yes | No | No | Diagnostic JSON and Dashboard market view operational |
| Broad research-universe collection | Yes | No | No | No | Resumable checkpoints; typed exhausted failures and raw snapshot hashes remain visible without blocking later batches |
| Analytical market/sector ranking | Yes | Yes | No | No | Diagnostic JSON; no new score or decision |
| Advisory model portfolio | Yes | No | No | No | Market: 2,429/794 after evidence-quality gates; ADR historical run: 501/219 eligible/candidates; each yields 20 capped positions |
| Point-in-time data contract | Yes | No | No | No | Executable observations, constituents, splits and delistings |
| Walk-forward replay | Yes | No | No | No | Ratios, two-year F-Score and partial valuation; coverage incomplete |
| Portfolio return/risk validation | Partial | No | No | No | Targets, execution evidence/next-open and metrics ready; broad real data still open |
| Dashboard/API/SDK | Yes | Yes | N/A | N/A | Read-only platform contracts operational |

## Conditional outputs

With `config/portfolio.csv`, Atlas creates:

- `output/dados/portfolio_report.json`;
- `Portfolio Summary` worksheet;
- `Portfolio Allocation` worksheet;
- `Portfolio Concentration` worksheet;
- `Portfolio Quality` worksheet;
- `Portfolio Rebalance` worksheet;
- `Portfolio Warnings` worksheet.

The Morning Brief also includes an executive portfolio section with largest
positions, quality, concentration, conviction/risk highlights, warnings and
advisory rebalance actions.
