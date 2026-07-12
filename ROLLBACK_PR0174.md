# Rollback

Antes do commit:

```cmd
del tests\test_deal_breaker_contract.py
del docs\CHANGELOG_PR0174.md
del README_PR0174.md
```

Reverter a edicao:
- `analytics/mapper.py`: remover o bloco que multiplica `short_float` por
  100 (a conversao fracao -> pontos percentuais).

Nota: reverter faz o deal breaker de short float voltar a nunca disparar
(bug), mas nao muda nenhum outro score.

Depois do commit:

```cmd
git revert HEAD
```
