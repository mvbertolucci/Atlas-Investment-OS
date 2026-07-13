from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from universe.models import UniverseMember, UniversePolicy, UniverseReport


def load_universe_policy(path: str | Path) -> UniversePolicy:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return UniversePolicy.from_dict(data)


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "n/a"}:
        return ""
    return text


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _present(value: Any) -> bool:
    if _text(value):
        return True
    return _number(value) is not None


def _normalized_set(values: tuple[str, ...]) -> set[str]:
    return {value.casefold() for value in values}


def evaluate_universe(
    frame: pd.DataFrame,
    policy: UniversePolicy,
) -> UniverseReport:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("evaluate_universe exige um DataFrame.")
    if not isinstance(policy, UniversePolicy):
        raise TypeError("evaluate_universe exige UniversePolicy.")

    allowed_quote_types = _normalized_set(policy.allowed_quote_types)
    allowed_currencies = _normalized_set(policy.allowed_currencies)
    allowed_countries = _normalized_set(policy.allowed_countries)
    symbols = frame.get("symbol", pd.Series(dtype=object)).map(_text).str.upper()
    duplicated_symbols = set(symbols[symbols.duplicated(keep=False)]) - {""}
    members: list[UniverseMember] = []

    for _, row in frame.iterrows():
        symbol = _text(row.get("symbol")).upper()
        quote_type = _text(row.get("quote_type")).upper()
        currency = _text(row.get("currency")).upper()
        country = _text(row.get("country"))
        sector = _text(row.get("sector"))
        industry = _text(row.get("industry"))
        price = _number(row.get("price"))
        market_cap = _number(row.get("market_cap"))
        volume = _number(row.get("volume"))

        missing = [
            field_name
            for field_name in policy.required_fields
            if not _present(row.get(field_name))
        ]
        coverage = round(
            (len(policy.required_fields) - len(missing))
            / len(policy.required_fields)
            * 100,
            1,
        )
        reasons: list[str] = [
            f"MISSING_REQUIRED_FIELD:{field_name}"
            for field_name in missing
        ]

        if symbol and symbol in duplicated_symbols:
            reasons.append("DUPLICATE_SYMBOL")
        if quote_type and quote_type.casefold() not in allowed_quote_types:
            reasons.append("UNSUPPORTED_QUOTE_TYPE")
        if currency and currency.casefold() not in allowed_currencies:
            reasons.append("UNSUPPORTED_CURRENCY")
        if country and country.casefold() not in allowed_countries:
            reasons.append("UNSUPPORTED_COUNTRY")
        if market_cap is not None and market_cap < policy.min_market_cap:
            reasons.append("MARKET_CAP_BELOW_MINIMUM")
        if price is not None and price < policy.min_price:
            reasons.append("PRICE_BELOW_MINIMUM")
        if volume is not None and volume < policy.min_volume:
            reasons.append("VOLUME_BELOW_MINIMUM")

        members.append(
            UniverseMember(
                symbol=symbol,
                eligible=not reasons,
                exclusion_reasons=tuple(reasons),
                data_coverage_pct=coverage,
                quote_type=quote_type,
                currency=currency,
                country=country,
                sector=sector,
                industry=industry,
                price=price,
                market_cap=market_cap,
                volume=volume,
            )
        )

    return UniverseReport(policy=policy, members=tuple(members))
