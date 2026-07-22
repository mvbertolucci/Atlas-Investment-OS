# Market Opportunity Funnel

`output/dados/market_opportunity_funnel.json` is the versioned, read-only
contract that makes the Atlas acquisition funnel observable before automatic
watchlist mutation.

It combines the latest available S&P 500, broad U.S. market and ADR ranking
reports in deterministic precedence order. It does not compute a new score or
decision: candidate qualification delegates to the same governed
`watchlist.auto_curation.select_auto_inclusion_candidates` function used by
automatic curation.

The contract publishes source availability and dates, source counts, unique
safeguard-passing symbols, qualified symbols after portfolio/watchlist
exclusions, and the final `top_n` selection with provenance and trigger.

Publication happens in `IntelligenceStage` immediately before automatic
curation so the artifact describes the candidates eligible for that run before
selected names are written to `config/watchlist.csv`. Serialization uses the
shared atomic-write retry.

The estimated Decision remains a first-pass acquisition signal with
`risk_penalty=0.0`. Selection is not an authoritative buy recommendation; the
normal collection and scoring pipeline must subsequently produce the governed
Decision with complete evidence.
