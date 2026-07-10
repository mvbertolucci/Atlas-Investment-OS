# PR-015.5D — Excel Domain Migration

## Objetivo

Migrar a aba `Decision Analysis` do Excel para consumir
objetos `CompanyReport`, mantendo as demais abas e interfaces
atuais compatíveis.

## Arquivos

- `reports/excel.py`
- `tests/test_excel_domain.py`

## O que mudou

- `build_company_reports(df)` cria os objetos de domínio.
- `_company_reports_dataframe()` converte os objetos apenas
  no limite da apresentação.
- A aba `Decision Analysis` deixa de ler diretamente as
  colunas do DataFrame bruto.

## Compatibilidade

As funções públicas continuam iguais:

```python
write_latest_and_history(df, output_dir)
```

## Testes

```cmd
pytest tests/test_excel_domain.py
pytest
python run_all.py
```

## Validação manual

Abra `output/latest.xlsx` e confirme a aba:

- `Decision Analysis`

Colunas esperadas:

- Decision
- Decision Rating
- Suggested Action
- Decision Confidence
- Decision Drivers
- Investment Thesis
- Thesis Strengths
- Thesis Risks
- Thesis Catalysts

## Commit

```cmd
git add .
git commit -m "PR-015.5D: Migrate Excel Decision Analysis to CompanyReport"
```
