"""A cola do walk-forward monta o dataset a partir de artefatos reais.

Fixtures espelham os formatos de verdade: o checkpoint da coleta SEC
(`observations_by_symbol`) e o CSV de constituintes com coluna `symbol`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtesting.point_in_time import PointInTimeDataset
from backtesting.walk_forward_pipeline import (
    build_manifest,
    load_memberships,
    load_observations,
)


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    path = tmp_path / "sec_edgar_collection.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "observations_by_symbol": {
                    "AAA": [
                        {
                            "symbol": "AAA",
                            "field_name": "total_assets",
                            "value": 1000.0,
                            "observed_on": "2025-12-31",
                            "available_at": "2026-02-10T00:00:00+00:00",
                            "source": "SEC EDGAR (10-K, us-gaap:Assets)",
                            "revision_id": "0000000001-26-000001",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_observations_round_trip_through_the_checkpoint(state_file: Path) -> None:
    observations = load_observations(state_file)

    assert len(observations) == 1
    assert observations[0].symbol == "AAA"
    # o corte anti-look-ahead sobrevive à serialização: o balanço de dezembro
    # só é visível depois do arquivamento de fevereiro
    assert observations[0].is_available("2026-02-10T00:00:00+00:00")
    assert not observations[0].is_available("2026-01-02T00:00:00+00:00")


def test_memberships_come_from_the_constituents_csv(tmp_path: Path) -> None:
    csv_file = tmp_path / "sp500_constituents_2026-01-01.csv"
    csv_file.write_text(
        "symbol,name,cik\nAAA,Alpha,0000000001\nBBB,Beta,0000000002\n",
        encoding="utf-8",
    )

    memberships = load_memberships(csv_file, effective_from="2026-01-01")

    assert [m.symbol for m in memberships] == ["AAA", "BBB"]
    assert all(m.is_active("2026-01-02T00:00:00+00:00") for m in memberships)
    # antes da data do snapshot nada é membro: o recorte honesto da fonte
    assert not memberships[0].is_active("2025-12-31T00:00:00+00:00")


def test_dataset_assembles_and_cuts(state_file: Path, tmp_path: Path) -> None:
    csv_file = tmp_path / "sp500_constituents_2026-01-01.csv"
    csv_file.write_text("symbol,name,cik\nAAA,Alpha,0000000001\n", encoding="utf-8")

    dataset = PointInTimeDataset.from_iterables(
        observations=load_observations(state_file),
        memberships=load_memberships(csv_file, effective_from="2026-01-01"),
    )

    january = dataset.as_of("2026-01-02T00:00:00+00:00")
    march = dataset.as_of("2026-03-02T00:00:00+00:00")

    # em janeiro a empresa é membro mas o 10-K ainda não foi arquivado:
    # o snapshot nem CONTÉM o fato -- pedir por ele é KeyError, não None
    assert list(january.members) == ["AAA"]
    with pytest.raises(KeyError):
        january.value("AAA", "total_assets")
    assert march.value("AAA", "total_assets") == 1000.0


def test_manifest_counts_unresolved_delistings_honestly(tmp_path: Path) -> None:
    universe_manifest = tmp_path / "universe_manifest.json"
    universe_manifest.write_text(
        json.dumps(
            {"wikipedia_revision_id": 123, "csv_sha256": "abc123def4567890"}
        ),
        encoding="utf-8",
    )

    manifest = build_manifest(
        universe_manifest_path=universe_manifest,
        constituents_csv=tmp_path / "sp500_constituents_2026-01-01.csv",
        tracked_fields=("total_assets", "total_assets", "revenues"),
        unresolved_delistings=("BK", "CTRA"),
        calendar_description="monthly, day 2",
    )

    assert manifest.unresolved_delisting_count == 2
    assert "BK" in manifest.delisting_coverage_description
    # campos deduplicados e ordenados: proveniência determinística
    assert manifest.tracked_fields == ("revenues", "total_assets")
    assert manifest.governed_config_hashes
