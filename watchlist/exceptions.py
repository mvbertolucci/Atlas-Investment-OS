from __future__ import annotations


class WatchlistError(Exception):
    """Erro-base da camada de watchlist."""


class WatchlistFileNotFoundError(
    WatchlistError,
    FileNotFoundError,
):
    """Arquivo de watchlist não encontrado."""


class WatchlistSchemaError(
    WatchlistError,
    ValueError,
):
    """Estrutura inválida do arquivo de watchlist."""


class WatchlistRowError(
    WatchlistError,
    ValueError,
):
    """Linha inválida do arquivo de watchlist."""
