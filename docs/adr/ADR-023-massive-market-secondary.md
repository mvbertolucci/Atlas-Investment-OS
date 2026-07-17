# ADR-023 — Massive market and ownership secondary

**Status:** Accepted
**Date:** 2026-07-17

## Context

SEC Company Facts independently confirms reported fundamentals but cannot
confirm market capitalization, enterprise value or short interest as a share
of float. Those Yahoo fields therefore remained `secondary_unavailable`.
Financial Modeling Prep covers market cap, enterprise value and free float,
but free float is not Atlas's governed `short_float` risk metric. Massive also
publishes dated FINRA short interest, allowing the correct ratio to be derived.

## Decision

1. Add a credential-gated `MassiveMarketDataProvider` for `market_cap`,
   `enterprise_value` and `short_float`.
2. Derive `short_float` only as dated `short_interest / free_float`; reject the
   derivation when source periods differ by more than 45 days.
3. Keep the adapter disabled in committed settings. Load its key only from the
   `MASSIVE_API_KEY` environment variable or ignored provider-secrets file.
4. Generalize Yahoo collection to run multiple independent secondary clients.
   Each provider declares supported fields, has isolated typed failure and an
   immutable raw snapshot, and cannot suppress another provider's result.
5. Preserve legacy singular secondary snapshot/error fields while adding
   provider-keyed maps for complete multiprovider evidence.
6. Do not mark live integration complete until a user-configured key and plan
   pass a bounded real-symbol verification.

## Consequences

- SEC remains authoritative for comparable filing fundamentals; Massive owns
  only its declared market and ownership fields.
- Missing credentials cause a warning only when explicitly enabled and never
  expose or invent a value.
- Market/ownership confirmation becomes possible without changing scores,
  thresholds or Deal Breakers.
- The experimental Massive Float endpoint is an explicit maintenance risk.
- A broad-universe run may require a paid plan and materially more API calls;
  activation remains a user decision.

## Migration and rollback

No persisted-data migration is required. Existing single-secondary callers and
legacy snapshot/error keys remain compatible. Rollback disables the committed
flag and removes the Massive builder; SEC and Yahoo behavior remain intact.
