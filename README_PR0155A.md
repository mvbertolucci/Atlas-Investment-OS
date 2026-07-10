# PR-015.5A — Reporting Domain Models

## Objetivo

Criar a primeira camada de domínio do Atlas para relatórios,
sem alterar o pipeline atual.

## Arquivos

- `reports/report_models.py`
- `tests/test_report_models.py`

## Modelos incluídos

### CompanyReport

Contrato principal para relatórios individuais:

- scores;
- decisão;
- ação sugerida;
- tese;
- forças;
- riscos;
- catalisadores;
- deal breakers.

### MarketSummary

Resumo agregado de uma execução do Atlas.

### PortfolioReport

Contrato inicial para a futura camada de Portfolio Intelligence.

## Instalação

Extraia o ZIP na raiz do projeto.

## Testes

```cmd
pytest tests/test_report_models.py
pytest
```

## Impacto

Nenhum módulo existente é alterado.
O pipeline continua funcionando sem mudanças.

## Commit

```cmd
git add .
git commit -m "PR-015.5A: Add Reporting Domain Models"
```
