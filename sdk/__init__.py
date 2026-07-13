"""
Read-only Python SDK for the Atlas dashboard contract (v2.0 Platform).

`AtlasClient` mirrors the read-only API resources. It talks either to a running
API (`AtlasClient.for_url(...)`) or to the emitted artifact directly, offline
(`AtlasClient.for_file(...)`). It only reads -- there are no write operations.
No third-party dependency; stdlib only.
"""
from __future__ import annotations

from sdk.client import (
    AtlasApiError,
    AtlasClient,
    NotFoundError,
    ServiceUnavailableError,
    http_transport,
    local_transport,
)

__all__ = [
    "AtlasClient",
    "AtlasApiError",
    "NotFoundError",
    "ServiceUnavailableError",
    "http_transport",
    "local_transport",
]
