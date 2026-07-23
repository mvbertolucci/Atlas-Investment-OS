# ADR-044 — Referência de score inclui qualquer domicílio (ADRs no cross-section)

- **Status**: Accepted
- **Data**: 2026-07-23
- **Relacionado**: `config/universe_market.yaml`, `portfolio/model_portfolio.py` (build da referência), `application/scoring.py` (carrega a referência oficial), `scoring/reference.py`, ADR-036/`config/universe_adr.yaml` (lente de ADR)

## Contexto

A referência cross-sectional de score (`output/dados/scoring_reference_market.json`,
`universe_id = US_MARKET_ELIGIBLE`) é a base contra a qual todos os percentis de
fator são calculados. Ela era construída do universo de mercado amplo filtrado
por `config/universe_market.yaml`, que exigia `allowed_countries: [United States]`
— **filtro por domicílio do emissor**, não por mercado de listagem.

Consequência medida: dos ~6.959 papéis US-listed coletados, **2.429** entravam
na referência (todos domiciliados nos EUA) e **501** que passavam em todos os
demais filtros (US-listed em USD, EQUITY, ≥ $300M, volume, campos obrigatórios)
ficavam de fora **apenas por domicílio estrangeiro**. Ao mesmo tempo, as
holdings estrangeiras da carteira real (ASML/NL, BTI/UK, BNTX/DE, JBS/BR,
YPF/AR, PAM/AR) **continuavam sendo pontuadas** — mas contra um cross-section
puramente doméstico do qual não faziam parte. Um ADR de mercado emergente
parecia "barato" em valuation em parte pela geografia (múltiplos estruturalmente
menores), não por barganha real, distorcendo o percentil.

Não há justificativa metodológica para calcular percentis só com empresas dos
EUA quando o papel negocia no mesmo mercado (bolsa americana, USD) e passa nos
mesmos filtros de qualidade/tamanho/liquidez.

## Decisão

`config/universe_market.yaml`: `allowed_countries: [United States]` →
`allowed_countries: ["*"]` (qualquer domicílio). Os demais filtros são
inalterados. A referência passa de **2.429 → 2.930** nomes (48 países), e as
holdings estrangeiras passam a ser pontuadas contra um universo que as inclui.

O `universe_id` permanece **US_MARKET_ELIGIBLE**: ele denota o mercado de
*listagem* (bolsas dos EUA), do qual ADRs fazem parte — o que mudou foi o filtro
de *domicílio*, não o mercado. Manter o id evita churn de contrato em ~8 arquivos
de teste e mantém a compatibilidade da chave de referência.

A referência foi reconstruída **do checkpoint de coleta existente**
(`data/research_universe_collection_market.json`, coleta de 2026-07-13) via
`python -m portfolio.model_portfolio --label market ...` — **sem nova coleta de
rede**; os 501 estrangeiros já estavam coletados, só eram descartados na
elegibilidade.

A lente de ADR (`config/universe_adr.yaml`, foreign-only) permanece como visão
de pesquisa separada; o universo de mercado agora a contém (mercado = EUA +
estrangeiros US-listed).

## Alternativas consideradas

- **Referência all-country dedicada, desacoplada do screener de mercado**: mais
  isolada, mas duplica política e coleta sem ganho — o screener de mercado já é
  o universo natural. Rejeitada.
- **Renomear `universe_id` para `US_LISTED_ELIGIBLE`**: mais preciso, mas o id
  atual já é correto (mercado de listagem) e o rename custa churn em vários
  contratos/testes sem ganho metodológico. Rejeitada.

## Consequências

- **Todos os percentis mudam** (o cross-section cresceu ~20%). Impacto por
  fator: qualidade/rentabilidade são comparáveis cross-border (mudança pequena);
  valuation muda mais para nomes de mercados emergentes, agora medidos contra um
  universo que inclui pares estrangeiros. Ver a validação `--portfolio` na nota
  de sessão do STATUS.md para o antes/depois nas 6 holdings estrangeiras.
- Escolha governada e explícita (AGENTS.md): config de universo é business
  configuration; a mudança está documentada aqui e validada com run real.
- A referência atual foi reconstruída do checkpoint de 2026-07-13 (defasado ~10
  dias). Um refresh amplo da coleta é tarefa operacional separada (ver
  `docs/UNIVERSE_SOURCES.md`), após o qual a referência é reconstruída com o
  mesmo comando.

## Rollback

Reverter `allowed_countries` para `[United States]` em
`config/universe_market.yaml` e reconstruir a referência. Nenhuma lógica mudou.
