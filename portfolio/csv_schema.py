from __future__ import annotations

REQUIRED_COLUMNS = (
    "symbol",
    "quantity",
    "average_price",
)

OPTIONAL_COLUMNS = (
    "current_price",
    "currency",
    "sector",
    "industry",
    "country",
    "notes",
)

SUPPORTED_COLUMNS = (
    *REQUIRED_COLUMNS,
    *OPTIONAL_COLUMNS,
)

COLUMN_ALIASES = {
    "ticker": "symbol",
    "asset": "symbol",
    "ativo": "symbol",
    "quantidade": "quantity",
    "qty": "quantity",
    "preco_medio": "average_price",
    "preço_médio": "average_price",
    "average cost": "average_price",
    "current price": "current_price",
    "preco_atual": "current_price",
    "preço_atual": "current_price",
    "moeda": "currency",
    "setor": "sector",
    "industria": "industry",
    "indústria": "industry",
    "pais": "country",
    "país": "country",
    "observacoes": "notes",
    "observações": "notes",
}


def normalize_column_name(name: object) -> str:
    return (
        str(name)
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def canonical_column_name(name: object) -> str:
    normalized = normalize_column_name(name)

    alias_lookup = {
        normalize_column_name(alias): target
        for alias, target in COLUMN_ALIASES.items()
    }

    return alias_lookup.get(
        normalized,
        normalized,
    )
