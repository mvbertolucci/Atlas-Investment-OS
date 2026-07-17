# ADR-014 — Provider evidence and immutable raw snapshots

**Status:** Accepted  
**Date:** 2026-07-17

## Context

Atlas previously treated provider failures as arbitrary exception text and
represented every unusable value as `None`. A current value, an invalid value,
a field omitted by the provider and a metric structurally irrelevant to a
sector therefore became indistinguishable. The resumable universe collector
had retries, but the watchlist path had no equivalent timeout, pacing or typed
failure contract. Derived checkpoints also could not prove which exact provider
payload produced a score.

## Decision

1. All new live provider boundaries use `ProviderClient` and `ProviderPolicy`,
   with a positive timeout, exponential retry budget, per-client rate limit and
   `ProviderError` classified as timeout, rate limited, unavailable, not found,
   authentication, invalid response or unknown.
2. Provider rows remain flat for downstream compatibility, but carry a
   `field_evidence` map. Each field records source, category, retrieval time,
   observation time, availability time, confirmation state and one of:
   `present`, `missing`, `unavailable`, `invalid`, `stale` or
   `not_applicable`.
3. `not_applicable` is governed by `config/data_quality.yaml`. It is removed
   from the coverage denominator and does not fail a required-feature gate.
   Other unusable states do not count as available evidence.
4. Every successful live Yahoo adapter response is serialized canonically and
   written before enrichment to a content-addressed path under
   `data/raw_snapshots/<provider>/<date>/<symbol>/<sha256>.json`. Creation is
   exclusive; an existing object is verified and never overwritten. The hash,
   path and field evidence are retained in collection checkpoints and SQLite
   score history.
5. Critical fields use `reconcile_critical_fields`. A usable secondary value
   replaces an unusable primary value (`fallback`); close values are
   `confirmed`; disagreement beyond tolerance invalidates the value instead of
   silently choosing one source. When no secondary adapter is configured, the
   evidence explicitly says `secondary_unavailable`.

## Secondary provider activation

The reconciliation contract is active in both watchlist and broad-universe
collection. SEC Company Facts is the configured independent adapter for
reported fundamentals. Its identifying `User-Agent` lives only in the ignored
`config/provider_secrets.json`; the repository ships a safe example file.

SEC confirms or provides fallback for cash, reported debt and current ratio
when a common fiscal period can be constructed. It can provide annual fallback
for free cash flow and EBITDA, but does not confirm Yahoo's TTM definitions;
those comparisons are marked `definition_mismatch`. Values from different
periods are marked `period_mismatch` and are not compared.
Company Facts still does not report market cap, enterprise value or short
float. ADR-023 adds an optional credential-gated Massive adapter for those
fields; until it is explicitly activated and live-verified, they remain
`secondary_unavailable` in real runs.

## Consequences

- Provider failures are bounded and machine-readable.
- A historical score can be traced to exact immutable input bytes.
- Structural sector exemptions no longer masquerade as missing data.
- Raw snapshots consume local disk and remain gitignored runtime evidence.
- Timed-out thread-backed calls cannot be forcibly terminated by Python; the
  caller returns at the deadline and cancels work that has not started, while a
  network library call already in progress may finish in the background.
