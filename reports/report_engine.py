from __future__ import annotations
from typing import Any
import pandas as pd
from reports.report_models import CompanyReport

def _split(value: Any)->tuple[str,...]:
    if value is None:
        return ()
    text=str(value).strip()
    if not text or text.lower() in {"nan","none"}:
        return ()
    return tuple(x.strip() for x in text.split(";") if x.strip())

def build_company_reports(df: pd.DataFrame)->list[CompanyReport]:
    reports=[]
    for _,row in df.iterrows():
        reports.append(CompanyReport(
            symbol=row.get("symbol",""),
            company_name=row.get("name",""),
            decision=row.get("Decision",""),
            decision_rating=row.get("Decision Rating",""),
            suggested_action=row.get("Suggested Action",""),
            decision_confidence=row.get("Decision Confidence"),
            investment_score=row.get("Investment Score"),
            opportunity_score=row.get("Opportunity Score"),
            conviction_score=row.get("Conviction Score"),
            business_score=row.get("Business Score"),
            valuation_score=row.get("Valuation Score"),
            financial_score=row.get("Financial Score"),
            timing_score=row.get("Timing Score"),
            confidence_score=row.get("Confidence Score"),
            risk_penalty=row.get("Risk Penalty"),
            investment_thesis=row.get("Investment Thesis",""),
            strengths=_split(row.get("Thesis Strengths")),
            risks=_split(row.get("Thesis Risks")),
            catalysts=_split(row.get("Thesis Catalysts")),
            deal_breakers=_split(row.get("Deal Breakers")),
            decision_drivers=_split(row.get("Decision Drivers")),
        ))
    return reports
