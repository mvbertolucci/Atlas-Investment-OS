# Analytical Ranking Method

## Purpose

The analytical ranking orders the companies already analyzed by Atlas for
research and future model-portfolio construction. It does not calculate a new
score, change a decision or recommend a trade.

## Ordering

`config/ranking.yaml` defines the existing columns used by the ranking:

1. Investment Score (primary);
2. Opportunity Score (first tie-breaker);
3. Conviction Score (second tie-breaker);
4. symbol (deterministic final tie-breaker).

Market rank is calculated among companies eligible under the current
`UniverseReport`. Sector rank uses the same order inside each sector. These are
ordinal positions, not new weighted scores.

## Candidate safeguards

A company receives a `candidate_rank` only when all safeguards pass:

- eligible under `config/universe.yaml`;
- primary Investment Score available;
- Confidence Score at or above the configured minimum (70 by default);
- no active Deal Breaker when `require_no_deal_breakers` is enabled.

Deal Breakers reuse the governed absolute thresholds in
`config/deal_breakers.json`. The ranking does not reproduce or override those
financial rules.

Every block is explicit through one or more codes:

- `UNIVERSE_INELIGIBLE`;
- `MISSING_PRIMARY_SCORE`;
- `MISSING_CONFIDENCE_SCORE`;
- `CONFIDENCE_BELOW_MINIMUM`;
- `DEAL_BREAKER_TRIGGERED`.

## Output

When enabled, `run_all.py` writes `output/ranking_report.json`, containing the
policy, summary, market/sector positions, candidate positions and safeguard
reasons. This output is diagnostic and advisory. PR-030 will consume it under
separate, explicit portfolio-construction constraints.

## Current limitation

The current ranking covers only the configured watchlist. It does not yet
discover or download all members of the U.S. market. Market and sector ranks
therefore describe the analyzed batch, not the entire investable market. A
broader reproducible constituent source is required before claiming full-market
coverage.
