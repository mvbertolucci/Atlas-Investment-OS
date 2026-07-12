# Changelog

PR-017.6 — Remover o Confidence Score Fantasma

- Removida a chamada e o import de `add_confidence_score` em `run_all.py`.
- Deletado `analytics/validator.py` (codigo morto: computava um
  "Confidence Score" sempre sobrescrito pelo Model Confidence do factor
  engine, e "Metrics Available/Expected" nunca lidos nem persistidos).
- Deletado `pipeline/runner.py` e o pacote `pipeline/`: runner orfao do
  PR-013.4 nunca conectado (sem __main__, ninguem importa, docs usam
  run_all.py) e ja divergido (sem compute_fundamentals, period=1y). Rodá-lo
  reintroduziria os bugs 017.1/017.2. Nada o invocava.
- `tests/test_confidence_score.py` (novo): trava que o factor engine e a
  fonte unica do Confidence Score (== Model Confidence; valor pre-existente
  e sobrescrito).

Comportamento inalterado: o Confidence Score que chega aos consumidores
sempre foi o Model Confidence (calculado pelo engine independentemente do
validator). Verificado por baseline sintetico identico com e sem
add_confidence_score.

Ver README_PR0176.md.
