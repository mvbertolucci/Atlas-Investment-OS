"""
Tests for the SEC EDGAR XBRL -> HistoricalObservation converter.

Only the pure parsing/conversion functions are tested with small, synthetic,
offline fixtures shaped like the real SEC companyfacts/company_tickers JSON --
mirroring the project's existing convention for external fetch wrappers
(e.g. universe.sources.fetch_sp500_constituents is likewise not
network-tested, only its parser is). No live network call is made in this
test file.
"""
from __future__ import annotations

import pytest

from backtesting.point_in_time import PointInTimeDataset
from backtesting.sec_edgar import (
    available_at_from_filed,
    extract_observations,
    parse_ticker_cik_map,
)


def _company_facts(entries: list[dict], tag: str = "Assets") -> dict:
    return {
        "cik": 320193,
        "entityName": "Test Co",
        "facts": {
            "us-gaap": {
                tag: {
                    "label": tag,
                    "units": {"USD": entries},
                }
            }
        },
    }


def _entry(
    end="2025-12-31",
    val=1000.0,
    filed="2026-02-01",
    accn="0000320193-26-000010",
    form="10-K",
):
    return {"end": end, "val": val, "filed": filed, "accn": accn, "form": form}


# ---------------------------------------------------------------------------
# available_at_from_filed
# ---------------------------------------------------------------------------


def test_available_at_is_midnight_utc_the_day_after_filing() -> None:
    assert available_at_from_filed("2026-02-01") == "2026-02-02T00:00:00+00:00"


# ---------------------------------------------------------------------------
# parse_ticker_cik_map
# ---------------------------------------------------------------------------


def test_parse_ticker_cik_map_pads_and_upcases() -> None:
    payload = {
        "0": {"cik_str": 320193, "ticker": "aapl", "title": "Apple Inc."},
        "1": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet"},
    }
    mapping = parse_ticker_cik_map(payload)
    assert mapping["AAPL"] == "0000320193"
    assert mapping["GOOGL"] == "0001652044"


def test_parse_ticker_cik_map_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="ticker"):
        parse_ticker_cik_map({"0": {"cik_str": 1}})


# ---------------------------------------------------------------------------
# extract_observations
# ---------------------------------------------------------------------------


def test_extract_observations_maps_native_tag_to_canonical_field() -> None:
    facts = _company_facts([_entry()])
    observations = extract_observations("AAPL", facts)

    assert len(observations) == 1
    obs = observations[0]
    assert obs.symbol == "AAPL"
    assert obs.field_name == "total_assets"
    assert obs.value == 1000.0
    assert obs.observed_on.isoformat() == "2025-12-31"
    assert obs.available_at.isoformat() == "2026-02-02T00:00:00+00:00"
    assert obs.revision_id == "0000320193-26-000010"
    assert "10-K" in obs.source


def test_extract_observations_ignores_tags_outside_the_mapping() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "SomeUnmappedConcept": {"units": {"USD": [_entry()]}},
            }
        }
    }
    assert extract_observations("AAPL", facts) == ()


def test_extract_observations_ignores_non_10k_10q_forms() -> None:
    facts = _company_facts([_entry(form="8-K")])
    assert extract_observations("AAPL", facts) == ()


def test_extract_observations_deduplicates_identical_identity() -> None:
    """The same (end, accn) can legitimately appear twice in raw XBRL units
    (e.g. once with a duration context, once with an instant context)."""
    facts = _company_facts([_entry(), _entry()])
    observations = extract_observations("AAPL", facts)
    assert len(observations) == 1


def test_extract_observations_captures_each_revision_separately() -> None:
    """A restated figure (10-K/A) gets its own accn/filed -- both revisions
    are kept, exactly matching PointInTimeDataset's own revision handling."""
    facts = _company_facts(
        [
            _entry(val=1000.0, filed="2026-02-01", accn="0000320193-26-000010"),
            _entry(
                val=1050.0,
                filed="2026-03-15",
                accn="0000320193-26-000099",
                form="10-K/A",
            ),
        ]
    )
    observations = extract_observations("AAPL", facts)
    assert len(observations) == 2

    # Feed straight into the real PointInTimeDataset contract end to end.
    dataset = PointInTimeDataset(observations=observations)
    before_restatement = dataset.as_of("2026-02-15T00:00:00Z")
    after_restatement = dataset.as_of("2026-03-20T00:00:00Z")

    assert before_restatement.value("AAPL", "total_assets") == 1000.0
    assert after_restatement.value("AAPL", "total_assets") == 1050.0


def test_extract_observations_uppercases_symbol() -> None:
    facts = _company_facts([_entry()])
    observations = extract_observations("aapl", facts)
    assert observations[0].symbol == "AAPL"


def test_extract_observations_handles_missing_facts_gracefully() -> None:
    assert extract_observations("AAPL", {}) == ()
    assert extract_observations("AAPL", {"facts": {}}) == ()


def test_extract_observations_merges_multiple_candidate_tags() -> None:
    """
    A company can use "Revenues" in early years and switch to
    "RevenueFromContractWithCustomerExcludingAssessedTax" later (the ~2018
    revenue-recognition standard change). Both must be extracted and merged
    under the same canonical field -- not just whichever tag is checked
    first -- or part of the company's real history would silently vanish.
    """
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _entry(
                                end="2016-12-31",
                                val=100.0,
                                filed="2017-02-01",
                                accn="0000320193-17-000001",
                            )
                        ]
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            _entry(
                                end="2019-12-31",
                                val=200.0,
                                filed="2020-02-01",
                                accn="0000320193-20-000001",
                            )
                        ]
                    }
                },
            }
        }
    }

    observations = extract_observations("AAPL", facts)
    revenue_obs = [o for o in observations if o.field_name == "total_revenue"]

    assert len(revenue_obs) == 2
    values_by_period = {o.observed_on.isoformat(): o.value for o in revenue_obs}
    assert values_by_period == {"2016-12-31": 100.0, "2019-12-31": 200.0}


def test_extract_observations_reads_shares_outstanding_from_dei_taxonomy() -> None:
    facts = {
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [_entry(val=15_000_000_000.0)]}
                }
            }
        }
    }

    observations = extract_observations("AAPL", facts)

    assert len(observations) == 1
    assert observations[0].field_name == "shares_outstanding"
    assert observations[0].value == 15_000_000_000.0
    assert "dei:" in observations[0].source


def test_extract_observations_covers_the_widened_native_tag_set() -> None:
    """Sanity check that the widened FIELD_TAG_CANDIDATES table round-trips
    for a representative sample of the newly added native tags."""
    facts = {
        "facts": {
            "us-gaap": {
                "GrossProfit": {"units": {"USD": [_entry(val=10.0)]}},
                "LongTermDebtNoncurrent": {"units": {"USD": [_entry(val=20.0)]}},
                "OperatingIncomeLoss": {"units": {"USD": [_entry(val=30.0)]}},
                "InterestExpense": {"units": {"USD": [_entry(val=40.0)]}},
            }
        }
    }

    observations = extract_observations("AAPL", facts)
    values = {o.field_name: o.value for o in observations}

    assert values == {
        "gross_profit": 10.0,
        "long_term_debt": 20.0,
        "operating_income": 30.0,
        "interest_expense": 40.0,
    }
