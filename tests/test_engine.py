from __future__ import annotations

from pathlib import Path

import pandas as pd

from factors.engine import score_all_factors


def test_factor_engine_scores_are_not_neutral_when_features_exist(tmp_path: Path):
    features_yaml = tmp_path / "features.yaml"
    model_yaml = tmp_path / "model.yaml"

    features_yaml.write_text(
        """
business:
  roe:
    label: ROE
    weight: 1.0
    higher_is_better: true

financial:
  debt_to_equity:
    label: Debt to Equity
    weight: 1.0
    higher_is_better: false

timing:
  rsi_14:
    label: RSI
    weight: 1.0
    higher_is_better: false
""",
        encoding="utf-8",
    )

    model_yaml.write_text(
        """
factor_weights:
  business: 0.4
  financial: 0.3
  timing: 0.3
""",
        encoding="utf-8",
    )

    df = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "roe": [30, 20, 10],
            "debt_to_equity": [0.2, 1.0, 2.0],
            "rsi_14": [35, 55, 80],
        }
    )

    result = score_all_factors(df, features_yaml, model_yaml)

    assert "Business Score" in result.columns
    assert "Financial Score" in result.columns
    assert "Timing Score" in result.columns
    assert "Investment Score" in result.columns

    assert result["Business Score"].nunique() > 1
    assert result["Financial Score"].nunique() > 1
    assert result["Timing Score"].nunique() > 1


def test_missing_features_return_neutral_score(tmp_path: Path):
    features_yaml = tmp_path / "features.yaml"
    model_yaml = tmp_path / "model.yaml"

    features_yaml.write_text(
        """
business:
  roe:
    label: ROE
    weight: 1.0
    higher_is_better: true
""",
        encoding="utf-8",
    )

    model_yaml.write_text(
        """
factor_weights:
  business: 1.0
""",
        encoding="utf-8",
    )

    df = pd.DataFrame({"symbol": ["AAA", "BBB"]})

    result = score_all_factors(df, features_yaml, model_yaml)

    assert all(result["Business Score"] == 50.0)
    assert all(result["Business Confidence"] == 0.0)


def test_lower_is_better_feature_ranking(tmp_path: Path):
    features_yaml = tmp_path / "features.yaml"
    model_yaml = tmp_path / "model.yaml"

    features_yaml.write_text(
        """
financial:
  debt_to_equity:
    label: Debt to Equity
    weight: 1.0
    higher_is_better: false
""",
        encoding="utf-8",
    )

    model_yaml.write_text(
        """
factor_weights:
  financial: 1.0
""",
        encoding="utf-8",
    )

    df = pd.DataFrame(
        {
            "symbol": ["LOW_DEBT", "HIGH_DEBT"],
            "debt_to_equity": [0.2, 3.0],
        }
    )

    result = score_all_factors(df, features_yaml, model_yaml)

    low_debt_score = result.loc[result["symbol"] == "LOW_DEBT", "Financial Score"].iloc[0]
    high_debt_score = result.loc[result["symbol"] == "HIGH_DEBT", "Financial Score"].iloc[0]

    assert low_debt_score > high_debt_score