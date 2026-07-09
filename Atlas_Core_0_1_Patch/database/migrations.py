from __future__ import annotations

from .db import Base, get_engine
from . import models  # noqa: F401  # registra os modelos no metadata


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
