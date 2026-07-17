# Feature Status

**Release:** v1.2.0
**Baseline:** PR-033 + point-in-time acquisition/derivation (including `timing` and extended `valuation`) + deterministic PR-034 target/execution-evidence/total-return-evidence/execution/validation cores
**Test baseline:** 802 passing / 87.79% production coverage

| Capability | Domain | Main pipeline | Excel | Morning Brief | Status |
|---|---:|---:|---:|---:|---|
| Market/fundamental collection | Yes | Yes | Yes | Yes | Operational |
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
| Broad research-universe collection | Yes | No | No | No | Resumable checkpoints; exhausted provider failures remain visible without blocking later batches |
| Analytical market/sector ranking | Yes | Yes | No | No | Diagnostic JSON; no new score or decision |
| Advisory model portfolio | Yes | No | No | No | Market: 2,429/1,042 after official-reference migration; ADR historical run: 501/219 eligible/candidates; each yields 20 capped positions |
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
