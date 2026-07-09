from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


DB_PATH = Path(__file__).resolve().parent / "atlas.db"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = connect()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        executed_at TEXT NOT NULL,
        symbols_count INTEGER,
        version TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        metric TEXT NOT NULL,
        value REAL,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS factor_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        business_score REAL,
        valuation_score REAL,
        financial_score REAL,
        timing_score REAL,
        investment_score REAL,
        confidence_score REAL,
        recommendation TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    con.commit()
    con.close()


def save_run(df: pd.DataFrame, version: str = "0.3.0") -> int:
    con = connect()
    cur = con.cursor()
    now = datetime.now().isoformat(timespec="seconds")

    cur.execute(
        "INSERT INTO runs (executed_at, symbols_count, version) VALUES (?, ?, ?)",
        (now, len(df), version),
    )

    run_id = cur.lastrowid
    con.commit()
    con.close()
    return int(run_id)


def save_snapshots(run_id: int, df: pd.DataFrame) -> None:
    con = connect()
    now = datetime.now().isoformat(timespec="seconds")

    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue

        payload = row.to_dict()
        payload = {k: (None if pd.isna(v) else v) for k, v in payload.items()}

        con.execute(
            """
            INSERT INTO snapshots (run_id, symbol, snapshot_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, symbol, json.dumps(payload, default=str), now),
        )

    con.commit()
    con.close()


def save_metrics(run_id: int, df: pd.DataFrame) -> None:
    con = connect()
    now = datetime.now().isoformat(timespec="seconds")

    skip_cols = {"symbol", "name", "sector", "industry", "country", "currency", "Recommendation"}

    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue

        for col, val in row.items():
            if col in skip_cols:
                continue

            num = pd.to_numeric(val, errors="coerce")
            if pd.isna(num):
                continue

            con.execute(
                """
                INSERT INTO metrics (run_id, symbol, metric, value, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, symbol, col, float(num), now),
            )

    con.commit()
    con.close()


def save_factor_scores(run_id: int, df: pd.DataFrame) -> None:
    con = connect()
    now = datetime.now().isoformat(timespec="seconds")

    def get_num(row, col):
        return None if col not in row or pd.isna(row[col]) else float(row[col])

    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue

        con.execute(
            """
            INSERT INTO factor_scores (
                run_id, symbol, business_score, valuation_score,
                financial_score, timing_score, investment_score,
                confidence_score, recommendation, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                symbol,
                get_num(row, "Business Score"),
                get_num(row, "Valuation Score"),
                get_num(row, "Financial Score"),
                get_num(row, "Timing Score"),
                get_num(row, "Investment Score"),
                get_num(row, "Confidence Score"),
                str(row.get("Recommendation", "")),
                now,
            ),
        )

    con.commit()
    con.close()


def save_all(df: pd.DataFrame, version: str = "0.3.0") -> int:
    init_db()
    run_id = save_run(df, version=version)
    save_snapshots(run_id, df)
    save_metrics(run_id, df)
    save_factor_scores(run_id, df)
    return run_id