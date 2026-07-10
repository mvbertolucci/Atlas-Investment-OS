from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    version: Mapped[str] = mapped_column(String(50), default="Atlas Core 0.1")
    symbols_processed: Mapped[int] = mapped_column(Integer, default=0)
    execution_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    scores: Mapped[list["Score"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Company(Base):
    __tablename__ = "companies"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(180), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    snapshot_json: Mapped[str] = mapped_column(Text)

    run: Mapped[Run] = relationship(back_populates="snapshots")

    __table_args__ = (UniqueConstraint("run_id", "symbol", name="uq_snapshot_run_symbol"),)


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)

    business_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    financial_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timing_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    investment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(80), nullable=True)

    run: Mapped[Run] = relationship(back_populates="scores")

    __table_args__ = (UniqueConstraint("run_id", "symbol", name="uq_score_run_symbol"),)
