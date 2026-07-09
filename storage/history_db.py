from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


class HistoryDatabase:
    """
    Banco de dados histórico do Atlas.

    Armazena um snapshot de cada execução do sistema.
    """

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.connection = sqlite3.connect(self.database_path)

        self._create_tables()

    def _create_tables(self) -> None:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots
            (
                snapshot_date      TEXT NOT NULL,
                symbol             TEXT NOT NULL,

                business_score     REAL,
                valuation_score    REAL,
                financial_score    REAL,
                timing_score       REAL,

                investment_score   REAL,
                opportunity_score  REAL,
                confidence_score   REAL,

                recommendation     TEXT,

                PRIMARY KEY (
                    snapshot_date,
                    symbol
                )
            )
            """
        )

        self.connection.commit()

    def save_snapshot(
        self,
        df: pd.DataFrame,
        snapshot_date: str,
    ) -> None:

        if df.empty:
            return

        rows = []

        for _, row in df.iterrows():

            rows.append(
                (
                    snapshot_date,
                    row.get("symbol"),

                    row.get("Business Score"),
                    row.get("Valuation Score"),
                    row.get("Financial Score"),
                    row.get("Timing Score"),

                    row.get("Investment Score"),
                    row.get("Opportunity Score"),
                    row.get("Confidence Score"),

                    row.get("Recommendation"),
                )
            )

        self.connection.executemany(
            """
            INSERT OR REPLACE INTO snapshots
            VALUES
            (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )

        self.connection.commit()

    def load_history(
        self,
        symbol: str | None = None,
    ) -> pd.DataFrame:

        if symbol is None:

            query = """
                SELECT *
                FROM snapshots
                ORDER BY
                    snapshot_date,
                    symbol
            """

            return pd.read_sql_query(
                query,
                self.connection,
            )

        query = """
            SELECT *
            FROM snapshots
            WHERE symbol = ?
            ORDER BY snapshot_date
        """

        return pd.read_sql_query(
            query,
            self.connection,
            params=(symbol,),
        )

    def list_symbols(self) -> list[str]:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT DISTINCT symbol
            FROM snapshots
            ORDER BY symbol
            """
        )

        return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ):
        self.close()