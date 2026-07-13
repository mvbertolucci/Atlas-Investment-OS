"""
Tests for the deterministic walk-forward replay engine (PR-033).

This engine consumes PointInTimeDataset.as_of(decision_at) and recreates
Atlas decisions using only evidence visible at each cutoff, through the
existing, unchanged, governed score_dataframe. It computes no return, risk
or performance metric -- that is a separate, later validation step.

There is no real historical point-in-time dataset collected yet (PR-032's
own stated scope excludes historical-data acquisition); these tests exercise
the engine with small, fully synthetic, offline fixtures. They prove the
mechanism -- correct temporal exclusion, incomplete-decision reporting,
determinism -- not any real predictive signal.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtesting.point_in_time import (
    DelistingRecord,
    HistoricalObservation,
    PointInTimeDataset,
    StockSplitRecord,
    UniverseMembership,
)
from backtesting.point_in_time_valuation import derive_point_in_time_valuation
from backtesting.walk_forward import (
    HistoricalInputManifest,
    WalkForwardReport,
    compute_governed_config_hashes,
    monthly_decision_calendar,
    reconstruct_snapshot_frame,
    replay_decision_batch,
    run_walk_forward,
    write_walk_forward_report,
)

CONFIG = Path("config")
MODEL_PATH = CONFIG / "model.yaml"
DEAL_BREAKERS_PATH = CONFIG / "deal_breakers.json"


def _observation(symbol, field_name, value, observed_on, available_at, revision="original"):
    return HistoricalObservation(
        symbol=symbol,
        field_name=field_name,
        value=value,
        observed_on=observed_on,
        available_at=available_at,
        source="test-fixture",
        revision_id=revision,
    )


def _membership(symbol, effective_from="2020-01-01", known_at="2020-01-01T00:00:00Z"):
    return UniverseMembership(
        symbol=symbol,
        effective_from=effective_from,
        known_at=known_at,
        source="index",
    )


def _manifest(**overrides) -> HistoricalInputManifest:
    fields = {
        "source_name": "test-fixture",
        "source_version": "v0",
        "benchmark_source": "none",
        "constituent_history_source": "synthetic",
        "decision_calendar_description": "single test date",
        "timezone": "UTC",
        "tracked_fields": ("price", "roic"),
        "revision_policy": "latest available at cutoff",
        "delisting_coverage_description": "none",
        "unresolved_delisting_count": 0,
        "atlas_code_revision": "test",
        "governed_config_hashes": {"model.yaml": "deadbeef"},
    }
    fields.update(overrides)
    return HistoricalInputManifest(**fields)


# ---------------------------------------------------------------------------
# HistoricalInputManifest
# ---------------------------------------------------------------------------


def test_manifest_requires_every_field_non_empty() -> None:
    with pytest.raises(ValueError, match="source_name"):
        _manifest(source_name="")


def test_manifest_rejects_empty_tracked_fields() -> None:
    with pytest.raises(ValueError, match="tracked_fields"):
        _manifest(tracked_fields=())


def test_manifest_rejects_negative_unresolved_count() -> None:
    with pytest.raises(ValueError, match="unresolved_delisting_count"):
        _manifest(unresolved_delisting_count=-1)


def test_manifest_requires_governed_config_hashes() -> None:
    with pytest.raises(ValueError, match="governed_config_hashes"):
        _manifest(governed_config_hashes={})


def test_manifest_to_dict_roundtrips() -> None:
    manifest = _manifest()
    data = manifest.to_dict()
    assert data["source_name"] == "test-fixture"
    assert data["tracked_fields"] == ["price", "roic"]


def test_compute_governed_config_hashes_is_deterministic_and_real() -> None:
    hashes = compute_governed_config_hashes(
        {"model.yaml": MODEL_PATH, "deal_breakers.json": DEAL_BREAKERS_PATH}
    )
    again = compute_governed_config_hashes(
        {"model.yaml": MODEL_PATH, "deal_breakers.json": DEAL_BREAKERS_PATH}
    )
    assert hashes == again
    assert len(hashes["model.yaml"]) == 64  # sha256 hex digest
    assert hashes["model.yaml"] != hashes["deal_breakers.json"]


# ---------------------------------------------------------------------------
# reconstruct_snapshot_frame
# ---------------------------------------------------------------------------


def test_reconstruct_frame_has_one_row_per_member_and_no_invented_values() -> None:
    dataset = PointInTimeDataset(
        observations=(
            _observation("AAA", "price", 100.0, "2025-12-31", "2026-01-01T00:00:00Z"),
        ),
        memberships=(_membership("AAA"), _membership("BBB")),
    )
    snapshot = dataset.as_of("2026-01-15T00:00:00Z")
    frame = reconstruct_snapshot_frame(snapshot)

    assert list(frame["symbol"]) == ["AAA", "BBB"]
    assert frame.loc[frame["symbol"] == "AAA", "price"].iloc[0] == 100.0
    assert frame.loc[frame["symbol"] == "BBB", "price"].isna().iloc[0]


def test_reconstruct_frame_with_no_observations_at_all() -> None:
    dataset = PointInTimeDataset(memberships=(_membership("AAA"),))
    snapshot = dataset.as_of("2026-01-15T00:00:00Z")
    frame = reconstruct_snapshot_frame(snapshot)

    assert list(frame["symbol"]) == ["AAA"]
    assert list(frame.columns) == ["symbol"]


def test_reconstruct_frame_carries_observation_dates_and_split_factor() -> None:
    dataset = PointInTimeDataset(
        observations=(
            _observation(
                "AAA", "shares_outstanding", 100.0,
                "2020-06-30", "2020-07-31T00:00:00Z",
            ),
            _observation(
                "AAA", "price", 50.0,
                "2020-09-01", "2020-09-02T00:00:00Z",
            ),
        ),
        memberships=(_membership("AAA"),),
        splits=(
            StockSplitRecord(
                "AAA", "2020-08-31", 4,
                "2020-09-01T00:00:00Z", "exchange",
            ),
            StockSplitRecord(
                "AAA", "2021-01-01", 2,
                "2021-01-02T00:00:00Z", "exchange",
            ),
        ),
    )

    frame = reconstruct_snapshot_frame(
        dataset.as_of("2020-09-02T00:00:00Z")
    )
    row = frame.iloc[0]

    assert row["shares_outstanding__observed_on"].isoformat() == "2020-06-30"
    assert row["price__observed_on"].isoformat() == "2020-09-01"
    assert row["shares_outstanding_split_factor"] == 4.0


def test_market_cap_remains_continuous_across_split_without_lookahead() -> None:
    dataset = PointInTimeDataset(
        observations=(
            _observation(
                "AAA", "shares_outstanding", 100.0,
                "2020-06-30", "2020-07-31T00:00:00Z",
            ),
            _observation(
                "AAA", "price", 500.0,
                "2020-08-28", "2020-08-29T00:00:00Z", "pre-split",
            ),
            _observation(
                "AAA", "price", 125.0,
                "2020-09-01", "2020-09-02T00:00:00Z", "post-split",
            ),
        ),
        memberships=(_membership("AAA"),),
        splits=(
            StockSplitRecord(
                "AAA", "2020-08-31", 4,
                "2020-09-01T00:00:00Z", "exchange",
            ),
        ),
    )

    before = derive_point_in_time_valuation(
        reconstruct_snapshot_frame(dataset.as_of("2020-08-29T00:00:00Z"))
    ).iloc[0]
    after = derive_point_in_time_valuation(
        reconstruct_snapshot_frame(dataset.as_of("2020-09-02T00:00:00Z"))
    ).iloc[0]

    assert before["shares_outstanding_split_factor"] == 1.0
    assert after["shares_outstanding_split_factor"] == 4.0
    assert before["market_cap"] == pytest.approx(50_000.0)
    assert after["market_cap"] == pytest.approx(50_000.0)


# ---------------------------------------------------------------------------
# replay_decision_batch
# ---------------------------------------------------------------------------


def _rich_observations(symbol: str) -> tuple[HistoricalObservation, ...]:
    fields = {
        "price": 100.0,
        "roic": 15.0,
        "roe": 18.0,
        "pe": 20.0,
        "sector": "Technology",
        "country": "United States",
        "currency": "USD",
        "quote_type": "EQUITY",
        "market_cap": 5_000_000_000.0,
        "volume": 1_000_000.0,
    }
    return tuple(
        _observation(symbol, name, value, "2025-12-31", "2026-01-01T00:00:00Z")
        for name, value in fields.items()
    )


def test_replay_produces_a_decision_for_a_well_covered_symbol() -> None:
    dataset = PointInTimeDataset(
        observations=_rich_observations("AAA"),
        memberships=(_membership("AAA"),),
    )
    snapshot = dataset.as_of("2026-01-15T00:00:00Z")

    replayed, incomplete = replay_decision_batch(
        snapshot, model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH
    )

    assert incomplete == ()
    assert len(replayed) == 1
    assert replayed[0].symbol == "AAA"
    assert replayed[0].investment_score is not None
    assert replayed[0].decision_at == snapshot.decision_at


def test_replay_marks_symbol_with_no_data_as_incomplete() -> None:
    dataset = PointInTimeDataset(memberships=(_membership("ZZZ"),))
    snapshot = dataset.as_of("2026-01-15T00:00:00Z")

    replayed, incomplete = replay_decision_batch(
        snapshot, model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH
    )

    assert replayed == ()
    assert len(incomplete) == 1
    assert incomplete[0].symbol == "ZZZ"
    assert incomplete[0].reasons == ("NO_DATA_AVAILABLE",)


def test_replay_marks_unresolved_delisting_as_incomplete_even_with_data() -> None:
    dataset = PointInTimeDataset(
        observations=_rich_observations("AAA"),
        memberships=(_membership("AAA"),),
        delistings=(
            DelistingRecord(
                symbol="AAA",
                effective_on="2026-01-10",
                known_at="2026-01-05T00:00:00Z",
                last_trade_on="2026-01-09",
                return_treatment="unresolved",
                source="exchange",
            ),
        ),
    )
    snapshot = dataset.as_of("2026-01-15T00:00:00Z")

    replayed, incomplete = replay_decision_batch(
        snapshot, model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH
    )

    assert replayed == ()
    assert incomplete[0].reasons == ("UNRESOLVED_DELISTING",)


def test_replay_does_not_flag_resolved_delisting_as_incomplete() -> None:
    """A 'zero' treatment is an explicit, resolved terminal event -- not a gap."""
    dataset = PointInTimeDataset(
        observations=_rich_observations("AAA"),
        memberships=(_membership("AAA"),),
        delistings=(
            DelistingRecord(
                symbol="AAA",
                effective_on="2026-01-10",
                known_at="2026-01-05T00:00:00Z",
                last_trade_on="2026-01-09",
                return_treatment="zero",
                source="exchange",
            ),
        ),
    )
    snapshot = dataset.as_of("2026-01-15T00:00:00Z")

    replayed, incomplete = replay_decision_batch(
        snapshot, model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH
    )

    assert incomplete == ()
    assert len(replayed) == 1


def test_replay_feeds_derived_two_year_f_score_to_governed_deal_breaker() -> None:
    prior = {
        "net_income": 100.0,
        "total_assets": 1000.0,
        "operating_cash_flow": 120.0,
        "current_assets": 400.0,
        "current_liabilities": 200.0,
        "shares_outstanding": 100.0,
        "gross_profit": 400.0,
        "total_revenue": 1000.0,
        "long_term_debt": 100.0,
    }
    current = {
        "net_income": -50.0,
        "total_assets": 1200.0,
        "operating_cash_flow": -20.0,
        "current_assets": 200.0,
        "current_liabilities": 300.0,
        "shares_outstanding": 200.0,
        "gross_profit": 200.0,
        "total_revenue": 900.0,
        "long_term_debt": 500.0,
    }
    observations: list[HistoricalObservation] = []
    for period_end, available_at, accession, values in (
        ("2024-12-31", "2025-02-02T00:00:00Z", "annual-2024", prior),
        ("2025-12-31", "2026-02-02T00:00:00Z", "annual-2025", current),
    ):
        observations.extend(
            HistoricalObservation(
                symbol="AAA",
                field_name=field_name,
                value=value,
                observed_on=period_end,
                available_at=available_at,
                source="SEC EDGAR (10-K, us-gaap:Test)",
                revision_id=accession,
            )
            for field_name, value in values.items()
        )
    observations.extend(_rich_observations("AAA"))
    dataset = PointInTimeDataset(
        observations=tuple(observations),
        memberships=(_membership("AAA"),),
    )

    replayed, incomplete = replay_decision_batch(
        dataset.as_of("2026-03-01T00:00:00Z"),
        model_path=MODEL_PATH,
        deal_breakers_path=DEAL_BREAKERS_PATH,
    )

    assert incomplete == ()
    assert "Piotroski baixo" in replayed[0].deal_breakers


# ---------------------------------------------------------------------------
# run_walk_forward
# ---------------------------------------------------------------------------


def test_run_walk_forward_validates_types() -> None:
    with pytest.raises(TypeError, match="PointInTimeDataset"):
        run_walk_forward(
            object(), ["2026-01-15T00:00:00Z"], _manifest(),
            model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH,
        )
    with pytest.raises(TypeError, match="HistoricalInputManifest"):
        run_walk_forward(
            PointInTimeDataset(), ["2026-01-15T00:00:00Z"], object(),
            model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH,
        )


def test_run_walk_forward_rejects_empty_calendar() -> None:
    with pytest.raises(ValueError, match="decision_dates"):
        run_walk_forward(
            PointInTimeDataset(), [], _manifest(),
            model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH,
        )


def test_run_walk_forward_is_deterministic() -> None:
    dataset = PointInTimeDataset(
        observations=_rich_observations("AAA"),
        memberships=(_membership("AAA"),),
    )
    dates = ["2026-01-15T00:00:00Z", "2026-02-15T00:00:00Z"]

    first = run_walk_forward(
        dataset, dates, _manifest(),
        model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH,
    )
    second = run_walk_forward(
        dataset, dates, _manifest(),
        model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH,
    )

    assert [d.to_dict() for d in first.replayed_decisions] == [
        d.to_dict() for d in second.replayed_decisions
    ]


def test_run_walk_forward_does_not_leak_future_availability() -> None:
    """
    The core anti-look-ahead property: a value available only after a
    decision date must not appear in that decision's replay, even though
    the SAME dataset is used for a later date where it IS visible.

    Uses two symbols: Atlas scores are cross-sectional percentile ranks
    within the batch (see docs/SCORING_MODEL.md), so a single-symbol batch
    always collapses to a neutral score regardless of the value -- that
    would mask a real leak instead of proving its absence.
    """
    dataset = PointInTimeDataset(
        observations=(
            *_rich_observations("AAA"),
            *_rich_observations("BBB"),
            _observation(
                "AAA", "roic", 999.0, "2026-01-31", "2026-02-10T00:00:00Z",
                revision="restated",
            ),
        ),
        memberships=(_membership("AAA"), _membership("BBB")),
    )

    report = run_walk_forward(
        dataset,
        ["2026-01-15T00:00:00Z", "2026-03-01T00:00:00Z"],
        _manifest(),
        model_path=MODEL_PATH,
        deal_breakers_path=DEAL_BREAKERS_PATH,
    )

    january_aaa = [
        d for d in report.replayed_decisions
        if d.decision_at.month == 1 and d.symbol == "AAA"
    ][0]
    march_aaa = [
        d for d in report.replayed_decisions
        if d.decision_at.month == 3 and d.symbol == "AAA"
    ][0]

    # Both dates produce a decision (data exists at both cutoffs), but the
    # January score must reflect the ORIGINAL roic (15.0, tied with BBB),
    # not the restated 999.0 value which only becomes visible in February.
    assert january_aaa.investment_score != march_aaa.investment_score


def test_run_walk_forward_deduplicates_and_sorts_dates() -> None:
    dataset = PointInTimeDataset(
        observations=_rich_observations("AAA"),
        memberships=(_membership("AAA"),),
    )
    report = run_walk_forward(
        dataset,
        [
            "2026-02-15T00:00:00Z",
            "2026-01-15T00:00:00Z",
            "2026-01-15T00:00:00Z",
        ],
        _manifest(),
        model_path=MODEL_PATH,
        deal_breakers_path=DEAL_BREAKERS_PATH,
    )
    assert [d.month for d in report.decision_dates] == [1, 2]


def test_report_to_dict_includes_disclaimer_and_summary() -> None:
    dataset = PointInTimeDataset(
        observations=_rich_observations("AAA"),
        memberships=(_membership("AAA"),),
    )
    report = run_walk_forward(
        dataset, ["2026-01-15T00:00:00Z"], _manifest(),
        model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH,
    )
    data = report.to_dict()

    assert data["advisory_only"] is True
    assert "no return, risk or performance claim" in data["performance_disclaimer"]
    assert data["summary"]["total_decision_dates"] == 1
    assert data["summary"]["total_replayed"] == 1
    assert data["summary"]["total_incomplete"] == 0


# ---------------------------------------------------------------------------
# monthly_decision_calendar
# ---------------------------------------------------------------------------


def test_monthly_calendar_spans_years_and_uses_utc() -> None:
    calendar = monthly_decision_calendar("2025-11-15", "2026-02-10", day_of_month=1)
    assert [d.isoformat() for d in calendar] == [
        "2025-12-01T00:00:00+00:00",
        "2026-01-01T00:00:00+00:00",
        "2026-02-01T00:00:00+00:00",
    ]


def test_monthly_calendar_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="end"):
        monthly_decision_calendar("2026-02-01", "2026-01-01")
    with pytest.raises(ValueError, match="day_of_month"):
        monthly_decision_calendar("2026-01-01", "2026-02-01", day_of_month=29)


# ---------------------------------------------------------------------------
# write_walk_forward_report
# ---------------------------------------------------------------------------


def test_write_walk_forward_report_creates_json(tmp_path: Path) -> None:
    dataset = PointInTimeDataset(
        observations=_rich_observations("AAA"),
        memberships=(_membership("AAA"),),
    )
    report = run_walk_forward(
        dataset, ["2026-01-15T00:00:00Z"], _manifest(),
        model_path=MODEL_PATH, deal_breakers_path=DEAL_BREAKERS_PATH,
    )
    output = write_walk_forward_report(report, tmp_path / "walk_forward.json")
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["summary"]["total_replayed"] == 1


def test_write_walk_forward_report_validates_type(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        write_walk_forward_report(object(), tmp_path / "out.json")
