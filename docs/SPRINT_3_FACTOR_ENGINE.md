# Sprint 3 — Factor Engine

## Objetivo
Transformar o Atlas de um sistema baseado em indicadores hardcoded para um sistema baseado em fatores configuráveis pela Feature Store.

## Arquivos adicionados
- `factors/engine.py`
- `models/investment_model.py`
- `config/model.yaml`

## Arquivo substituído
- `scoring/investment.py`

## Como funciona
1. `config/features.yaml` define as métricas e a qual fator pertencem.
2. `factors.engine` calcula cada fator automaticamente.
3. `config/model.yaml` combina os fatores no Investment Score.
4. `scoring.investment` aplica deal breakers e recomendação.

## Critério de aceite
Rodar:

```cmd
python run_all.py
```

Deve gerar `output/latest.xlsx` com:
- Business Factor / Business Score
- Valuation Factor / Valuation Score
- Financial Factor / Financial Score
- Timing Factor / Timing Score
- Model Confidence / Confidence Score
- Investment Score
- Recommendation
