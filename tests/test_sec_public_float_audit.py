from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import providers.sec_public_float_audit as audit_module
from providers.contracts import ProviderPolicy
from providers.fmp_cache import FmpCacheStore
from providers.massive_cache import MassiveFloatSnapshotCache
from providers.sec_public_float_audit import (
    assess_record,
    residual_members,
    run_audit,
)


def test_residual_members_excludes_massive_and_fmp_coverage(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    massive = MassiveFloatSnapshotCache(
        tmp_path / "massive.json", clock=lambda: now
    )
    massive.append_page([{"ticker": "AAA", "free_float": 10}], None)
    fmp = FmpCacheStore(tmp_path / "fmp.json", clock=lambda: now)
    fmp.put(
        "BBB",
        "float",
        [{"symbol": "BBB", "floatShares": 20}],
    )
    universe = {
        "members": [
            {"symbol": symbol, "eligible": True}
            for symbol in ("AAA", "BBB", "CCC")
        ]
    }

    result = residual_members(
        universe,
        massive,
        fmp,
        massive_max_age_days=7,
        fmp_max_age_days=7,
    )

    assert [member["symbol"] for member in result] == ["CCC"]


def test_assessment_never_mislabels_monetary_value_as_share_count() -> None:
    member = {
        "symbol": "AAA",
        "sector": "Energy",
        "industry": "Oil & Gas Midstream",
    }
    record = {
        "sec_cik": "0000000001",
        "entity_public_float_value": 1_000_000,
        "_raw_company_facts": {"entityName": "Example Partners L.P."},
        "field_evidence": {
            "entity_public_float_value": {
                "observed_at": "2026-06-30",
                "available_at": "2026-07-16T00:00:00+00:00",
            }
        },
    }

    assessment = assess_record(
        member,
        record,
        reference_date=date(2026, 7, 17),
        alignment_days=45,
    )

    assert assessment["status"] == "sec_price_basis_unavailable"
    assert assessment["structural_group"] == "partnership_or_mlp"
    assert assessment["conversion_eligible"] is False
    assert assessment["free_float_shares"] is None


def test_audit_stores_raw_snapshot_and_counts_stale_value(
    tmp_path: Path,
) -> None:
    def provider(symbol: str):
        return {
            "symbol": symbol,
            "as_of": "2026-07-17T12:00:00+00:00",
            "sec_cik": "0000000001",
            "entity_public_float_value": 500,
            "_raw_company_facts": {"entityName": "Example Inc."},
            "field_evidence": {
                "entity_public_float_value": {
                    "observed_at": "2025-06-30",
                    "available_at": "2026-02-01T00:00:00+00:00",
                }
            },
        }

    result = run_audit(
        [{"symbol": "AAA", "sector": "Technology", "industry": "Software"}],
        provider,
        reference_date=date(2026, 7, 17),
        alignment_days=45,
        policy=ProviderPolicy(
            timeout_seconds=1,
            max_retries=0,
            rate_limit_per_second=1_000,
        ),
        raw_snapshot_root=tmp_path / "raw",
    )

    assert result["status_counts"] == {"sec_monetary_value_stale": 1}
    assert result["conversion_eligible"] == 0
    assert len(result["members"][0]["raw_snapshot_sha256"]) == 64
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 1


def test_audit_cli_writes_governed_report(
    tmp_path: Path, monkeypatch
) -> None:
    universe_path = tmp_path / "universe.json"
    universe_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-17T11:00:00",
                "members": [{"symbol": "AAA", "eligible": True}],
            }
        ),
        encoding="utf-8",
    )
    massive_path = tmp_path / "massive.json"
    MassiveFloatSnapshotCache(massive_path).append_page([], None)
    settings_path = tmp_path / "settings.json"
    report_path = tmp_path / "audit.json"
    settings_path.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe_path),
                "massive_float_cache_path": str(massive_path),
                "massive_float_cache_days": 7,
                "fmp_cache_path": str(tmp_path / "fmp.json"),
                "fmp_float_cache_days": 7,
                "sec_public_float_audit_report_path": str(report_path),
                "sec_public_float_alignment_days": 45,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        audit_module, "build_sec_secondary_provider", lambda *_args: object()
    )
    monkeypatch.setattr(
        audit_module,
        "run_audit",
        lambda members, *_args, **_kwargs: {
            "requested": len(members),
            "audited": len(members),
            "conversion_eligible": 0,
            "status_counts": {"sec_not_reported": len(members)},
            "structural_group_counts": {},
            "members": [],
        },
    )

    assert audit_module.main(["--settings", str(settings_path)]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["reference_universe"] == "US_MARKET_ELIGIBLE"
    assert report["reference_date"] == "2026-07-17"
    assert report["requested"] == 1
