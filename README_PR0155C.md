# PR-015.5C — Morning Brief Domain Migration

## Objetivo

Migrar o Morning Brief para usar `CompanyReport` como
modelo de domínio para empresas, mantendo compatibilidade
com as interfaces atuais baseadas em DataFrame.

## Arquivos

- `reports/morning_brief.py`
- `tests/test_morning_brief_domain.py`

## Compatibilidade

As assinaturas públicas continuam iguais:

- `render_morning_brief(current_df, database_path, ...)`
- `write_morning_brief(current_df, database_path, ...)`
- `build_morning_brief_dataframe(...)`

Internamente, o Morning Brief converte o DataFrame usando
`build_company_reports()` e renderiza os ativos a partir de
objetos `CompanyReport`.

## Testes

```cmd
pytest tests/test_morning_brief_domain.py
pytest
python run_all.py
```

## Commit

```cmd
git add .
git commit -m "PR-015.5C: Migrate Morning Brief to CompanyReport"
```
