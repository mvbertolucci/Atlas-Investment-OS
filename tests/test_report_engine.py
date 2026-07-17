import pandas as pd
from reports.report_engine import build_company_reports

def test_build_company_reports():
    df=pd.DataFrame([{
        "symbol":"NVDA","name":"NVIDIA","Decision":"BUY",
        "Decision Rating":"Strong Buy","Investment Score":90,
        "Opportunity Score":91,"Conviction Score":92,
        "Investment Thesis":"Great","Thesis Strengths":"AI;Moat",
        "Data Coverage":88,"Source Quality":80,"Data Freshness":100,
        "Missing Required Features":"valuation:pe",
        "Observed Risk Penalty":4,"Risk Uncertainty Penalty":3,
        "Risk Evidence Missing":"short_float"
    }])
    reports=build_company_reports(df)
    assert len(reports)==1
    r=reports[0]
    assert r.symbol=="NVDA"
    assert r.investment_thesis=="Great"
    assert r.strengths==("AI","Moat")
    assert r.data_coverage==88
    assert r.source_quality==80
    assert r.data_freshness==100
    assert r.missing_required_features==("valuation:pe",)
    assert r.observed_risk_penalty==4
    assert r.risk_uncertainty_penalty==3
    assert r.risk_evidence_missing==("short_float",)
