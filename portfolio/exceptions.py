from __future__ import annotations


class PortfolioError(Exception):
    """Erro-base da camada de portfólio."""


class PortfolioFileNotFoundError(
    PortfolioError,
    FileNotFoundError,
):
    """Arquivo de carteira não encontrado."""


class PortfolioSchemaError(
    PortfolioError,
    ValueError,
):
    """Estrutura inválida do arquivo de carteira."""


class PortfolioRowError(
    PortfolioError,
    ValueError,
):
    """Linha inválida do arquivo de carteira."""
