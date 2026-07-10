import pandas as pd
from reports.report_engine import build_company_reports

def test_build_company_reports():
    df=pd.DataFrame([{
        "symbol":"NVDA","name":"NVIDIA","Decision":"BUY",
        "Decision Rating":"Strong Buy","Investment Score":90,
        "Opportunity Score":91,"Conviction Score":92,
        "Investment Thesis":"Great","Thesis Strengths":"AI;Moat"
    }])
    reports=build_company_reports(df)
    assert len(reports)==1
    r=reports[0]
    assert r.symbol=="NVDA"
    assert r.investment_thesis=="Great"
    assert r.strengths==("AI","Moat")
