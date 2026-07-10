from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def normalize_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    text = str(value).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "null",
        "n/a",
    }:
        return default

    return text


def normalize_symbol(value: Any) -> str:
    return normalize_text(value).upper()


def normalize_non_negative_float(
    value: Any,
    *,
    field_name: str,
    allow_none: bool = False,
) -> float | None:
    if value is None and allow_none:
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} deve ser numérico."
        ) from exc

    if numeric != numeric:
        if allow_none:
            return None

        raise ValueError(
            f"{field_name} não pode ser NaN."
        )

    if numeric < 0:
        raise ValueError(
            f"{field_name} não pode ser negativo."
        )

    return numeric


def normalize_positive_float(
    value: Any,
    *,
    field_name: str,
) -> float:
    numeric = normalize_non_negative_float(
        value,
        field_name=field_name,
    )

    assert numeric is not None

    if numeric <= 0:
        raise ValueError(
            f"{field_name} deve ser maior que zero."
        )

    return numeric


def normalize_weight(
    value: Any,
    *,
    field_name: str,
    allow_none: bool = True,
) -> float | None:
    numeric = normalize_non_negative_float(
        value,
        field_name=field_name,
        allow_none=allow_none,
    )

    if numeric is None:
        return None

    if numeric > 1:
        raise ValueError(
            f"{field_name} deve estar entre 0 e 1."
        )

    return round(numeric, 6)


def normalize_score(
    value: Any,
    *,
    field_name: str,
    allow_none: bool = True,
) -> float | None:
    if value is None and allow_none:
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} deve ser numérico."
        ) from exc

    if numeric != numeric:
        if allow_none:
            return None

        raise ValueError(
            f"{field_name} não pode ser NaN."
        )

    return round(
        max(0.0, min(100.0, numeric)),
        1,
    )


def normalize_items(
    values: Iterable[Any] | str | None,
) -> tuple[str, ...]:
    if values is None:
        return ()

    source = (
        values.split(";")
        if isinstance(values, str)
        else values
    )

    items: list[str] = []

    for value in source:
        text = normalize_text(value)

        if text and text not in items:
            items.append(text)

    return tuple(items)


def normalize_mapping(
    values: dict[Any, Any] | None,
    *,
    field_name: str,
) -> dict[str, float]:
    if not values:
        return {}

    normalized: dict[str, float] = {}

    for raw_key, raw_value in values.items():
        key = normalize_text(raw_key)

        if not key:
            raise ValueError(
                f"{field_name} contém uma chave vazia."
            )

        value = normalize_weight(
            raw_value,
            field_name=f"{field_name}[{key}]",
            allow_none=False,
        )

        assert value is not None
        normalized[key] = value

    return normalized


def validate_weight_total(
    weights: dict[str, float],
    *,
    tolerance: float = 0.0001,
    allow_empty: bool = True,
) -> None:
    if not weights:
        if allow_empty:
            return

        raise ValueError(
            "A distribuição de pesos não pode estar vazia."
        )

    total = sum(weights.values())

    if abs(total - 1.0) > tolerance:
        raise ValueError(
            "A soma dos pesos deve ser igual a 1. "
            f"Valor encontrado: {total:.6f}."
        )
