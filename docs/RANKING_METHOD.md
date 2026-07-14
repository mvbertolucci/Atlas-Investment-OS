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

## Universe provenance

Every row of the analyzed DataFrame carries an `origin` tag set by
`run_all.merge_watchlist_with_portfolio` (`portfolio`, `watchlist`, or --
once a broad-market screener is wired into the same merge -- `universe`;
hierarchy `portfolio > watchlist > universe` when a symbol belongs to more
than one). `RankedCompany.already_held` mirrors that tag
(`origin == "portfolio"`), so a real holding is never presented as an
ordinary fresh candidate without that flag, even when it also passes every
safeguard above. A frame that never went through that merge (a point-in-time
replay, a standalone research collection) simply has no `origin` column, and
`already_held` defaults to `False`.

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

## Execution scopes

The normal `run_all.py` ranking still covers only the configured personal
watchlist. The explicit `python -m portfolio.model_portfolio` research command
applies the same ranking contract to the completed, dated broad-universe
checkpoint and writes `output/research_ranking_report.json`. Ranks always
describe their stated input snapshot; neither scope claims point-in-time
historical membership.
