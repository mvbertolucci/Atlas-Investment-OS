from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select

from .db import SessionLocal
from .migrations import init_db
from .models import Company, Run, Score, Snapshot


SCORE_COLUMNS = {
    "Business Score": "business_score",
    "Valuation Score": "valuation_score",
    "Financial Score": "financial_score",
    "Timing Score": "timing_score",
    "Confidence Score": "confidence_score",
    "Investment Score": "investment_score",
    "Recommendation": "recommendation",
}


@dataclass
class AtlasRepository:
    version: str = "Atlas Core 0.1"

    def __post_init__(self) -> None:
        init_db()
        self._start_time = time.perf_counter()

    def start_run(self, symbols_processed: int) -> int:
        with SessionLocal() as session:
            run = Run(
                executed_at=datetime.utcnow(),
                version=self.version,
                symbols_processed=int(symbols_processed),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def finish_run(self, run_id: int) -> None:
        elapsed = time.perf_counter() - self._start_time
        with SessionLocal() as session:
            run = session.get(Run, run_id)
            if run:
                run.execution_seconds = elapsed
                session.commit()

    def save_companies(self, df: pd.DataFrame) -> None:
        if "symbol" not in df.columns:
            return

        with SessionLocal() as session:
            for _, row in df.iterrows():
                symbol = str(row.get("symbol", "")).strip()
                if not symbol:
                    continue
                company = session.get(Company, symbol) or Company(symbol=symbol)
                company.company_name = _clean(row.get("company_name") or row.get("name"))
                company.sector = _clean(row.get("sector"))
                company.industry = _clean(row.get("industry"))
                company.country = _clean(row.get("country"))
                company.currency = _clean(row.get("currency"))
                company.updated_at = datetime.utcnow()
                session.merge(company)
            session.commit()

    def save_snapshots(self, run_id: int, df: pd.DataFrame) -> None:
        with SessionLocal() as session:
            for _, row in df.iterrows():
                symbol = str(row.get("symbol", "")).strip()
                if not symbol:
                    continue
                payload = _row_to_json(row)
                session.add(Snapshot(run_id=run_id, symbol=symbol, snapshot_json=payload))
            session.commit()

    def save_scores(self, run_id: int, df: pd.DataFrame) -> None:
        with SessionLocal() as session:
            for _, row in df.iterrows():
                symbol = str(row.get("symbol", "")).strip()
                if not symbol:
                    continue
                score = Score(run_id=run_id, symbol=symbol)
                for df_col, model_attr in SCORE_COLUMNS.items():
                    if df_col in df.columns:
                        setattr(score, model_attr, _number_or_text(row.get(df_col)))
                session.add(score)
            session.commit()

    def previous_run_id(self, current_run_id: int) -> int | None:
        with SessionLocal() as session:
            stmt = (
                select(Run.id)
                .where(Run.id < current_run_id)
                .order_by(Run.id.desc())
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none()

    def scores_for_run(self, run_id: int) -> pd.DataFrame:
        with SessionLocal() as session:
            stmt = select(Score).where(Score.run_id == run_id)
            rows = session.execute(stmt).scalars().all()
            data = []
            for s in rows:
                data.append({
                    "run_id": s.run_id,
                    "symbol": s.symbol,
                    "previous_score" if False else "investment_score": s.investment_score,
                    "business_score": s.business_score,
                    "valuation_score": s.valuation_score,
                    "financial_score": s.financial_score,
                    "timing_score": s.timing_score,
                    "confidence_score": s.confidence_score,
                    "recommendation": s.recommendation,
                })
            return pd.DataFrame(data)

    def compare_with_previous(self, current_run_id: int) -> pd.DataFrame:
        previous_run_id = self.previous_run_id(current_run_id)
        current = self.scores_for_run(current_run_id)

        if previous_run_id is None or current.empty:
            out = current.rename(columns={
                "investment_score": "current_score",
                "recommendation": "current_recommendation",
            })
            out["previous_score"] = None
            out["delta_score"] = None
            out["previous_recommendation"] = None
            return out[[
                "symbol", "previous_score", "current_score", "delta_score",
                "previous_recommendation", "current_recommendation",
            ]]

        previous = self.scores_for_run(previous_run_id).rename(columns={
            "investment_score": "previous_score",
            "recommendation": "previous_recommendation",
        })
        current = current.rename(columns={
            "investment_score": "current_score",
            "recommendation": "current_recommendation",
        })

        merged = current.merge(
            previous[["symbol", "previous_score", "previous_recommendation"]],
            on="symbol",
            how="left",
        )
        merged["delta_score"] = merged["current_score"] - merged["previous_score"]
        return merged[[
            "symbol", "previous_score", "current_score", "delta_score",
            "previous_recommendation", "current_recommendation",
        ]].sort_values("delta_score", ascending=False, na_position="last")


def _clean(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _number_or_text(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _row_to_json(row: pd.Series) -> str:
    data = {}
    for key, value in row.items():
        if pd.isna(value):
            data[key] = None
        elif hasattr(value, "item"):
            data[key] = value.item()
        else:
            data[key] = value
    return json.dumps(data, ensure_ascii=False, default=str)
