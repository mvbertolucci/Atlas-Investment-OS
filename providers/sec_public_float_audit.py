from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from providers.contracts import ProviderClient, ProviderError, ProviderPolicy
from providers.fmp_cache import FmpCacheStore
from providers.massive_cache import MassiveFloatSnapshotCache
from providers.massive_prefetch import _atomic_write
from providers.sec_companyfacts import build_sec_secondary_provider
from storage.raw_snapshots import store_raw_snapshot


ROOT = Path(__file__).resolve().parents[1]


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _fmp_float_available(payload: Any) -> bool:
    return isinstance(payload, list) and any(
        isinstance(row, Mapping)
        and _number(row.get("floatShares")) is not None
        for row in payload
    )


def residual_members(
    universe: Mapping[str, Any],
    massive_cache: MassiveFloatSnapshotCache,
    fmp_cache: FmpCacheStore,
    *,
    massive_max_age_days: float,
    fmp_max_age_days: float,
) -> list[dict[str, Any]]:
    state = massive_cache.prepare(max_age_days=massive_max_age_days)
    if not state.get("complete"):
        raise RuntimeError(
            "A auditoria SEC exige snapshot Massive Float completo e vigente."
        )
    members = universe.get("members")
    if not isinstance(members, list):
        raise ValueError("Universo oficial não contém lista members.")
    residual: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, Mapping) or member.get("eligible") is not True:
            continue
        symbol = str(member.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        massive_row, _ = massive_cache.lookup(
            symbol, max_age_days=massive_max_age_days
        )
        massive_available = massive_row is not None and _number(
            massive_row.get("free_float")
        ) is not None
        fmp_available = _fmp_float_available(
            fmp_cache.get(symbol, "float", max_age_days=fmp_max_age_days)
        )
        if not massive_available and not fmp_available:
            residual.append(dict(member))
    return residual


def _structural_group(
    member: Mapping[str, Any], company_facts: Mapping[str, Any]
) -> str:
    industry = str(member.get("industry") or "").casefold()
    entity_name = str(company_facts.get("entityName") or "").upper()
    if industry == "shell companies":
        return "shell_company"
    if any(marker in entity_name for marker in (" L.P.", " LP", " PARTNERS")):
        return "partnership_or_mlp"
    if industry == "asset management":
        return "asset_manager_or_fund_review"
    return "operating_or_recent_listing"


def assess_record(
    member: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    reference_date: date,
    alignment_days: int,
) -> dict[str, Any]:
    evidence = (record.get("field_evidence") or {}).get(
        "entity_public_float_value"
    ) or {}
    company_facts = record.get("_raw_company_facts") or {}
    value = _number(record.get("entity_public_float_value"))
    observed_at = str(evidence.get("observed_at") or "") or None
    result: dict[str, Any] = {
        "symbol": str(member.get("symbol") or "").strip().upper(),
        "sector": member.get("sector"),
        "industry": member.get("industry"),
        "structural_group": _structural_group(member, company_facts),
        "sec_cik": record.get("sec_cik"),
        "entity_public_float_usd": value,
        "observed_at": observed_at,
        "available_at": evidence.get("available_at"),
        "free_float_shares": None,
        "conversion_eligible": False,
    }
    if value is None:
        result.update(
            status="sec_not_reported",
            reason="dei:EntityPublicFloat ausente nos Company Facts",
        )
        return result
    if value == 0:
        result.update(
            status="sec_zero_public_float",
            reason="valor monetário SEC igual a zero não produz denominador",
        )
        return result
    try:
        observed = date.fromisoformat(str(observed_at)[:10])
    except ValueError:
        result.update(
            status="sec_invalid_observation_date",
            reason="data de observação SEC ausente ou inválida",
        )
        return result
    age_days = (reference_date - observed).days
    result["age_days"] = age_days
    if age_days < 0:
        result.update(
            status="sec_future_observation",
            reason="observação SEC posterior à data de referência",
        )
    elif age_days > alignment_days:
        result.update(
            status="sec_monetary_value_stale",
            reason=(
                "valor monetário SEC fora da janela de alinhamento; não é "
                "quantidade de ações"
            ),
        )
    else:
        result.update(
            status="sec_price_basis_unavailable",
            reason=(
                "a SEC não informa no Company Facts o preço exato usado para "
                "converter o valor monetário em ações"
            ),
        )
    return result


def run_audit(
    members: Sequence[Mapping[str, Any]],
    provider: Any,
    *,
    reference_date: date,
    alignment_days: int,
    policy: ProviderPolicy,
    raw_snapshot_root: Path,
) -> dict[str, Any]:
    client = ProviderClient("SEC EDGAR Company Facts", policy)
    assessments: list[dict[str, Any]] = []
    for member in members:
        symbol = str(member.get("symbol") or "").strip().upper()
        try:
            record = client.execute("public_float_audit", provider, symbol)
            raw = record.get("_raw_company_facts") or {}
            receipt = store_raw_snapshot(
                raw,
                raw_snapshot_root,
                provider="SEC_EDGAR_Company_Facts",
                symbol=symbol,
                collected_at=str(
                    record.get("as_of")
                    or datetime.now(timezone.utc).isoformat()
                ),
            )
            assessment = assess_record(
                member,
                record,
                reference_date=reference_date,
                alignment_days=alignment_days,
            )
            assessment["raw_snapshot_sha256"] = receipt.sha256
        except ProviderError as exc:
            assessment = {
                "symbol": symbol,
                "sector": member.get("sector"),
                "industry": member.get("industry"),
                "structural_group": "unresolved",
                "status": "sec_provider_unavailable",
                "reason": exc.kind.value,
                "conversion_eligible": False,
                "free_float_shares": None,
            }
        assessments.append(assessment)
    statuses = Counter(item["status"] for item in assessments)
    groups = Counter(item["structural_group"] for item in assessments)
    return {
        "requested": len(members),
        "audited": len(assessments),
        "conversion_eligible": sum(
            bool(item["conversion_eligible"]) for item in assessments
        ),
        "status_counts": dict(sorted(statuses.items())),
        "structural_group_counts": dict(sorted(groups.items())),
        "members": assessments,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita EntityPublicFloat SEC para lacunas de free float."
    )
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--max-symbols", type=int)
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    if not settings_path.is_absolute():
        settings_path = ROOT / settings_path
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    universe_path = ROOT / str(
        settings.get(
            "massive_prefetch_universe_path",
            "output/dados/research_universe_report_market.json",
        )
    )
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    reference_date = date.fromisoformat(str(universe["generated_at"])[:10])
    massive_cache = MassiveFloatSnapshotCache(
        ROOT / str(settings["massive_float_cache_path"])
    )
    fmp_cache = FmpCacheStore(ROOT / str(settings["fmp_cache_path"]))
    members = residual_members(
        universe,
        massive_cache,
        fmp_cache,
        massive_max_age_days=float(settings.get("massive_float_cache_days", 7)),
        fmp_max_age_days=float(settings.get("fmp_float_cache_days", 7)),
    )
    if args.max_symbols is not None:
        if args.max_symbols <= 0:
            raise ValueError("--max-symbols deve ser positivo.")
        members = members[: args.max_symbols]
    provider = build_sec_secondary_provider(ROOT, settings)
    if provider is None:
        raise RuntimeError("SEC está desabilitada ou sec_user_agent está ausente.")
    alignment_days = int(settings.get("sec_public_float_alignment_days", 45))
    summary = run_audit(
        members,
        provider,
        reference_date=reference_date,
        alignment_days=alignment_days,
        policy=ProviderPolicy(
            timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
            max_retries=int(settings.get("provider_max_retries", 2)),
            backoff_seconds=float(settings.get("provider_backoff_seconds", 0.5)),
            rate_limit_per_second=float(
                settings.get("sec_public_float_rate_limit_per_second", 2)
            ),
        ),
        raw_snapshot_root=ROOT
        / str(settings.get("raw_snapshot_path", "data/raw_snapshots")),
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_universe": settings.get(
            "scoring_reference_universe_id", "US_MARKET_ELIGIBLE"
        ),
        "reference_date": reference_date.isoformat(),
        "alignment_days": alignment_days,
        **summary,
    }
    report_path = ROOT / str(
        settings.get(
            "sec_public_float_audit_report_path",
            "output/dados/sec_public_float_audit.json",
        )
    )
    _atomic_write(report, report_path)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "members"},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
