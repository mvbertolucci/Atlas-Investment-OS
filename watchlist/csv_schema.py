from __future__ import annotations

REQUIRED_COLUMNS = ("symbol",)

OPTIONAL_COLUMNS = (
    "name",
    "included_at",
    "note",
    "trigger_condition",
)

SUPPORTED_COLUMNS = (
    *REQUIRED_COLUMNS,
    *OPTIONAL_COLUMNS,
)

COLUMN_ALIASES = {
    "ticker": "symbol",
    "ativo": "symbol",
    "data_inclusao": "included_at",
    "data_de_inclusao": "included_at",
    "data de inclusão": "included_at",
    "included date": "included_at",
    "nota": "note",
    "observacao": "note",
    "observação": "note",
    "observacoes": "note",
    "observações": "note",
    "motivo": "note",
    "condicao": "trigger_condition",
    "condição": "trigger_condition",
    "condicao_trigger": "trigger_condition",
    "condição de trigger": "trigger_condition",
    "trigger": "trigger_condition",
    "trigger_condition": "trigger_condition",
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
