# Feature Status

**Release:** v1.2.0
**Baseline:** PR-027
**Test baseline:** 320 passing / 87.96% production coverage

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
| Market-universe eligibility | Yes | No | No | No | Contract operational; pipeline integration is PR-028 |
| Backtesting | No | No | No | No | Future milestone |
| Dashboard/API/SDK | Yes | Yes | N/A | N/A | Read-only platform contracts operational |

## Conditional outputs

With `config/portfolio.csv`, Atlas creates:

- `output/portfolio_report.json`;
- `Portfolio Summary` worksheet;
- `Portfolio Allocation` worksheet;
- `Portfolio Concentration` worksheet;
- `Portfolio Quality` worksheet;
- `Portfolio Rebalance` worksheet;
- `Portfolio Warnings` worksheet.

The Morning Brief also includes an executive portfolio section with largest
positions, quality, concentration, conviction/risk highlights, warnings and
advisory rebalance actions.
