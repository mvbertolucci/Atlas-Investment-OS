# PR-015.4B — Investment Thesis Integration

## Arquivos para substituir

- `scoring/investment.py`
- `reports/excel.py`
- `reports/morning_brief.py`
- `run_all.py`

## Arquivo novo

- `tests/test_thesis_integration.py`

## Resultado

A tese passa a ser gerada dentro do pipeline e aparece:

- no DataFrame principal;
- na aba `Decision Analysis` do Excel;
- no `Summary`;
- no Morning Brief;
- no resumo do terminal com Decision e Conviction.

## Instalação

Extraia o ZIP na raiz do projeto e permita a substituição dos arquivos.

## Testes

```cmd
pytest tests/test_thesis_integration.py
pytest
python run_all.py
```

## Critérios de aceite

No `output/latest.xlsx`, confirme a aba `Decision Analysis` e as colunas:

- Investment Thesis
- Thesis Strengths
- Thesis Risks
- Thesis Catalysts

No `output/morning_brief.md`, confirme:

- Decisão
- Conviction
- Tese
- Ação

## Commit

```cmd
git add .
git commit -m "PR-015.4B: Integrate Investment Thesis"
```
