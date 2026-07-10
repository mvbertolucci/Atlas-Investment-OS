from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "atlas.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str = "atlas") -> logging.Logger:
    """
    Retorna um logger configurado para console e arquivo.

    O arquivo de log é salvo em:

        logs/atlas.log

    Os arquivos são rotacionados quando atingem 5 MB,
    mantendo até cinco backups.
    """

    logger = logging.getLogger(name)

    if getattr(logger, "_atlas_configured", False):
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger._atlas_configured = True  # type: ignore[attr-defined]

    return logger