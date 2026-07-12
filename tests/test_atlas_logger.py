from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

import atlas_logger


def test_get_logger_is_idempotent_and_writes_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_file = tmp_path / "atlas.log"
    monkeypatch.setattr(atlas_logger, "LOG_FILE", log_file)
    name = f"atlas-test-{uuid4()}"

    logger = atlas_logger.get_logger(name)
    same_logger = atlas_logger.get_logger(name)

    assert same_logger is logger
    assert logger.level == logging.INFO
    assert logger.propagate is False
    assert len(logger.handlers) == 2

    logger.info("operational message")
    for handler in logger.handlers:
        handler.flush()

    assert "operational message" in log_file.read_text(
        encoding="utf-8"
    )

    for handler in tuple(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logging.Logger.manager.loggerDict.pop(name, None)
