# Rollback

Antes do commit:

```cmd
del tests\test_confidence_score.py
del docs\CHANGELOG_PR0176.md
del README_PR0176.md
```

Restaurar `analytics/validator.py` e o pacote `pipeline/` (via git) e
reverter as edicoes:
- `git checkout HEAD -- analytics/validator.py pipeline/`
- `run_all.py`: readicionar `from analytics.validator import add_confidence_score`
  e a linha `result = add_confidence_score(result)` entre normalize_columns
  e score_dataframe em build_scores.

Nota: reverter reintroduz o codigo morto (Confidence Score recomputado e
descartado) e o runner orfao, sem mudar nenhum output.

Depois do commit:

```cmd
git revert HEAD
```
