"""
Read-only dashboard contract for the v2.0 Platform milestone.

This package defines a bounded, versioned, serializable aggregate of existing
Atlas outputs (company, portfolio and outcome views). It is pure assembly: it
computes no scores and changes no decisions. Exposing it through the pipeline
(emitting output/dashboard.json) and any API/SDK are separate increments.
"""
from __future__ import annotations

from dashboard.contract import DASHBOARD_CONTRACT_VERSION, DashboardView
from dashboard.builder import build_dashboard_view, write_dashboard_view

__all__ = [
    "DASHBOARD_CONTRACT_VERSION",
    "DashboardView",
    "build_dashboard_view",
    "write_dashboard_view",
]
