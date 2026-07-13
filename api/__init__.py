"""
Read-only HTTP API over the dashboard contract (v2.0 Platform increment).

Serves `output/dashboard.json` and its sub-resources over HTTP GET. It reads
already-produced output and never triggers a run, changes a decision or writes
anything. The resource layer (`api.resources`) is framework-agnostic; the
stdlib server (`api.server`) is a thin adapter and adds no dependency.
"""
from __future__ import annotations

from api.resources import ResourceError, dispatch, load_dashboard, route

__all__ = ["ResourceError", "dispatch", "load_dashboard", "route"]
