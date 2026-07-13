"""Contracts for reproducible historical validation."""

from backtesting.point_in_time import (
    AsOfSnapshot,
    DelistingRecord,
    HistoricalObservation,
    PointInTimeDataset,
    UniverseMembership,
)
from backtesting.sec_edgar import (
    extract_observations,
    fetch_company_facts,
    fetch_ticker_cik_map,
)
from backtesting.walk_forward import (
    HistoricalInputManifest,
    IncompleteDecision,
    ReplayedDecision,
    WalkForwardReport,
    compute_governed_config_hashes,
    monthly_decision_calendar,
    reconstruct_snapshot_frame,
    run_walk_forward,
    write_walk_forward_report,
)

__all__ = [
    "AsOfSnapshot",
    "DelistingRecord",
    "HistoricalObservation",
    "PointInTimeDataset",
    "UniverseMembership",
    "HistoricalInputManifest",
    "IncompleteDecision",
    "ReplayedDecision",
    "WalkForwardReport",
    "compute_governed_config_hashes",
    "monthly_decision_calendar",
    "reconstruct_snapshot_frame",
    "run_walk_forward",
    "write_walk_forward_report",
    "extract_observations",
    "fetch_company_facts",
    "fetch_ticker_cik_map",
]
