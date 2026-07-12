# Feature Status

**Baseline:** PR-018.2  
**Test baseline:** 187 passing

| Capability | Domain | Main pipeline | Excel | Morning Brief | Status |
|---|---:|---:|---:|---:|---|
| Market/fundamental collection | Yes | Yes | Yes | Yes | Operational |
| Technical enrichment | Yes | Yes | Yes | Yes | Operational; coverage hardening pending |
| Investment scoring | Yes | Yes | Yes | Yes | Operational |
| Opportunity and conviction | Yes | Yes | Yes | Yes | Operational |
| Deal Breakers and penalties | Yes | Yes | Yes | Yes | Operational |
| Decision Engine and thesis | Yes | Yes | Yes | Yes | Operational |
| Historical snapshots and alerts | Yes | Yes | Partial | Yes | Operational |
| Portfolio import and validation | Yes | Yes | Yes | No | Operational |
| Allocation and concentration | Yes | Yes | Yes | No | Morning Brief pending |
| Portfolio quality and ranking | Yes | Yes | Yes | No | Morning Brief pending |
| Advisory rebalance | Yes | Yes | Yes | No | Morning Brief pending |
| Health check and execution metrics | Yes | Yes | N/A | N/A | Operational; direct tests pending |
| Outcome Analytics | No | No | No | No | Planned v1.2 |
| Backtesting | No | No | No | No | Future milestone |
| Dashboard/API | Scaffold/roadmap | No | No | No | Future platform |

## Conditional outputs

With `config/portfolio.csv`, Atlas creates:

- `output/portfolio_report.json`;
- `Portfolio Summary` worksheet;
- `Portfolio Allocation` worksheet;
- `Portfolio Concentration` worksheet;
- `Portfolio Quality` worksheet;
- `Portfolio Rebalance` worksheet;
- `Portfolio Warnings` worksheet.
