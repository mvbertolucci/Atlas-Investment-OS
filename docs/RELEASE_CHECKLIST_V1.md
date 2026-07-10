# Release Checklist — Atlas v1.0.0

## Passo 1 — Aplicar o pacote

Extraia o ZIP na raiz do projeto.

## Passo 2 — Limpeza

Execute:

```cmd
cleanup_release_v1.bat
```

## Passo 3 — Teste específico

```cmd
pytest tests/test_portfolio_report.py
```

## Passo 4 — Suíte completa

```cmd
pytest
```

## Passo 5 — Execução completa

```cmd
python run_all.py
```

## Passo 6 — Conferência

```cmd
git status
```

## Passo 7 — Commit

```cmd
git add .
git commit -m "release: Atlas v1.0.0"
```

## Passo 8 — Tag

```cmd
git tag -a v1.0.0 -m "Atlas Investment OS v1.0.0"
```

## Passo 9 — Verificação

```cmd
git status
git tag
```
