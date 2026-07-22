# Custody History

`output/dados/portfolio_custody_history.json` is an append-only, quantity-only
history captured whenever the dashboard is generated with a portfolio report.
Each snapshot stores its deterministic ID, portfolio generation timestamp,
portfolio name and sorted `symbol`/`quantity` pairs.

Identical snapshots from an idempotent rerun are not duplicated. Snapshots are
kept chronologically ordered. Prices, scores and recommendations are excluded:
the artifact exists solely to provide an auditable quantity baseline for
execution reconciliation.

Once two snapshots exist, Atlas automatically:

1. selects the two latest consecutive snapshots;
2. considers only ledger fills after the baseline and at or before the current
   snapshot;
3. writes `execution_reconciliation.json`;
4. publishes aggregate status counts in the Dashboard and Decision Cockpit.

The history does not import brokerage data by itself. Its reliability depends
on each portfolio input being a complete custody snapshot. It never modifies
the input portfolio or resolves a divergence automatically.
