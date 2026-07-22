# Active Watchlist

The Watchlist is an active acquisition queue, not only a symbol list. Legacy
CSV files remain valid; missing lifecycle fields load with conservative
defaults and do not trigger promotion or removal merely because of migration.

Persisted entry metadata:

- `lifecycle_state`: stable base state (`monitoring` for legacy/manual,
  `analyzing` for automatic inclusion);
- `analytical_origin`: `sp500`, `broad_market`, `adr` or `manual`;
- `entry_rank` and `entry_score`: immutable acquisition context;
- `review_due_at`: first formal review deadline, governed for automatic
  entries by `watchlist_auto.yaml::selection.review_sla_days`;
- `promotion_condition`: objective trigger inherited from screening;
- `discard_condition`: objective exit threshold recorded at entry.

Every Watchlist report publishes `active_queue`. Its `effective_state` is
derived read-only from current evidence:

- `promotion_ready`: the promotion condition triggered in this run;
- `waiting_trigger`: a valid condition exists but remains clear;
- `review_required`: invalid/unassessable condition or review deadline reached;
- `discard_review`: aging cleanup condition reached;
- otherwise the persisted `analyzing`/`monitoring` base state.

`promotion_ready` is not an executed purchase and `discard_review` is not an
automatic rejection. Both are explicit human decision queues. Existing
automatic removal remains restricted to auto-origin entries below the governed
Investment Score exit threshold, with portfolio and manual-entry safeguards.
