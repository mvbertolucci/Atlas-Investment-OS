# PR-017.6 — Remover o Confidence Score Fantasma (dupla definicao / codigo morto)

## Objetivo

Fechar o smell identificado durante a linha PR-017.x: o "Confidence Score"
era calculado em dois lugares, e o primeiro era sempre descartado.

### O que acontecia

`analytics/validator.py::add_confidence_score` computava, ANTES do scoring:
- `Confidence Score` = % de CORE_METRICS (lista curada) presentes;
- `Metrics Available` / `Metrics Expected`.

Logo em seguida, `factors/engine.py::score_all_factors` computava
`Model Confidence` (media das confidences por fator = peso-com-dado /
peso-total) e o **aliasava para `Confidence Score`**, sobrescrevendo o valor
do validator. Nos dois pipelines (`run_all.py` e `pipeline/runner.py`) a
ordem era sempre `normalize -> add_confidence_score -> score_dataframe`,
entao o Confidence Score do validator nunca sobrevivia.

Resultado: as tres colunas do validator eram inuteis:
- `Confidence Score`: sempre sobrescrita pelo Model Confidence;
- `Metrics Available` / `Metrics Expected`: nunca lidas por logica nem
  persistidas (history_db e excel extraem campos nomeados, nao dao dump do
  frame inteiro).

Artefato de evolucao: o factor engine (mais principled, pois pondera pela
importancia de cada feature) superou o validator, que ficou vestigial.

## Mudancas (behavior-preserving)

- Removida a chamada `add_confidence_score` de `run_all.py` (e o import).
- Deletado `analytics/validator.py` (a funcao e o CORE_METRICS so eram
  usados por ela mesma).
- `tests/test_confidence_score.py` (novo): trava que o factor engine e a
  fonte autoritativa -- Confidence Score == Model Confidence, e um valor
  pre-existente e sobrescrito (sem mais dupla definicao com ordem de
  execucao decidindo o vencedor).

### Bonus: removido o runner orfao `pipeline/runner.py`

Ao rastrear os consumidores do Confidence Score, encontrei
`pipeline/runner.py`: um quase-duplicado do `run_all.py` nascido no PR-013.4
("Refactor Atlas execution pipeline") que NUNCA foi conectado -- sem
`__main__`, ninguem importa, e todos os docs usam `python run_all.py`. Pior,
divergiu: ficou sem `compute_fundamentals` (PR-017.1) e com `period="1y"`
(pre-017.2), entao rodá-lo reintroduziria peso fantasma e o momentum_12m
quebrado. Deletado o arquivo e o pacote `pipeline/` (so continha ele + um
`__init__.py` vazio). `run_all.py` e o unico entry point, como os docs ja
diziam. Nada o invocava -> zero mudanca de comportamento.

## Prova de que nada muda

O `Confidence Score` que chega a todos os consumidores (opportunity,
conviction, thesis, reports, history DB) e o `Model Confidence`, calculado
pelo engine INDEPENDENTEMENTE do validator. Verificado em frame sintetico
com disponibilidade parcial:

```
Confidence Score COM add_confidence_score : [92.5, 100.0, 90.0, 100.0, 100.0, 100.0]
Confidence Score SEM add_confidence_score : [92.5, 100.0, 90.0, 100.0, 100.0, 100.0]
IDENTICO: True
```

`Metrics Available`/`Metrics Expected` nunca alcancavam output (checado:
history_db.save_snapshot e reports/excel extraem campos nomeados).

## Nota / candidato futuro

Se a cobertura de dados por CORE_METRICS for desejada como sinal proprio
(distinto do Model Confidence), o certo e promove-la a uma coluna "Data
Coverage" que SOBREVIVA e chegue aos relatorios -- nao recomputar um
Confidence Score que morre. Nao feito aqui para manter behavior-preserving.

## Testes

```cmd
pytest tests/test_confidence_score.py
pytest
python run_all.py
```

182 passed.

## Commit

```cmd
git add -A
git commit -m "PR-017.6: Remove dead pre-scoring Confidence Score (single source: factor engine)"
```
