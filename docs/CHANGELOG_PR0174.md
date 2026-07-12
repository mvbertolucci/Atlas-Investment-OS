# Changelog

PR-017.4 — Deal Breaker de Short Float (escala) + Contrato da Camada

- `analytics/mapper.py`: `normalize_columns` converte `short_float` de
  fracao (0.2449) para pontos percentuais (24.49). O deal breaker
  `short_float_max: 20.0` esta em pontos percentuais e nunca disparava
  contra uma fracao (<= ~1). Efeito colateral desejado: short_float nos
  outputs vira legivel em p.p.
- `tests/test_deal_breaker_contract.py` (novo): contrato da camada de deal
  breakers -- toda chave do config e reconhecida, resolve para coluna
  produzivel, e cada regra dispara quando violada / silencia quando
  cumprida (via normalize_columns, exercitando a escala real). Fecha a
  classe de bug que apareceu no PR-017.1 (chaves nao lidas, bloco altman_z
  ausente) e PR-017.2 (escala).

Prova (smoke real): BYND (24% short) passa a disparar "Short float alto";
AMD (2,5%) segue limpa. Antes, essa regra nunca disparava para ninguem.

177 passed. Ver README_PR0174.md.
