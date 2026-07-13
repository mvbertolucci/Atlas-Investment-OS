from datetime import datetime, timezone

import pytest

from backtesting.point_in_time import (
    DelistingRecord,
    HistoricalObservation,
    PointInTimeDataset,
    UniverseMembership,
)


UTC = timezone.utc


def observation(
    *,
    value: float = 10.0,
    observed_on: str = "2025-03-31",
    available_at: str = "2025-05-01T12:00:00Z",
    revision_id: str = "original",
) -> HistoricalObservation:
    return HistoricalObservation(
        symbol="abc",
        field_name="roic",
        value=value,
        observed_on=observed_on,
        available_at=available_at,
        source="filing",
        revision_id=revision_id,
    )


def test_observation_normalizes_identity_and_requires_availability_after_observation() -> None:
    item = observation()

    assert item.symbol == "ABC"
    assert item.observed_on.isoformat() == "2025-03-31"
    assert item.available_at == datetime(2025, 5, 1, 12, tzinfo=UTC)
    assert item.identity[-1] == "original"

    with pytest.raises(ValueError, match="anteceder observed_on"):
        observation(available_at="2025-03-01T12:00:00Z")


def test_point_in_time_timestamps_require_explicit_timezone() -> None:
    with pytest.raises(ValueError, match="fuso horário explícito"):
        observation(available_at="2025-05-01T12:00:00")

    dataset = PointInTimeDataset(observations=(observation(),))
    with pytest.raises(ValueError, match="fuso horário explícito"):
        dataset.as_of("2025-05-02T12:00:00")


def test_as_of_excludes_information_not_yet_available() -> None:
    dataset = PointInTimeDataset(observations=(observation(),))

    before_release = dataset.as_of("2025-05-01T11:59:59Z")
    after_release = dataset.as_of("2025-05-01T12:00:00Z")

    assert before_release.observations == ()
    assert after_release.value("abc", "roic") == 10.0


def test_as_of_uses_latest_revision_available_at_each_decision() -> None:
    original = observation()
    restated = observation(
        value=12.0,
        available_at="2025-06-15T12:00:00Z",
        revision_id="restatement-1",
    )
    dataset = PointInTimeDataset(observations=(restated, original))

    assert dataset.as_of("2025-06-01T00:00:00Z").value("ABC", "roic") == 10.0
    assert dataset.as_of("2025-07-01T00:00:00Z").value("ABC", "roic") == 12.0


def test_as_of_prefers_newer_observation_period_over_older_revision() -> None:
    old_restated = observation(
        value=12.0,
        available_at="2025-08-01T00:00:00Z",
        revision_id="restatement-1",
    )
    new_period = observation(
        value=20.0,
        observed_on="2025-06-30",
        available_at="2025-07-20T00:00:00Z",
        revision_id="original",
    )
    dataset = PointInTimeDataset(observations=(old_restated, new_period))

    assert dataset.as_of("2025-09-01T00:00:00Z").value("ABC", "roic") == 20.0


def test_dataset_rejects_duplicate_observation_versions() -> None:
    item = observation()
    with pytest.raises(ValueError, match="duplicada"):
        PointInTimeDataset(observations=(item, item))


def test_membership_is_half_open_and_respects_when_record_became_known() -> None:
    membership = UniverseMembership(
        symbol="old",
        effective_from="2020-01-01",
        effective_to="2025-06-01",
        known_at="2020-01-01T00:00:00Z",
        source="index-provider",
    )
    future_addition = UniverseMembership(
        symbol="new",
        effective_from="2025-06-01",
        known_at="2025-05-25T00:00:00Z",
        source="index-provider",
    )
    late_history = UniverseMembership(
        symbol="late",
        effective_from="2020-01-01",
        known_at="2025-07-01T00:00:00Z",
        source="archive",
    )
    dataset = PointInTimeDataset(
        memberships=(membership, future_addition, late_history)
    )

    assert dataset.as_of("2025-05-31T23:59:59Z").members == ("OLD",)
    assert dataset.as_of("2025-06-01T00:00:00Z").members == ("NEW",)
    assert dataset.as_of("2025-07-02T00:00:00Z").members == ("LATE", "NEW")


def test_dataset_rejects_overlapping_membership_intervals() -> None:
    first = UniverseMembership(
        "ABC", "2020-01-01", "2020-01-01T00:00:00Z", "index", "2025-01-01"
    )
    overlapping = UniverseMembership(
        "ABC", "2024-12-31", "2024-01-01T00:00:00Z", "index"
    )

    with pytest.raises(ValueError, match="sobrepor"):
        PointInTimeDataset(memberships=(first, overlapping))


@pytest.mark.parametrize(
    ("treatment", "kwargs"),
    [
        ("cash", {"cash_proceeds": 42.5}),
        ("zero", {}),
        ("successor", {"successor_symbol": "xyz"}),
        ("unresolved", {}),
    ],
)
def test_delisting_requires_explicit_return_treatment(treatment, kwargs) -> None:
    record = DelistingRecord(
        symbol="abc",
        effective_on="2025-06-10",
        known_at="2025-06-01T00:00:00Z",
        last_trade_on="2025-06-09",
        return_treatment=treatment,
        source="exchange",
        **kwargs,
    )

    assert record.return_treatment == treatment


def test_delisting_validation_rejects_ambiguous_terminal_values() -> None:
    common = dict(
        symbol="ABC",
        effective_on="2025-06-10",
        known_at="2025-06-01T00:00:00Z",
        last_trade_on="2025-06-09",
        source="exchange",
    )
    with pytest.raises(ValueError, match="cash_proceeds"):
        DelistingRecord(return_treatment="cash", **common)
    with pytest.raises(ValueError, match="successor_symbol"):
        DelistingRecord(return_treatment="successor", **common)
    with pytest.raises(ValueError, match="não suportado"):
        DelistingRecord(return_treatment="drop-row", **common)


def test_snapshot_exposes_delisting_only_after_known_and_effective() -> None:
    record = DelistingRecord(
        symbol="ABC",
        effective_on="2025-06-10",
        known_at="2025-06-01T00:00:00Z",
        last_trade_on="2025-06-09",
        return_treatment="zero",
        source="exchange",
    )
    dataset = PointInTimeDataset(delistings=(record,))

    assert dataset.as_of("2025-06-09T23:59:59Z").delistings == ()
    assert dataset.as_of("2025-06-10T00:00:00Z").delistings == (record,)


def test_snapshot_missing_value_remains_explicit() -> None:
    snapshot = PointInTimeDataset().as_of("2025-06-10T00:00:00Z")

    with pytest.raises(KeyError):
        snapshot.value("ABC", "roic")
