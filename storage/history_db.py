from __future__ import annotations

import json
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

                model_version      TEXT NOT NULL DEFAULT 'legacy',
                reference_universe TEXT,
                reference_date     TEXT,
                reference_count    INTEGER,
                reference_version  TEXT,
                altman_z            REAL,
                interest_coverage   REAL,
                target_upside       REAL,
                f_score_annual      REAL,
                roic                REAL,
                score_coverage      REAL,
                source_quality      REAL,
                data_freshness      REAL,
                missing_required_features TEXT,
                risk_evidence_missing TEXT,
                observed_risk_penalty REAL,
                risk_uncertainty_penalty REAL,
                field_evidence_json  TEXT,
                raw_snapshot_hash    TEXT,
                raw_snapshot_path    TEXT,
                earnings_date       TEXT,
                quantity            REAL,
                is_candidate        INTEGER,

                recommendation     TEXT,

                PRIMARY KEY (
                    snapshot_date,
                    symbol
                )
            )
            """
        )

        self._ensure_snapshot_columns()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS outcome_results
            (
                decision_date       TEXT NOT NULL,
                symbol              TEXT NOT NULL,
                company_name        TEXT,
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
                business_score      REAL,
                valuation_score     REAL,
                financial_score     REAL,
                timing_score        REAL,
                risk_penalty        REAL,
                has_deal_breaker    INTEGER NOT NULL DEFAULT 0,
                deal_breakers_json  TEXT NOT NULL DEFAULT '[]',

                PRIMARY KEY (
                    decision_date,
                    symbol
                )
            )
            """
        )

        self._ensure_outcome_snapshot_columns()
        self._ensure_outcome_result_columns()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_triggers
            (
                symbol             TEXT NOT NULL PRIMARY KEY,
                condition_text     TEXT NOT NULL,
                last_triggered_at  TEXT NOT NULL
            )
            """
        )

        self.connection.commit()

    def _ensure_snapshot_columns(self) -> None:
        columns = {
            row[1]
            for row in self.connection.execute(
                "PRAGMA table_info(snapshots)"
            ).fetchall()
        }
        additions = {
            "model_version": "TEXT NOT NULL DEFAULT 'legacy'",
            "reference_universe": "TEXT",
            "reference_date": "TEXT",
            "reference_count": "INTEGER",
            "reference_version": "TEXT",
            "altman_z": "REAL",
            "interest_coverage": "REAL",
            "target_upside": "REAL",
            "f_score_annual": "REAL",
            "roic": "REAL",
            "score_coverage": "REAL",
            "source_quality": "REAL",
            "data_freshness": "REAL",
            "missing_required_features": "TEXT",
            "risk_evidence_missing": "TEXT",
            "observed_risk_penalty": "REAL",
            "risk_uncertainty_penalty": "REAL",
            "field_evidence_json": "TEXT",
            "analysis_values_json": "TEXT",
            "raw_snapshot_hash": "TEXT",
            "raw_snapshot_path": "TEXT",
            "earnings_date": "TEXT",
            "quantity": "REAL",
            "is_candidate": "INTEGER",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.connection.execute(
                    f"ALTER TABLE snapshots ADD COLUMN {name} {definition}"
                )

    def _ensure_outcome_snapshot_columns(self) -> None:
        columns = {
            row[1]
            for row in self.connection.execute(
                "PRAGMA table_info(outcome_snapshots)"
            ).fetchall()
        }
        additions = {
            "business_score": "REAL",
            "valuation_score": "REAL",
            "financial_score": "REAL",
            "timing_score": "REAL",
            "deal_breakers_json": "TEXT NOT NULL DEFAULT '[]'",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.connection.execute(
                    f"ALTER TABLE outcome_snapshots "
                    f"ADD COLUMN {name} {definition}"
                )

    def _ensure_outcome_result_columns(self) -> None:
        columns = {
            row[1]
            for row in self.connection.execute(
                "PRAGMA table_info(outcome_results)"
            ).fetchall()
        }
        if "company_name" not in columns:
            self.connection.execute(
                "ALTER TABLE outcome_results "
                "ADD COLUMN company_name TEXT"
            )
        self.connection.execute(
            """
            UPDATE outcome_results
            SET company_name = (
                SELECT company_name
                FROM outcome_snapshots
                WHERE outcome_snapshots.decision_date = outcome_results.decision_date
                  AND outcome_snapshots.symbol = outcome_results.symbol
            )
            WHERE COALESCE(TRIM(company_name), '') = ''
            """
        )

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
                business_score,
                valuation_score,
                financial_score,
                timing_score,
                risk_penalty,
                has_deal_breaker,
                deal_breakers_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                data["business_score"],
                data["valuation_score"],
                data["financial_score"],
                data["timing_score"],
                data["risk_penalty"],
                int(data["has_deal_breaker"]),
                json.dumps(
                    data["deal_breakers"],
                    ensure_ascii=False,
                ),
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

        if "deal_breakers_json" in result.columns:
            result["deal_breakers"] = result[
                "deal_breakers_json"
            ].map(
                lambda value: tuple(
                    json.loads(value or "[]")
                )
            )

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
                company_name,
                horizon_days,
                due_date,
                evaluation_date,
                evaluation_lag_days,
                decision_price,
                outcome_price,
                return_pct
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["decision_date"],
                data["symbol"],
                data["company_name"],
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

    @staticmethod
    def _analysis_values(row: pd.Series) -> str | None:
        """Serializa os valores escalares da linha de análise.

        O `field_evidence` já registra *situação/fonte/data* de cada campo, mas
        não o número: métricas que o Atlas deriva em memória (RSI, momentum,
        EV/EBITDA, médias móveis, dívida líquida) ficavam sem valor persistido,
        e a página da empresa não tinha como exibi-las.

        Estritamente aditivo e sem efeito sobre o modelo: nada aqui volta para
        scoring, decisão ou política -- é evidência de leitura. Colunas não
        escalares (o próprio `field_evidence`, DataFrames de balanço) ficam de
        fora; elas já têm armazenamento próprio.
        """
        values: dict[str, object] = {}
        for key, value in row.items():
            name = str(key)
            if name == "field_evidence" or isinstance(value, (dict, list, tuple, set)):
                continue
            try:
                if value is None or pd.isna(value):
                    continue
            except (TypeError, ValueError):
                pass
            if isinstance(value, (bool, int, float, str)):
                values[name] = value
            else:
                try:
                    values[name] = value.item()
                except (AttributeError, ValueError):
                    values[name] = str(value)
        if not values:
            return None
        return json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)

    def save_snapshot(
        self,
        df: pd.DataFrame,
        snapshot_date: str,
        model_version: str = "legacy",
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

                    str(model_version).strip() or "legacy",
                    row.get("reference_universe"),
                    row.get("reference_date"),
                    (
                        int(row["reference_count"])
                        if "reference_count" in row
                        and pd.notna(row["reference_count"])
                        else None
                    ),
                    row.get("reference_version"),
                    row.get("altman_z"),
                    row.get("interest_coverage"),
                    row.get("target_upside"),
                    row.get("f_score_annual", row.get("piotroski_f")),
                    row.get("roic"),
                    row.get(
                        "Data Coverage",
                        row.get("Score Coverage", row.get("Confidence Score")),
                    ),
                    row.get("Source Quality"),
                    row.get("Data Freshness"),
                    row.get("Missing Required Features"),
                    row.get("Risk Evidence Missing"),
                    row.get("Observed Risk Penalty"),
                    row.get("Risk Uncertainty Penalty"),
                    (
                        json.dumps(
                            row.get("field_evidence"),
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        )
                        if isinstance(row.get("field_evidence"), dict)
                        else row.get("field_evidence")
                    ),
                    row.get("raw_snapshot_hash"),
                    row.get("raw_snapshot_path"),
                    row.get("earnings_date"),
                    row.get("quantity"),
                    (
                        int(row["is_candidate"])
                        if "is_candidate" in row and pd.notna(row["is_candidate"])
                        else None
                    ),

                    # coluna de storage segue nomeada `recommendation` por
                    # compat de schema; alimentada pela faixa descritiva
                    # `Score Band` (o antigo rótulo de compra foi aposentado
                    # em favor de `Decision`). `Recommendation` é fallback
                    # para snapshots legados/df antigos.
                    row.get("Score Band", row.get("Recommendation")),
                    self._analysis_values(row),
                )
            )

        self.connection.executemany(
            """
            INSERT OR REPLACE INTO snapshots
            (
                snapshot_date,
                symbol,
                business_score,
                valuation_score,
                financial_score,
                timing_score,
                investment_score,
                opportunity_score,
                confidence_score,
                model_version,
                reference_universe,
                reference_date,
                reference_count,
                reference_version,
                altman_z,
                interest_coverage,
                target_upside,
                f_score_annual,
                roic,
                score_coverage,
                source_quality,
                data_freshness,
                missing_required_features,
                risk_evidence_missing,
                observed_risk_penalty,
                risk_uncertainty_penalty,
                field_evidence_json,
                raw_snapshot_hash,
                raw_snapshot_path,
                earnings_date,
                quantity,
                is_candidate,
                recommendation,
                analysis_values_json
            )
            VALUES
            (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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

    def save_watchlist_trigger(
        self,
        symbol: str,
        condition_text: str,
        last_triggered_at: str,
    ) -> None:
        """
        Registra a última vez que a condição de trigger de um símbolo da
        watchlist passou a valer. Nunca escreve em config/watchlist.csv --
        esse arquivo é curado à mão pelo usuário; este é o estado que o run
        calcula (ver watchlist/aging.py).
        """
        self.connection.execute(
            """
            INSERT INTO watchlist_triggers
                (symbol, condition_text, last_triggered_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                condition_text = excluded.condition_text,
                last_triggered_at = excluded.last_triggered_at
            """,
            (symbol, condition_text, last_triggered_at),
        )
        self.connection.commit()

    def load_watchlist_triggers(self) -> dict[str, dict[str, str]]:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT symbol, condition_text, last_triggered_at "
            "FROM watchlist_triggers"
        )
        return {
            row[0]: {
                "condition_text": row[1],
                "last_triggered_at": row[2],
            }
            for row in cursor.fetchall()
        }

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
