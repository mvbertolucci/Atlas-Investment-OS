from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from outcomes.models import OutcomeResult, OutcomeSnapshot


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

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS outcome_results
            (
                decision_date       TEXT NOT NULL,
                symbol              TEXT NOT NULL,
                horizon_days        INTEGER NOT NULL,
                due_date            TEXT NOT NULL,
                evaluation_date     TEXT NOT NULL,
                evaluation_lag_days INTEGER NOT NULL,
                decision_price      REAL NOT NULL,
                outcome_price       REAL NOT NULL,
                return_pct          REAL NOT NULL,

                PRIMARY KEY (
                    decision_date,
                    symbol,
                    horizon_days
                )
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS outcome_snapshots
            (
                decision_date       TEXT NOT NULL,
                symbol              TEXT NOT NULL,
                company_name        TEXT,
                decision_price      REAL NOT NULL,
                decision            TEXT NOT NULL,
                decision_rating     TEXT,
                investment_score    REAL,
                opportunity_score   REAL,
                conviction_score    REAL,
                decision_confidence REAL,
                risk_penalty        REAL,
                has_deal_breaker    INTEGER NOT NULL DEFAULT 0,

                PRIMARY KEY (
                    decision_date,
                    symbol
                )
            )
            """
        )

        self.connection.commit()

    def save_outcome_snapshot(
        self,
        snapshot: OutcomeSnapshot,
    ) -> None:
        if not isinstance(snapshot, OutcomeSnapshot):
            raise TypeError(
                "snapshot deve ser OutcomeSnapshot."
            )

        data = snapshot.to_dict()
        self.connection.execute(
            """
            INSERT OR REPLACE INTO outcome_snapshots
            (
                decision_date,
                symbol,
                company_name,
                decision_price,
                decision,
                decision_rating,
                investment_score,
                opportunity_score,
                conviction_score,
                decision_confidence,
                risk_penalty,
                has_deal_breaker
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["decision_date"],
                data["symbol"],
                data["company_name"],
                data["decision_price"],
                data["decision"],
                data["decision_rating"],
                data["investment_score"],
                data["opportunity_score"],
                data["conviction_score"],
                data["decision_confidence"],
                data["risk_penalty"],
                int(data["has_deal_breaker"]),
            ),
        )
        self.connection.commit()

    def save_outcome_snapshots(
        self,
        snapshots: list[OutcomeSnapshot],
    ) -> None:
        for snapshot in snapshots:
            self.save_outcome_snapshot(snapshot)

    def load_outcome_snapshots(
        self,
        symbol: str | None = None,
    ) -> pd.DataFrame:
        if symbol is None:
            query = """
                SELECT *
                FROM outcome_snapshots
                ORDER BY decision_date, symbol
            """
            result = pd.read_sql_query(
                query,
                self.connection,
            )
        else:
            query = """
                SELECT *
                FROM outcome_snapshots
                WHERE symbol = ?
                ORDER BY decision_date
            """
            result = pd.read_sql_query(
                query,
                self.connection,
                params=(str(symbol).strip().upper(),),
            )

        if "has_deal_breaker" in result.columns:
            result["has_deal_breaker"] = result[
                "has_deal_breaker"
            ].astype(bool)

        return result

    def save_outcome_result(
        self,
        result: OutcomeResult,
    ) -> None:
        if not isinstance(result, OutcomeResult):
            raise TypeError(
                "result deve ser OutcomeResult."
            )

        data = result.to_dict()
        self.connection.execute(
            """
            INSERT OR IGNORE INTO outcome_results
            (
                decision_date,
                symbol,
                horizon_days,
                due_date,
                evaluation_date,
                evaluation_lag_days,
                decision_price,
                outcome_price,
                return_pct
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["decision_date"],
                data["symbol"],
                data["horizon_days"],
                data["due_date"],
                data["evaluation_date"],
                data["evaluation_lag_days"],
                data["decision_price"],
                data["outcome_price"],
                data["return_pct"],
            ),
        )
        self.connection.commit()

    def save_outcome_results(
        self,
        results: list[OutcomeResult],
    ) -> None:
        for result in results:
            self.save_outcome_result(result)

    def load_outcome_results(
        self,
        symbol: str | None = None,
    ) -> pd.DataFrame:
        if symbol is None:
            query = """
                SELECT *
                FROM outcome_results
                ORDER BY decision_date, symbol, horizon_days
            """
            return pd.read_sql_query(
                query,
                self.connection,
            )

        query = """
            SELECT *
            FROM outcome_results
            WHERE symbol = ?
            ORDER BY decision_date, horizon_days
        """
        return pd.read_sql_query(
            query,
            self.connection,
            params=(str(symbol).strip().upper(),),
        )

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
